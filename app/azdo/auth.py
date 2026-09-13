"""Server-side authentication providers."""

from __future__ import annotations

import base64
import os
from typing import Protocol


class TokenProvider(Protocol):
    def authorization_header(self) -> str: ...


class PATTokenProvider:
    def __init__(self, token: str) -> None:
        self.token = token

    def authorization_header(self) -> str:
        encoded = base64.b64encode(f":{self.token}".encode("utf-8")).decode("ascii")
        return f"Basic {encoded}"


class EntraTokenProvider:
    """Extension point for workload identity token acquisition when configured."""

    def authorization_header(self) -> str:
        raise RuntimeError("Entra workload identity is not configured yet. Set AZDO_PAT for the current MVP.")


def token_provider_from_environment() -> TokenProvider:
    token = os.environ.get("AZDO_PAT") or os.environ.get("AZDO_PERSONAL_ACCESS_TOKEN")
    if token:
        return PATTokenProvider(token)
    if os.environ.get("AZDO_AUTH_MODE") == "entra":
        return EntraTokenProvider()
    raise RuntimeError("Set AZDO_PAT or AZDO_PERSONAL_ACCESS_TOKEN before starting the dashboard.")
