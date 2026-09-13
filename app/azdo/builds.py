"""Build and pipeline REST queries."""

from __future__ import annotations

import urllib.parse
from typing import Any

from app.azdo.client import AzureDevOpsClient


def quote(value: str) -> str:
    return urllib.parse.quote(value, safe="")


def latest_build(client: AzureDevOpsClient, project: str, definition_id: int, branch: str | None = None) -> dict[str, Any] | None:
    query = {"definitions": definition_id, "$top": 1, "queryOrder": "finishTimeDescending", "api-version": "7.1"}
    if branch:
        query["branchName"] = branch
    response = client.get(f"/{quote(project)}/_apis/build/builds?{urllib.parse.urlencode(query)}")
    builds = response.get("value", [])
    return builds[0] if builds else None


def execution_pool_name(build: dict[str, Any]) -> str:
    """Return the pool recorded for this build, never a configured default."""
    queue = build.get("queue")
    if not isinstance(queue, dict):
        return "Unknown"
    pool = queue.get("pool")
    if isinstance(pool, dict) and pool.get("name"):
        return str(pool["name"])
    if queue.get("name"):
        return str(queue["name"])
    return "Unknown"
