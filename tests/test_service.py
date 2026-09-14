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

    def test_pr_queries_only_repositories_with_configured_validations(self):
        class PrTargetClient:
            def __init__(self):
                self.paths: list[str] = []

            def get(self, path):
                self.paths.append(path)
                if "test/runs" in path:
                    return {"value": []}
                if "branchName=refs%2Fheads%2Fmain" in path:
                    return {"value": [{"id": 1, "uri": "vstfs:///Build/Build/1", "status": "completed", "result": "succeeded"}]}
                if "repositories/Enabled/pullrequests" in path:
                    return {"value": [{"pullRequestId": 42, "title": "Change", "sourceRefName": "refs/heads/change", "targetRefName": "refs/heads/main"}]}
                if "branchName=refs%2Fpull%2F42%2Fmerge" in path:
                    return {"value": [{"id": 2, "uri": "vstfs:///Build/Build/2", "status": "completed", "result": "succeeded"}]}
                raise AssertionError(f"unexpected Azure DevOps request: {path}")

        main_pipeline = PipelineSpec(project="Platform", name="Main", definition_id=1, role="pipeline", repository="Enabled")
        validation_one = PipelineSpec(project="Platform", name="Validation one", definition_id=2, role="pr-validation", repository="Enabled")
        validation_two = PipelineSpec(project="Platform", name="Validation two", definition_id=3, role="pr-validation", repository="Enabled")
        config = DashboardConfig(
            "https://dev.azure.com/example",
            (ProjectConfig("Platform", (RepositorySpec("Enabled"), RepositorySpec("Ignored"))),),
            (main_pipeline, validation_one, validation_two),
        )
        client = PrTargetClient()

        dashboard = collect_dashboard(config, client)

        self.assertEqual(len(dashboard["pull_requests"]), 1)
        self.assertEqual(len(dashboard["pull_requests"][0]["validations"]), 2)
        self.assertTrue(any("repositories/Enabled/pullrequests" in path for path in client.paths))
        self.assertFalse(any("repositories/Ignored/pullrequests" in path for path in client.paths))

    def test_repository_health_state_is_explicit(self):
        pipeline = PipelineSpec(project="Platform", name="Build", definition_id=1, role="pipeline", repository="repository")
        self.assertEqual(repository_health_state(None), "unknown")
        self.assertEqual(repository_health_state(PipelineHealth(pipeline=pipeline, run_id=1, status="completed", result="succeeded")), "healthy")
        self.assertEqual(repository_health_state(PipelineHealth(pipeline=pipeline, run_id=1, status="completed", result="failed")), "failing")
        self.assertEqual(repository_health_state(PipelineHealth(pipeline=pipeline, run_id=1, status="inProgress")), "running")

    def test_repository_health_ignores_newer_non_ci_runs(self):
        ci = PipelineSpec(project="Platform", name="Unit tests", definition_id=1, role="pipeline", repository="repository")
        smoke = PipelineSpec(project="Platform", name="Integration tests", definition_id=2, role="smoke-test", repository="repository")
        deployment = PipelineSpec(project="Platform", name="Deploy", definition_id=3, role="deployment", repository="repository")
        image_build = PipelineSpec(project="Platform", name="Image build", definition_id=4, role="image-build", repository="repository")
        config = DashboardConfig(
            "https://dev.azure.com/example",
            (ProjectConfig("Platform", (RepositorySpec("repository"),)),),
            (ci, smoke, deployment, image_build),
        )
        runs = [
            PipelineHealth(pipeline=ci, run_id=10, status="completed", result="succeeded", completed_at="2026-09-14T00:01:00Z"),
            PipelineHealth(pipeline=smoke, run_id=11, status="completed", result="failed", completed_at="2026-09-14T00:02:00Z"),
            PipelineHealth(pipeline=deployment, run_id=12, status="completed", result="failed", completed_at="2026-09-14T00:03:00Z"),
            PipelineHealth(pipeline=image_build, run_id=13, status="completed", result="failed", completed_at="2026-09-14T00:04:00Z"),
        ]

        health = repository_healths(config, runs)[0]

        self.assertEqual(health.latest_run.pipeline.name, "Unit tests")
        self.assertEqual(health.health, "healthy")

    def test_repository_without_a_normal_ci_pipeline_is_unknown(self):
        smoke = PipelineSpec(project="Platform", name="Smoke", definition_id=1, role="smoke-test", repository="repository")
        config = DashboardConfig(
            "https://dev.azure.com/example",
            (ProjectConfig("Platform", (RepositorySpec("repository"),)),),
            (smoke,),
        )

        health = repository_healths(config, [PipelineHealth(pipeline=smoke, run_id=1, status="completed", result="succeeded")])[0]

        self.assertEqual(health.health, "unknown")
        self.assertIsNone(health.latest_run)

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

    def test_test_api_failure_does_not_change_build_health(self):
        class TestFailingClient:
            def __init__(self, result):
                self.result = result

            def get(self, path):
                if "test/runs" in path:
                    from app.azdo.client import AzureDevOpsError

                    raise AzureDevOpsError("Test API unavailable")
                return {"value": [{"id": 7, "uri": "vstfs:///Build/Build/7", "status": "completed", "result": self.result}]}

        pipeline = PipelineSpec(project="Platform", name="Build", definition_id=1, role="pipeline", repository="repository")
        for build_result, expected_health in (("succeeded", "healthy"), ("failed", "failing")):
            with self.subTest(build_result=build_result):
                item = pipeline_health(TestFailingClient(build_result), pipeline, MAIN_BRANCH)

                self.assertEqual(item.result, build_result)
                self.assertEqual(repository_health_state(item), expected_health)
                self.assertFalse(item.tests.available)
                self.assertEqual(item.tests.total, 0)
                self.assertIn("Test API unavailable", item.tests.error)
