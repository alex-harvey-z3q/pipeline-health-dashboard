"""Small Azure DevOps REST client with no browser-visible credentials."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any

from app.azdo.auth import TokenProvider


class AzureDevOpsError(RuntimeError):
    pass


class AzureDevOpsClient:
    def __init__(self, organization_url: str, token_provider: TokenProvider) -> None:
        self.organization_url = organization_url.rstrip("/")
        self.token_provider = token_provider

    def get(self, path: str) -> dict[str, Any]:
        request = urllib.request.Request(
            self.organization_url + path,
            headers={"Accept": "application/json", "Authorization": self.token_provider.authorization_header()},
        )
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                return json.loads(response.read())
        except urllib.error.HTTPError as error:
            detail = error.read().decode("utf-8", errors="replace").strip()
            raise AzureDevOpsError(f"GET {request.full_url} failed with {error.code}: {detail}") from error
