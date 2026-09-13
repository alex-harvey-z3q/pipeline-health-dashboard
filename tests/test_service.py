import unittest

from app.config import DashboardConfig, ProjectConfig
from app.models import PipelineHealth, PipelineSpec, RepositorySpec
from app.service import MAIN_BRANCH, collect_dashboard, pipeline_health, repository_health_state, repository_healths


class MainBranchClient:
    def __init__(self):
        self.paths: list[str] = []

    def get(self, path):
        self.paths.append(path)
        if "pullrequests" in path:
            return {"value": [{"pullRequestId": 42, "title": "Change template", "sourceRefName": "refs/heads/change", "targetRefName": "refs/heads/main"}]}
        if "test/runs" in path:
            return {"value": [{"totalTests": 2, "passedTests": 2, "failedTests": 0}]}
        if "branchName=refs%2Fpull%2F42%2Fmerge" in path:
            return {"value": [{"id": 9, "uri": "vstfs:///Build/Build/9", "buildNumber": "9", "status": "completed", "result": "failed"}]}
        if "branchName=refs%2Fheads%2Fmain" in path and "definitions=1" in path:
            return {"value": [{"id": 7, "uri": "vstfs:///Build/Build/7", "buildNumber": "7", "status": "completed", "result": "succeeded", "sourceBranch": "refs/heads/main", "startTime": "2026-09-14T00:00:00Z", "finishTime": "2026-09-14T00:01:00Z", "queue": {"pool": {"name": "pool-a"}}}]}
        raise AssertionError(f"unexpected Azure DevOps request: {path}")


class ServiceTests(unittest.TestCase):
    def test_overview_is_repository_centric_and_queries_main_branch_only(self):
        main_pipeline = PipelineSpec(project="Templates", name="Main build", definition_id=1, role="pipeline", repository="Examples")
        validation = PipelineSpec(project="Templates", name="PR validation", definition_id=2, role="pr-validation", repository="Examples")
        unassociated = PipelineSpec(project="Templates", name="Shared job", definition_id=3, role="pipeline")
        config = DashboardConfig(
            "https://dev.azure.com/example",
            (ProjectConfig("Templates", (RepositorySpec("Examples"), RepositorySpec("TestConfig"))),),
            (main_pipeline, validation, unassociated),
        )
        client = MainBranchClient()

        dashboard = collect_dashboard(config, client)

        self.assertEqual(dashboard["summary"], {"repositories_monitored": 2, "healthy": 1, "failing": 0, "running": 0, "unknown": 1})
        self.assertNotIn("pipelines", dashboard)
        example, test_config = dashboard["repositories"]
        self.assertEqual((example["repository"], example["branch"], example["health"]), ("Examples", "main", "healthy"))
        self.assertEqual(example["latest_run"]["pipeline"]["name"], "Main build")
        self.assertEqual(example["latest_run"]["agent_pool"], "pool-a")
        self.assertEqual((test_config["repository"], test_config["health"], test_config["latest_run"]), ("TestConfig", "unknown", None))
        self.assertTrue(any("definitions=1" in path and "branchName=refs%2Fheads%2Fmain" in path for path in client.paths))
        self.assertFalse(any("definitions=2" in path and "branchName=refs%2Fheads%2Fmain" in path for path in client.paths))
        self.assertFalse(any("definitions=3" in path for path in client.paths))

    def test_pr_validation_remains_a_secondary_view(self):
        main_pipeline = PipelineSpec(project="Templates", name="Main build", definition_id=1, role="pipeline", repository="Examples")
        validation = PipelineSpec(project="Templates", name="PR validation", definition_id=2, role="pr-validation", repository="Examples")
        config = DashboardConfig(
            "https://dev.azure.com/example",
            (ProjectConfig("Templates", (RepositorySpec("Examples"),)),),
            (main_pipeline, validation),
        )

        dashboard = collect_dashboard(config, MainBranchClient())

        self.assertEqual(dashboard["pull_requests"][0]["pr_id"], 42)
        self.assertEqual(dashboard["pull_requests"][0]["validations"][0]["result"], "failed")

    def test_repository_health_state_is_explicit(self):
        pipeline = PipelineSpec(project="Platform", name="Build", definition_id=1, role="pipeline", repository="repository")
        self.assertEqual(repository_health_state(None), "unknown")
        self.assertEqual(repository_health_state(PipelineHealth(pipeline=pipeline, run_id=1, status="completed", result="succeeded")), "healthy")
        self.assertEqual(repository_health_state(PipelineHealth(pipeline=pipeline, run_id=1, status="completed", result="failed")), "failing")
        self.assertEqual(repository_health_state(PipelineHealth(pipeline=pipeline, run_id=1, status="inProgress")), "running")

    def test_repository_uses_the_most_recent_associated_main_run(self):
        older = PipelineSpec(project="Platform", name="Unit tests", definition_id=1, role="pipeline", repository="repository")
        newer = PipelineSpec(project="Platform", name="Integration tests", definition_id=2, role="smoke-test", repository="repository")
        config = DashboardConfig(
            "https://dev.azure.com/example",
            (ProjectConfig("Platform", (RepositorySpec("repository"),)),),
            (older, newer),
        )
        runs = [
            PipelineHealth(pipeline=older, run_id=10, status="completed", result="succeeded", completed_at="2026-09-14T00:01:00Z"),
            PipelineHealth(pipeline=newer, run_id=11, status="completed", result="failed", completed_at="2026-09-14T00:02:00Z"),
        ]

        health = repository_healths(config, runs)[0]

        self.assertEqual(health.latest_run.pipeline.name, "Integration tests")
        self.assertEqual(health.health, "failing")

    def test_repository_with_no_main_branch_run_is_unknown(self):
        class NoBuildClient:
            def get(self, path):
                if "pullrequests" in path:
                    return {"value": []}
                if "branchName=refs%2Fheads%2Fmain" in path:
                    return {"value": []}
                raise AssertionError(f"unexpected Azure DevOps request: {path}")

        pipeline = PipelineSpec(project="Platform", name="Build", definition_id=1, role="pipeline", repository="repository")
        config = DashboardConfig(
            "https://dev.azure.com/example",
            (ProjectConfig("Platform", (RepositorySpec("repository"),)),),
            (pipeline,),
        )

        dashboard = collect_dashboard(config, NoBuildClient())

        self.assertEqual(dashboard["repositories"][0]["health"], "unknown")
        self.assertIsNone(dashboard["repositories"][0]["latest_run"])

    def test_pipeline_api_failure_is_returned_as_an_item_error(self):
        class FailingClient:
            def get(self, path):
                from app.azdo.client import AzureDevOpsError

                raise AzureDevOpsError("Build API unavailable")

        item = pipeline_health(FailingClient(), PipelineSpec(project="Platform", name="Smoke", definition_id=1, role="smoke-test"), MAIN_BRANCH)

        self.assertEqual(item.status, "error")
        self.assertIn("unavailable", item.error)

    def test_pipeline_without_queue_information_reports_unknown_pool(self):
        class PoollessClient:
            def get(self, path):
                if "test/runs" in path:
                    return {"value": []}
                return {"value": [{"id": 7, "uri": "vstfs:///Build/Build/7", "buildNumber": "7", "status": "completed", "result": "succeeded"}]}

        item = pipeline_health(PoollessClient(), PipelineSpec(project="Platform", name="Smoke", definition_id=1, role="smoke-test"), MAIN_BRANCH)

        self.assertEqual(item.agent_pool, "Unknown")
