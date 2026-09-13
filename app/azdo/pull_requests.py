"""Pull request queries and explicit PR validation association."""

from __future__ import annotations

import urllib.parse
from typing import Any

from app.azdo.builds import quote
from app.azdo.client import AzureDevOpsClient


def active_pull_requests(client: AzureDevOpsClient, project: str, repository: str) -> list[dict[str, Any]]:
    query = urllib.parse.urlencode({"searchCriteria.status": "active", "api-version": "7.1"})
    response = client.get(f"/{quote(project)}/_apis/git/repositories/{quote(repository)}/pullrequests?{query}")
    return response.get("value", [])


def validation_branch(pr_id: int) -> str:
    """Azure DevOps PR validation refs explicitly identify the associated PR."""
    return f"refs/pull/{pr_id}/merge"
