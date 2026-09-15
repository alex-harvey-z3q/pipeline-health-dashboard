import unittest
import urllib.parse

from app.azdo.client import AzureDevOpsError
from app.config import DashboardConfig, ProjectConfig
from app.models import PipelineSpec, RepositorySpec
from app.service import collect_dashboard, pipeline_health, repository_health_state


class DiscoveryClient:
    def __init__(self, default_branch="refs/heads/main", definitions=None, builds=None, repository_error=None, definitions_error=None):
        self.default_branch = default_branch
        self.definitions = definitions if definitions is not None else []
        self.builds = builds if builds is not None else {}
        self.repository_error = repository_error
        self.definitions_error = definitions_error
        self.paths: list[str] = []

    def get(self, path):
        self.paths.append(path)
        if "/_apis/git/repositories/" in path:
            if self.repository_error:
                raise AzureDevOpsError(self.repository_error)
            return {"id": "repo-guid", "defaultBranch": self.default_branch}
        if "/_apis/build/definitions?" in path:
            if self.definitions_error:
                raise AzureDevOpsError(self.definitions_error)
            return {"value": self.definitions}
        if "test/runs" in path:
            return {"value": [{"totalTests": 2, "passedTests": 2, "failedTests": 0}]}
        if "/_apis/build/builds?" in path:
            query = urllib.parse.parse_qs(path.partition("?")[2])
            key = (int(query["definitions"][0]), query.get("branchName", [None])[0])
            return {"value": self.builds.get(key, [])}
        raise AssertionError(f"unexpected Azure DevOps request: {path}")


def build(identifier, *, status="completed", result="succeeded"):
    return {
        "id": identifier,
        "uri": f"vstfs:///Build/Build/{identifier}",
        "buildNumber": str(identifier),
        "status": status,
        "result": result,
        "startTime": "2026-09-14T00:00:00Z",
        "finishTime": "2026-09-14T00:01:00Z",
        "queue": {"pool": {"name": "pool-a"}},
    }


def config_for(repositories, pipelines=()):
    return DashboardConfig(
        "https://dev.azure.com/example",
        (ProjectConfig("Platform", tuple(repositories)),),
        tuple(pipelines),
    )


