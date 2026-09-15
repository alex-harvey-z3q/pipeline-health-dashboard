import unittest
import urllib.parse
from datetime import datetime, timezone

from app.azdo.client import AzureDevOpsError
from app.config import DashboardConfig, ProjectConfig
from app.models import PipelineSpec, RepositorySpec, ReusableTemplatePRConfig
from app.service import collect_dashboard, collect_reusable_template_prs


NOW = datetime(2026, 9, 15, 12, 0, tzinfo=timezone.utc)


class TemplatePrClient:
    organization_url = "https://dev.azure.com/example"

    def __init__(self, pull_requests=(), changed_paths=None, failing_pr_ids=(), builds=None, failing_definition_ids=()):
        self.pull_requests = list(pull_requests)
        self.changed_paths = changed_paths or {}
        self.failing_pr_ids = set(failing_pr_ids)
        self.builds = builds or {}
        self.failing_definition_ids = set(failing_definition_ids)
        self.paths: list[str] = []

    def get(self, path):
        self.paths.append(path)
        if "/_apis/git/repositories/Templates?" in path:
            return {"id": "templates-id", "defaultBranch": "refs/heads/main"}
        if "/_apis/build/definitions?" in path:
            return {"value": []}
        if "/_apis/build/builds?" in path:
            query = urllib.parse.parse_qs(path.partition("?")[2])
            definition_id = int(query["definitions"][0])
            if definition_id in self.failing_definition_ids:
                raise AzureDevOpsError(f"Build lookup unavailable for {definition_id}")
            key = (definition_id, query.get("branchName", [None])[0])
            return {"value": self.builds.get(key, [])}
        if "/_apis/test/runs?" in path:
            return {"value": [{"totalTests": 148, "passedTests": 148, "failedTests": 0}]}
        if "/pullrequests?" in path:
            return {"value": self.pull_requests}
        if "/iterations?" in path:
            return {"value": [{"id": 1}]}
        if "/changes?" in path:
            pr_id = int(path.split("/pullRequests/")[1].split("/")[0])
            if pr_id in self.failing_pr_ids:
                raise AzureDevOpsError(f"Changes unavailable for {pr_id}")
            return {"changeEntries": [{"item": {"path": item_path}} for item_path in self.changed_paths.get(pr_id, [])]}
        raise AssertionError(f"unexpected Azure DevOps request: {path}")


def pull_request(pr_id, *, target="refs/heads/main", created_at="2026-09-12T12:00:00Z", title=None):
    return {
        "pullRequestId": pr_id,
        "title": title or f"Change {pr_id}",
        "sourceRefName": f"refs/heads/change-{pr_id}",
        "targetRefName": target,
        "creationDate": created_at,
        "createdBy": {"displayName": "Example Author"},
        "_links": {"web": {"href": f"https://dev.azure.com/example/Pipeline%20Templates/_git/Templates/pullrequest/{pr_id}"}},
    }


def template_config(enabled=True, max_age_days=14, path_prefixes=("/pipelines/templates/",)):
    return ReusableTemplatePRConfig(
        enabled=enabled,
        max_age_days=max_age_days,
        path_prefixes=path_prefixes,
    )


def dashboard_config(repository, pipelines=()):
    return DashboardConfig(
        "https://dev.azure.com/example",
        (ProjectConfig("Pipeline Templates", (repository,)),),
        tuple(pipelines),
    )


def validation_pipeline(definition_id, name=None):
    return PipelineSpec(
        "Pipeline Templates",
        name or f"Validation {definition_id}",
        definition_id,
        "pr-validation",
        "Templates",
    )


def validation_build(identifier, *, status="completed", result="succeeded"):
    return {
        "id": identifier,
        "uri": f"vstfs:///Build/Build/{identifier}",
        "buildNumber": str(identifier),
        "status": status,
        "result": result,
        "startTime": "2026-09-14T00:00:00Z",
        "finishTime": "2026-09-14T00:01:00Z",
        "_links": {"web": {"href": f"https://dev.azure.com/example/build/{identifier}"}},
    }


