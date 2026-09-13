import unittest

from app.config import DashboardConfig, ProjectConfig
from app.models import PipelineSpec, RepositorySpec
from app.service import collect_dashboard, pipeline_health


class FakeClient:
    def get(self, path):
        if "pullrequests" in path:
            return {"value": [{"pullRequestId": 42, "title": "Change template", "sourceRefName": "refs/heads/change", "targetRefName": "refs/heads/main"}]}
        if "test/runs" in path:
            return {"value": [{"totalTests": 2, "passedTests": 1, "failedTests": 1}]}
        if "branchName=refs%2Fpull%2F42%2Fmerge" in path:
            return {"value": [{"id": 9, "uri": "vstfs:///Build/Build/9", "buildNumber": "9", "status": "completed", "result": "failed"}]}
        return {"value": [{"id": 7, "uri": "vstfs:///Build/Build/7", "buildNumber": "7", "status": "completed", "result": "succeeded", "queue": {"name": "pool-a"}}]}


class ServiceTests(unittest.TestCase):
    def test_collects_runs_and_associates_pr_by_merge_ref(self):
        validation = PipelineSpec("validation", "Templates", "PR validation", 2, "pr-validation", repository="Examples")
        smoke = PipelineSpec("smoke", "Platform", "Smoke", 1, "smoke-test")
        config = DashboardConfig("https://dev.azure.com/example", (ProjectConfig("Templates", (RepositorySpec("Examples"),)),), (smoke, validation), (), ())

        dashboard = collect_dashboard(config, FakeClient())

        self.assertEqual(dashboard["summary"]["pipelines_monitored"], 2)
        self.assertEqual(dashboard["pipelines"][0]["reported_agent_pool"], "pool-a")
        self.assertEqual(dashboard["pull_requests"][0]["pr_id"], 42)
        self.assertEqual(dashboard["pull_requests"][0]["validations"][0]["result"], "failed")

    def test_pipeline_api_failure_is_returned_as_an_item_error(self):
        class FailingClient:
            def get(self, path):
                from app.azdo.client import AzureDevOpsError

                raise AzureDevOpsError("Build API unavailable")

        item = pipeline_health(FailingClient(), PipelineSpec("smoke", "Platform", "Smoke", 1, "smoke-test"))

        self.assertEqual(item.status, "error")
        self.assertIn("unavailable", item.error)
