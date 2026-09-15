"""HTTP server for the Pipeline Health Dashboard."""

from __future__ import annotations

import argparse
import json
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from app.azdo.auth import token_provider_from_environment
from app.azdo.client import AzureDevOpsClient
from app.config import DashboardConfig, load_config
from app.service import collect_dashboard


STATIC_DIR = Path(__file__).parent / "static"


class DashboardHandler(SimpleHTTPRequestHandler):
    config: DashboardConfig

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, directory=str(STATIC_DIR), **kwargs)

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/healthz":
            self._send_json(HTTPStatus.OK, {"status": "ok"})
        elif self.path == "/readyz":
            self._send_json(HTTPStatus.OK, {"status": "ready"})
        elif self.path == "/api/dashboard":
            self._dashboard()
        else:
            super().do_GET()

    def _dashboard(self) -> None:
        try:
            client = AzureDevOpsClient(self.config.organization_url, token_provider_from_environment())
            payload = collect_dashboard(self.config, client)
        except Exception as error:
            try:
                self._send_json(HTTPStatus.BAD_GATEWAY, {"error": str(error)})
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                pass
            return
        try:
            self._send_json(HTTPStatus.OK, payload)
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            return

    def _send_json(self, status: HTTPStatus, payload: dict[str, Any]) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=Path("config.yml"))
    parser.add_argument("--host", default="127.0.0.1", help="Use 0.0.0.0 only behind an authenticated network boundary.")
    parser.add_argument("--port", type=int, default=8080)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config = load_config(args.config)
    handler = type("ConfiguredDashboardHandler", (DashboardHandler,), {"config": config})
    server = ThreadingHTTPServer((args.host, args.port), handler)
    print(f"Pipeline Health Dashboard: http://{args.host}:{args.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nDashboard stopped.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
