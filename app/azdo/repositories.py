"""Azure DevOps repository metadata queries."""

from __future__ import annotations

from typing import Any

from app.azdo.builds import quote
from app.azdo.client import AzureDevOpsClient


def get_repository(client: AzureDevOpsClient, project: str, repository: str) -> dict[str, Any]:
    """Return Azure DevOps metadata for one repository, including defaultBranch."""
    return client.get(f"/{quote(project)}/_apis/git/repositories/{quote(repository)}?api-version=7.1")
