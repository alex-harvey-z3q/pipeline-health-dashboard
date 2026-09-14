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


def pull_request_changed_paths(
    client: AzureDevOpsClient,
    project: str,
    repository: str,
    pr_id: int,
) -> set[str]:
    """Return changed repo-relative paths from the latest pull-request iteration."""
    iterations = client.get(
        f"/{quote(project)}/_apis/git/repositories/{quote(repository)}/pullRequests/{pr_id}/iterations?api-version=7.1"
    ).get("value", [])
    iteration_ids = [int(iteration["id"]) for iteration in iterations if iteration.get("id") is not None]
    if not iteration_ids:
        return set()
    query = urllib.parse.urlencode({"$top": 1000, "api-version": "7.1"})
    response = client.get(
        f"/{quote(project)}/_apis/git/repositories/{quote(repository)}/pullRequests/{pr_id}/iterations/{max(iteration_ids)}/changes?{query}"
    )
    return {
        str(change["item"]["path"])
        for change in response.get("changeEntries", [])
        if isinstance(change.get("item"), dict) and change["item"].get("path")
    }


def validation_branch(pr_id: int) -> str:
    """Azure DevOps PR validation refs explicitly identify the associated PR."""
    return f"refs/pull/{pr_id}/merge"


def pull_request_web_url(organization_url: str, project: str, repository: str, pull_request: dict[str, Any]) -> str:
    """Return an Azure DevOps browser URL, never the REST API URL on the PR payload."""
    web_url = pull_request.get("_links", {}).get("web", {}).get("href")
    if web_url:
        return str(web_url)
    return (
        f"{organization_url.rstrip('/')}/{quote(project)}/_git/{quote(repository)}"
        f"/pullrequest/{int(pull_request['pullRequestId'])}"
    )
