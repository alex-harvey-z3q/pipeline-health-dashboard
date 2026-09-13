"""Published test-run queries."""

from __future__ import annotations

import urllib.parse

from app.azdo.builds import quote
from app.azdo.client import AzureDevOpsClient
from app.models import TestSummary


def test_summary(client: AzureDevOpsClient, project: str, build_uri: str) -> TestSummary:
    query = urllib.parse.urlencode({"buildUri": build_uri, "includeRunDetails": "true", "$top": 100, "api-version": "7.1"})
    response = client.get(f"/{quote(project)}/_apis/test/runs?{query}")
    return TestSummary.from_runs(response.get("value", []))
