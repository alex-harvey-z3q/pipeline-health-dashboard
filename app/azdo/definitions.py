"""Azure DevOps build-definition discovery for repository CI."""

from __future__ import annotations

import urllib.parse
from typing import Any

from app.azdo.builds import quote
from app.azdo.client import AzureDevOpsClient


def repository_build_definitions(
    client: AzureDevOpsClient,
    project: str,
    repository_id: str,
) -> list[dict[str, Any]]:
    """Return build definitions Azure DevOps associates with a repository ID."""
    query = urllib.parse.urlencode({"repositoryId": repository_id, "api-version": "7.1"})
    response = client.get(f"/{quote(project)}/_apis/build/definitions?{query}")
    return response.get("value", [])
