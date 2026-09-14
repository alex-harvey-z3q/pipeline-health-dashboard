import unittest

from app.azdo.pull_requests import pull_request_web_url


class PullRequestUrlTests(unittest.TestCase):
    def test_prefers_azure_devops_web_link_over_rest_url(self):
        pull_request = {
            "pullRequestId": 42,
            "url": "https://dev.azure.com/example/Platform/_apis/git/repositories/Repo/pullRequests/42",
            "_links": {"web": {"href": "https://dev.azure.com/example/Platform/_git/Repo/pullrequest/42"}},
        }

        url = pull_request_web_url("https://dev.azure.com/example", "Platform", "Repo", pull_request)

        self.assertEqual(url, "https://dev.azure.com/example/Platform/_git/Repo/pullrequest/42")
        self.assertNotIn("_apis", url)

    def test_builds_browser_link_when_web_link_is_unavailable(self):
        url = pull_request_web_url(
            "https://dev.azure.com/example/",
            "Shared Platform",
            "agent infrastructure",
            {"pullRequestId": 42},
        )

        self.assertEqual(
            url,
            "https://dev.azure.com/example/Shared%20Platform/_git/agent%20infrastructure/pullrequest/42",
        )