class ReusableTemplatePrTests(unittest.TestCase):
    def test_feature_disabled_and_ordinary_repository_do_not_query_prs(self):
        disabled = RepositorySpec("Templates", reusable_template_prs=template_config(enabled=False))
        ordinary = RepositorySpec("Other")
        client = TemplatePrClient()
        config = DashboardConfig(
            "https://dev.azure.com/example",
            (ProjectConfig("Pipeline Templates", (disabled, ordinary)),),
            (),
        )

        items = collect_reusable_template_prs(config, client, NOW)

        self.assertEqual(items, [])
        self.assertEqual(client.paths, [])

    def test_only_active_prs_targeting_default_branch_and_matching_prefixes_are_included(self):
        client = TemplatePrClient(
            [
                pull_request(1),
                pull_request(2, target="refs/heads/release/current"),
                pull_request(3),
                pull_request(4),
            ],
            {
                1: ["/pipelines/templates/docker/build.yml"],
                3: ["/pipelines/templates-old/build.yml"],
                4: ["/docs/readme.md"],
            },
        )

        items = collect_reusable_template_prs(
            dashboard_config(RepositorySpec("Templates", reusable_template_prs=template_config())), client, NOW
        )

        self.assertEqual([item.pr_id for item in items], [1])
        self.assertEqual(items[0].affected_areas, ["docker/"])
        self.assertEqual(items[0].matched_paths, ["/pipelines/templates/docker/build.yml"])
        self.assertEqual(sum("/pullrequests?" in path for path in client.paths), 1)
        self.assertFalse(any("/pullRequests/2/iterations" in path for path in client.paths))

    def test_multiple_changed_paths_report_affected_areas_once_each(self):
        client = TemplatePrClient(
            [pull_request(1)],
            {
                1: [
                    "/pipelines/templates/docker/build.yml",
                    "/pipelines/templates/docker/publish.yml",
                    "/pipelines/templates/containers/deploy.yml",
                    "/pipelines/templates/steps-webApp-deploy.yml",
                ]
            },
        )

        items = collect_reusable_template_prs(
            dashboard_config(RepositorySpec("Templates", reusable_template_prs=template_config())), client, NOW
        )

        self.assertEqual(items[0].affected_areas, ["containers/", "docker/", "steps-webApp-deploy.yml"])
        self.assertEqual(
            items[0].matched_paths,
            [
                "/pipelines/templates/containers/deploy.yml",
                "/pipelines/templates/docker/build.yml",
                "/pipelines/templates/docker/publish.yml",
                "/pipelines/templates/steps-webApp-deploy.yml",
            ],
        )

    def test_multiple_prefixes_and_a_path_without_a_leading_slash_match(self):
        client = TemplatePrClient(
            [pull_request(1)],
            {1: ["pipelines/templates/docker/build.yml", "/shared/workflows/validation/check.yml"]},
        )

        items = collect_reusable_template_prs(
            dashboard_config(
                RepositorySpec(
                    "Templates",
                    reusable_template_prs=template_config(
                        path_prefixes=("/pipelines/templates/", "/shared/workflows/"),
                    ),
                )
            ),
            client,
            NOW,
        )

        self.assertEqual(items[0].affected_areas, ["docker/", "validation/"])
        self.assertEqual(
            items[0].matched_paths,
            ["/pipelines/templates/docker/build.yml", "/shared/workflows/validation/check.yml"],
        )

    def test_age_and_stale_state_use_configured_threshold(self):
        client = TemplatePrClient(
            [
                pull_request(1, created_at="2026-09-12T12:00:00Z"),
                pull_request(2, created_at="2026-08-28T11:59:59Z"),
            ],
            {1: ["/pipelines/templates/build.yml"], 2: ["/pipelines/templates/build.yml"]},
        )

        items = collect_reusable_template_prs(
            dashboard_config(RepositorySpec("Templates", reusable_template_prs=template_config(max_age_days=14))), client, NOW
        )
        by_id = {item.pr_id: item for item in items}

        self.assertEqual(by_id[1].age_days, 3)
        self.assertFalse(by_id[1].stale)
        self.assertEqual(by_id[2].age_days, 18)
        self.assertTrue(by_id[2].stale)

    def test_web_url_uses_azure_devops_web_link(self):
        client = TemplatePrClient([pull_request(1)], {1: ["/pipelines/templates/build.yml"]})

        item = collect_reusable_template_prs(
            dashboard_config(RepositorySpec("Templates", reusable_template_prs=template_config())), client, NOW
        )[0]

        self.assertEqual(item.web_url, "https://dev.azure.com/example/Pipeline%20Templates/_git/Templates/pullrequest/1")
        self.assertNotIn("_apis", item.web_url)

    def test_one_pr_change_lookup_failure_does_not_hide_other_matching_prs(self):
        client = TemplatePrClient(
            [pull_request(1), pull_request(2)],
            {2: ["/pipelines/templates/deploy.yml"]},
            failing_pr_ids={1},
        )

        items = collect_reusable_template_prs(
            dashboard_config(RepositorySpec("Templates", reusable_template_prs=template_config())), client, NOW
        )

        self.assertEqual([item.pr_id for item in items], [2])

    def test_validation_uses_configured_pipeline_and_pr_merge_ref(self):
        pipeline = validation_pipeline(3892, "templates.pr.validate")
        client = TemplatePrClient(
            [pull_request(1)],
            {1: ["/pipelines/templates/docker/build.yml"]},
            builds={(3892, "refs/pull/1/merge"): [validation_build(101)]},
        )

        item = collect_reusable_template_prs(
            dashboard_config(RepositorySpec("Templates", reusable_template_prs=template_config()), (pipeline,)),
            client,
            NOW,
        )[0]

        self.assertEqual(item.validation_status, "passed")
        self.assertEqual(len(item.validation_runs), 1)
        self.assertEqual(item.validation_runs[0].pipeline.name, "templates.pr.validate")
        self.assertEqual(item.validation_runs[0].run_id, 101)
        self.assertEqual(item.validation_runs[0].tests.total, 148)
        self.assertEqual(item.validation_runs[0].run_url, "https://dev.azure.com/example/build/101")
        self.assertTrue(any("definitions=3892" in path and "branchName=refs%2Fpull%2F1%2Fmerge" in path for path in client.paths))

    def test_multiple_validation_pipelines_aggregate_failed_and_running_states(self):
        pipelines = (validation_pipeline(1), validation_pipeline(2))
        cases = (
            ({(1, "refs/pull/1/merge"): [validation_build(101)], (2, "refs/pull/1/merge"): [validation_build(102, result="canceled")]}, "failing"),
            ({(1, "refs/pull/1/merge"): [validation_build(101)], (2, "refs/pull/1/merge"): [validation_build(102, status="inProgress", result=None)]}, "running"),
        )
        for builds, expected_status in cases:
            with self.subTest(expected_status=expected_status):
                client = TemplatePrClient(
                    [pull_request(1)],
                    {1: ["/pipelines/templates/docker/build.yml"]},
                    builds=builds,
                )
                item = collect_reusable_template_prs(
                    dashboard_config(RepositorySpec("Templates", reusable_template_prs=template_config()), pipelines),
                    client,
                    NOW,
                )[0]

                self.assertEqual(item.validation_status, expected_status)
                self.assertEqual(len(item.validation_runs), 2)

    def test_validation_is_unknown_when_no_matching_build_exists(self):
        client = TemplatePrClient([pull_request(1)], {1: ["/pipelines/templates/docker/build.yml"]})

        item = collect_reusable_template_prs(
            dashboard_config(
                RepositorySpec("Templates", reusable_template_prs=template_config()),
                (validation_pipeline(3892),),
            ),
            client,
            NOW,
        )[0]

        self.assertEqual(item.validation_status, "unknown")
        self.assertIsNone(item.validation_runs[0].run_id)

    def test_one_validation_lookup_failure_does_not_hide_other_validation_runs(self):
        pipelines = (validation_pipeline(1), validation_pipeline(2))
        client = TemplatePrClient(
            [pull_request(1)],
            {1: ["/pipelines/templates/docker/build.yml"]},
            builds={(2, "refs/pull/1/merge"): [validation_build(102)]},
            failing_definition_ids={1},
        )

        item = collect_reusable_template_prs(
            dashboard_config(RepositorySpec("Templates", reusable_template_prs=template_config()), pipelines),
            client,
            NOW,
        )[0]

        self.assertEqual(item.validation_status, "unknown")
        self.assertEqual([run.run_id for run in item.validation_runs], [None, 102])
        self.assertIn("Build lookup unavailable", item.validation_runs[0].error)

    def test_dashboard_response_has_dedicated_reusable_template_pr_field(self):
        client = TemplatePrClient([pull_request(1)], {1: ["/pipelines/templates/build.yml"]})

        dashboard = collect_dashboard(
            dashboard_config(RepositorySpec("Templates", reusable_template_prs=template_config())), client
        )

        self.assertEqual([item["pr_id"] for item in dashboard["reusable_template_prs"]], [1])
        self.assertEqual(dashboard["reusable_template_prs"][0]["validation_status"], "unknown")
