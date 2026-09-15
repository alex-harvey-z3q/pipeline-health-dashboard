import unittest
from datetime import datetime, timezone

from app.azdo.client import AzureDevOpsError
from app.config import DashboardConfig, ProjectConfig
from app.models import RepositorySpec, ReusableTemplatePRConfig
from app.service import collect_dashboard, collect_reusable_template_prs


NOW = datetime(2026, 9, 15, 12, 0, tzinfo=timezone.utc)


class TemplatePrClient:
    organization_url = "https://dev.azure.com/example"

    def __init__(self, pull_requests=(), changed_paths=None, failing_pr_ids=()):
        self.pull_requests = list(pull_requests)
        self.changed_paths = changed_paths or {}
        self.failing_pr_ids = set(failing_pr_ids)
        self.paths: list[str] = []

    def get(self, path):
        self.paths.append(path)
        if "/_apis/git/repositories/Templates?" in path:
            return {"id": "templates-id", "defaultBranch": "refs/heads/main"}
        if "/_apis/build/definitions?" in path:
            return {"value": []}
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


def dashboard_config(repository):
    return DashboardConfig(
        "https://dev.azure.com/example",
        (ProjectConfig("Pipeline Templates", (repository,)),),
        (),
    )


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

    def test_dashboard_response_has_dedicated_reusable_template_pr_field(self):
        client = TemplatePrClient([pull_request(1)], {1: ["/pipelines/templates/build.yml"]})

        dashboard = collect_dashboard(
            dashboard_config(RepositorySpec("Templates", reusable_template_prs=template_config())), client
        )

        self.assertEqual([item["pr_id"] for item in dashboard["reusable_template_prs"]], [1])
