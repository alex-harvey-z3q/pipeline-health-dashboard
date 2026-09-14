import unittest
import urllib.parse

from app.azdo.client import AzureDevOpsError
from app.config import DashboardConfig, ProjectConfig
from app.models import PipelineHealth, PipelineSpec, RepositorySpec
from app.service import collect_dashboard, pipeline_health, repository_health_state


class RepositoryClient:
    def __init__(self, default_branch="refs/heads/main", builds=None, repository_error=None, build_error=None):
        self.default_branch = default_branch
        self.builds = builds if builds is not None else {}
        self.repository_error = repository_error
        self.build_error = build_error
        self.paths: list[str] = []

    def get(self, path):
        self.paths.append(path)
        if "/_apis/git/repositories/" in path:
            if self.repository_error:
                raise AzureDevOpsError(self.repository_error)
            return {"defaultBranch": self.default_branch} if self.default_branch is not None else {}
        if "test/runs" in path:
            return {"value": [{"totalTests": 2, "passedTests": 2, "failedTests": 0}]}
        if "/_apis/build/builds?" in path:
            if self.build_error:
                raise AzureDevOpsError(self.build_error)
            query = urllib.parse.parse_qs(path.partition("?")[2])
            key = (int(query["definitions"][0]), query.get("branchName", [None])[0])
            return {"value": self.builds.get(key, [])}
        raise AssertionError(f"unexpected Azure DevOps request: {path}")


def config_for(pipelines):
    return DashboardConfig(
        "https://dev.azure.com/example",
        (ProjectConfig("Platform", (RepositorySpec("repository"),)),),
        tuple(pipelines),
    )


def successful_build(identifier=7):
    return {
        "id": identifier,
        "uri": f"vstfs:///Build/Build/{identifier}",
        "buildNumber": str(identifier),
        "status": "completed",
        "result": "succeeded",
        "startTime": "2026-09-14T00:00:00Z",
        "finishTime": "2026-09-14T00:01:00Z",
        "queue": {"pool": {"name": "pool-a"}},
    }