class ServiceTests(unittest.TestCase):
    def test_repo_ci_discovers_main_master_and_nonstandard_default_branches(self):
        definitions = [{"id": 1, "name": "Ordinary CI"}]
        for default_branch in ("refs/heads/main", "refs/heads/master", "refs/heads/release/current"):
            with self.subTest(default_branch=default_branch):
                client = DiscoveryClient(default_branch, definitions, {(1, default_branch): [build(1)]})

                dashboard = collect_dashboard(config_for([RepositorySpec("repository")]), client)

                item = dashboard["repositories"][0]
                self.assertEqual(item["default_branch"], default_branch)
                self.assertEqual(item["branch"], default_branch.removeprefix("refs/heads/"))
                self.assertEqual(item["health"], "healthy")
                self.assertEqual(item["ci_runs"][0]["pipeline"]["name"], "Ordinary CI")
                self.assertTrue(any(f"branchName={urllib.parse.quote(default_branch, safe='')}" in path for path in client.paths))

    def test_repository_id_is_used_to_discover_build_definitions(self):
        client = DiscoveryClient(definitions=[])

        collect_dashboard(config_for([RepositorySpec("repository")]), client)

        definition_path = next(path for path in client.paths if "/_apis/build/definitions?" in path)
        query = urllib.parse.parse_qs(definition_path.partition("?")[2])
        self.assertEqual(query["repositoryId"], ["repo-guid"])
        self.assertEqual(query["repositoryType"], ["TfsGit"])
        self.assertEqual(query["api-version"], ["7.1"])

    def test_no_discovered_ci_definition_is_explicit(self):
        dashboard = collect_dashboard(config_for([RepositorySpec("repository")]), DiscoveryClient())

        item = dashboard["repositories"][0]
        self.assertEqual(item["status_reason"], "No default-branch CI pipeline discovered")
        self.assertEqual(item["ci_runs"], [])

    def test_missing_default_branch_is_explicit(self):
        client = DiscoveryClient(default_branch=None)
        dashboard = collect_dashboard(
            config_for([RepositorySpec("repository")]),
            client,
        )

        item = dashboard["repositories"][0]
        self.assertEqual(item["status_reason"], "Default branch unknown")
        self.assertFalse(any("/_apis/build/definitions?" in path for path in client.paths))

    def test_specialist_definitions_are_excluded_from_repo_ci(self):
        default_branch = "refs/heads/main"
        definitions = [
            {"id": 1, "name": "Normal CI"},
            {"id": 2, "name": "Misleading normal-looking smoke name"},
            {"id": 3, "name": "Deployment"},
            {"id": 4, "name": "Image"},
            {"id": 5, "name": "PR validation"},
        ]
        specialists = [
            PipelineSpec("Platform", "Smoke", 2, "smoke-test", "repository"),
            PipelineSpec("Platform", "Deploy", 3, "deployment", "repository"),
            PipelineSpec("Platform", "Image", 4, "image-build", "repository"),
            PipelineSpec("Platform", "PR", 5, "pr-validation", "repository"),
        ]
        client = DiscoveryClient(default_branch, definitions, {(1, default_branch): [build(1)]})

        dashboard = collect_dashboard(config_for([RepositorySpec("repository")], specialists), client)

        item = dashboard["repositories"][0]
        self.assertEqual(item["health"], "healthy")
        self.assertEqual([run["pipeline"]["definition_id"] for run in item["ci_runs"]], [1])
        default_branch_paths = [path for path in client.paths if "branchName=" in path]
        self.assertTrue(any("definitions=1" in path for path in default_branch_paths))
        self.assertFalse(any(f"definitions={definition_id}" in path for definition_id in (2, 3, 4, 5) for path in default_branch_paths))

    def test_multiple_discovered_ci_pipelines_aggregate_to_healthy(self):
        default_branch = "refs/heads/master"
        client = DiscoveryClient(
            default_branch,
            [{"id": 1, "name": "Lint"}, {"id": 2, "name": "Tests"}],
            {(1, default_branch): [build(1)], (2, default_branch): [build(2)]},
        )

        dashboard = collect_dashboard(config_for([RepositorySpec("repository")]), client)

        item = dashboard["repositories"][0]
        self.assertEqual(item["health"], "healthy")
        self.assertEqual([run["pipeline"]["name"] for run in item["ci_runs"]], ["Lint", "Tests"])

    def test_failing_or_running_ci_pipeline_sets_aggregate_health(self):
        definitions = [{"id": 1, "name": "Lint"}, {"id": 2, "name": "Tests"}]
        cases = (
            ({(1, "refs/heads/main"): [build(1)], (2, "refs/heads/main"): [build(2, result="failed")]}, "failing"),
            ({(1, "refs/heads/main"): [build(1, status="inProgress", result=None)], (2, "refs/heads/main"): [build(2)]}, "running"),
        )
        for builds, expected_health in cases:
            with self.subTest(expected_health=expected_health):
                dashboard = collect_dashboard(
                    config_for([RepositorySpec("repository")]),
                    DiscoveryClient(definitions=definitions, builds=builds),
                )

                self.assertEqual(dashboard["repositories"][0]["health"], expected_health)

    def test_optional_ci_definition_override_narrows_discovery(self):
        default_branch = "refs/heads/release/current"
        client = DiscoveryClient(
            default_branch,
            [{"id": 1, "name": "Lint"}, {"id": 2, "name": "Release checks"}],
            {(1, default_branch): [build(1)], (2, default_branch): [build(2)]},
        )

        dashboard = collect_dashboard(config_for([RepositorySpec("repository", ci_definition_ids=(2,))]), client)

        item = dashboard["repositories"][0]
        self.assertEqual([run["pipeline"]["definition_id"] for run in item["ci_runs"]], [2])
        self.assertFalse(any("definitions=1" in path and "branchName=" in path for path in client.paths))

    def test_no_builds_on_default_branch_is_explicit(self):
        dashboard = collect_dashboard(
            config_for([RepositorySpec("repository")]),
            DiscoveryClient(definitions=[{"id": 1, "name": "CI"}]),
        )

        item = dashboard["repositories"][0]
        self.assertEqual(item["status_reason"], "No builds found on main")
        self.assertEqual(item["health"], "unknown")
        self.assertEqual(len(item["ci_runs"]), 1)

    def test_definition_discovery_failure_is_explicit(self):
        dashboard = collect_dashboard(
            config_for([RepositorySpec("repository")]),
            DiscoveryClient(definitions_error="Definitions API unavailable"),
        )

        item = dashboard["repositories"][0]
        self.assertEqual(item["status_reason"], "Unable to query Azure DevOps")
        self.assertIn("Definitions API unavailable", item["error"])

    def test_repository_health_state_is_explicit(self):
        pipeline = PipelineSpec("Platform", "Build", 1, "pipeline", "repository")
        self.assertEqual(repository_health_state(None), "unknown")
        self.assertEqual(repository_health_state(pipeline_health(DiscoveryClient(builds={(1, "refs/heads/main"): [build(1)]}), pipeline, "refs/heads/main")), "healthy")

    def test_test_api_failure_does_not_change_build_health(self):
        class TestFailingClient:
            def get(self, path):
                if "test/runs" in path:
                    raise AzureDevOpsError("Test API unavailable")
                return {"value": [build(1)]}

        pipeline = PipelineSpec("Platform", "Build", 1, "pipeline", "repository")
        item = pipeline_health(TestFailingClient(), pipeline, "refs/heads/main")

        self.assertEqual(repository_health_state(item), "healthy")
        self.assertFalse(item.tests.available)
        self.assertIn("Test API unavailable", item.tests.error)