class ServiceTests(unittest.TestCase):
    def test_repo_ci_uses_each_discovered_default_branch(self):
        pipeline = PipelineSpec(project="Platform", name="CI", definition_id=1, role="pipeline", repository="repository")
        for default_branch in ("refs/heads/main", "refs/heads/master", "refs/heads/release/current"):
            with self.subTest(default_branch=default_branch):
                client = RepositoryClient(default_branch, {(1, default_branch): [successful_build()]})

                dashboard = collect_dashboard(config_for([pipeline]), client)

                item = dashboard["repositories"][0]
                self.assertEqual(item["default_branch"], default_branch)
                self.assertEqual(item["branch"], default_branch.removeprefix("refs/heads/"))
                self.assertEqual(item["health"], "healthy")
                self.assertTrue(any(f"branchName={urllib.parse.quote(default_branch, safe='')}" in path for path in client.paths))

    def test_no_ci_pipeline_configured_is_distinct_from_no_builds(self):
        smoke = PipelineSpec(project="Platform", name="Smoke", definition_id=1, role="smoke-test", repository="repository")
        client = RepositoryClient()

        dashboard = collect_dashboard(config_for([smoke]), client)

        item = dashboard["repositories"][0]
        self.assertEqual(item["status_reason"], "No CI pipeline configured")
        self.assertEqual(item["branch"], "main")
        self.assertIsNone(item["ci_pipeline"])
        self.assertFalse(any("branchName=" in path for path in client.paths))

    def test_no_build_on_discovered_default_branch_is_explicit(self):
        pipeline = PipelineSpec(project="Platform", name="CI", definition_id=1, role="pipeline", repository="repository")

        dashboard = collect_dashboard(config_for([pipeline]), RepositoryClient("refs/heads/master"))

        item = dashboard["repositories"][0]
        self.assertEqual(item["status_reason"], "No builds found on master")
        self.assertEqual(item["ci_pipeline"]["definition_id"], 1)
        self.assertIsNone(item["latest_run"])

    def test_missing_default_branch_is_explicit(self):
        pipeline = PipelineSpec(project="Platform", name="CI", definition_id=1, role="pipeline", repository="repository")

        dashboard = collect_dashboard(config_for([pipeline]), RepositoryClient(default_branch=None))

        item = dashboard["repositories"][0]
        self.assertEqual(item["status_reason"], "Default branch unknown")
        self.assertIsNone(item["default_branch"])
        self.assertIsNone(item["error"])

    def test_null_default_branch_is_explicit(self):
        class NullDefaultBranchClient(RepositoryClient):
            def get(self, path):
                if "/_apis/git/repositories/" in path:
                    self.paths.append(path)
                    return {"defaultBranch": None}
                return super().get(path)

        pipeline = PipelineSpec(project="Platform", name="CI", definition_id=1, role="pipeline", repository="repository")

        dashboard = collect_dashboard(config_for([pipeline]), NullDefaultBranchClient())

        self.assertEqual(dashboard["repositories"][0]["status_reason"], "Default branch unknown")

    def test_repository_metadata_failure_is_explicit(self):
        pipeline = PipelineSpec(project="Platform", name="CI", definition_id=1, role="pipeline", repository="repository")

        dashboard = collect_dashboard(config_for([pipeline]), RepositoryClient(repository_error="Repository API unavailable"))

        item = dashboard["repositories"][0]
        self.assertEqual(item["status_reason"], "Unable to query Azure DevOps")
        self.assertIn("Repository API unavailable", item["error"])
        self.assertIsNone(item["latest_run"])

    def test_build_lookup_failure_is_explicit(self):
        pipeline = PipelineSpec(project="Platform", name="CI", definition_id=1, role="pipeline", repository="repository")

        dashboard = collect_dashboard(config_for([pipeline]), RepositoryClient(build_error="Build API unavailable"))

        item = dashboard["repositories"][0]
        self.assertEqual(item["status_reason"], "Unable to query Azure DevOps")
        self.assertIn("Build API unavailable", item["error"])
        self.assertIsNone(item["latest_run"])

    def test_repo_ci_excludes_non_ci_pipeline_roles(self):
        ci = PipelineSpec(project="Platform", name="CI", definition_id=1, role="pipeline", repository="repository")
        smoke = PipelineSpec(project="Platform", name="Smoke", definition_id=2, role="smoke-test", repository="repository")
        deployment = PipelineSpec(project="Platform", name="Deploy", definition_id=3, role="deployment", repository="repository")
        image_build = PipelineSpec(project="Platform", name="Image", definition_id=4, role="image-build", repository="repository")
        validation = PipelineSpec(project="Platform", name="PR", definition_id=5, role="pr-validation", repository="repository")
        client = RepositoryClient()

        collect_dashboard(config_for([ci, smoke, deployment, image_build, validation]), client)

        build_paths = [path for path in client.paths if "/_apis/build/builds?" in path]
        self.assertTrue(any("definitions=1" in path and "branchName=refs%2Fheads%2Fmain" in path for path in build_paths))
        self.assertFalse(any(f"definitions={definition_id}" in path and "branchName=" in path for definition_id in (2, 3, 4, 5) for path in build_paths))

    def test_repository_health_state_is_explicit(self):
        pipeline = PipelineSpec(project="Platform", name="Build", definition_id=1, role="pipeline", repository="repository")
        self.assertEqual(repository_health_state(None), "unknown")
        self.assertEqual(repository_health_state(PipelineHealth(pipeline=pipeline, run_id=1, status="completed", result="succeeded")), "healthy")
        self.assertEqual(repository_health_state(PipelineHealth(pipeline=pipeline, run_id=1, status="completed", result="failed")), "failing")
        self.assertEqual(repository_health_state(PipelineHealth(pipeline=pipeline, run_id=1, status="inProgress")), "running")

    def test_pipeline_api_failure_is_returned_as_an_item_error(self):
        item = pipeline_health(
            RepositoryClient(build_error="Build API unavailable"),
            PipelineSpec(project="Platform", name="Smoke", definition_id=1, role="smoke-test"),
            "refs/heads/main",
        )

        self.assertEqual(item.status, "error")
        self.assertIn("unavailable", item.error)

    def test_pipeline_without_queue_information_reports_unknown_pool(self):
        class PoollessClient:
            def get(self, path):
                if "test/runs" in path:
                    return {"value": []}
                return {"value": [{"id": 7, "uri": "vstfs:///Build/Build/7", "buildNumber": "7", "status": "completed", "result": "succeeded"}]}

        item = pipeline_health(PoollessClient(), PipelineSpec(project="Platform", name="Smoke", definition_id=1, role="smoke-test"), "refs/heads/main")

        self.assertEqual(item.agent_pool, "Unknown")

    def test_test_api_failure_does_not_change_build_health(self):
        class TestFailingClient:
            def get(self, path):
                if "test/runs" in path:
                    raise AzureDevOpsError("Test API unavailable")
                return {"value": [{"id": 7, "uri": "vstfs:///Build/Build/7", "status": "completed", "result": "succeeded"}]}

        pipeline = PipelineSpec(project="Platform", name="Build", definition_id=1, role="pipeline", repository="repository")
        item = pipeline_health(TestFailingClient(), pipeline, "refs/heads/main")

        self.assertEqual(item.result, "succeeded")
        self.assertEqual(repository_health_state(item), "healthy")
        self.assertFalse(item.tests.available)
        self.assertIn("Test API unavailable", item.tests.error)
