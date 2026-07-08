"""Local browser UI server for ECHO Adventure."""

from __future__ import annotations

import argparse
import json
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import urlparse

from .session import GameSession, SessionStore
from .view import INDEX_HTML, UI_DIR

STATIC_ASSETS = {
    "/ui/api.js": ("application/javascript; charset=utf-8", UI_DIR / "api.js"),
    "/ui/app.js": ("application/javascript; charset=utf-8", UI_DIR / "app.js"),
    "/ui/assets/virginia-submarine-cutout.png": ("image/png", UI_DIR / "assets" / "virginia-submarine-cutout.png"),
    "/ui/dayClock.js": ("application/javascript; charset=utf-8", UI_DIR / "dayClock.js"),
    "/ui/html.js": ("application/javascript; charset=utf-8", UI_DIR / "html.js"),
    "/ui/modals.js": ("application/javascript; charset=utf-8", UI_DIR / "modals.js"),
    "/ui/renderDecisions.js": ("application/javascript; charset=utf-8", UI_DIR / "renderDecisions.js"),
    "/ui/renderFinal.js": ("application/javascript; charset=utf-8", UI_DIR / "renderFinal.js"),
    "/ui/renderMetrics.js": ("application/javascript; charset=utf-8", UI_DIR / "renderMetrics.js"),
    "/ui/renderSummary.js": ("application/javascript; charset=utf-8", UI_DIR / "renderSummary.js"),
    "/ui/state.js": ("application/javascript; charset=utf-8", UI_DIR / "state.js"),
    "/ui/submarineVisual.js": ("application/javascript; charset=utf-8", UI_DIR / "submarineVisual.js"),
    "/ui/styles.css": ("text/css; charset=utf-8", UI_DIR / "styles.css"),
}


class GameRequestHandler(BaseHTTPRequestHandler):
    """Small JSON/HTML request handler for the local-only browser app."""

    # The dynamically-created subclass in run_ui_server attaches a SessionStore
    # here so every request handler instance shares one locked session owner.
    session_store: SessionStore

    def do_GET(self) -> None:
        """Serve the shell HTML or the current JSON state."""
        parsed = urlparse(self.path)
        if parsed.path == "/":
            self._send_html(INDEX_HTML)
        elif parsed.path == "/api/state":
            self._send_json(self.session_store.state_payload())
        elif parsed.path in STATIC_ASSETS:
            self._send_static(parsed.path)
        else:
            self._send_json({"error": "Not found"}, HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:
        """Handle state-changing UI actions."""
        parsed = urlparse(self.path)
        try:
            # This intentionally tiny API mirrors the UI's workflow:
            # create/read a run, apply decisions, then advance days.
            if parsed.path == "/api/new":
                data = self._read_json()
                self._send_json(self.session_store.new_session_payload(seed=_parse_optional_seed(data.get("seed"))))
            elif parsed.path == "/api/choice":
                data = self._read_json()
                self._send_json(
                    self.session_store.choice_payload(str(data.get("cardId", "")), str(data.get("choiceId", "")))
                )
            elif parsed.path == "/api/shift":
                self._send_json(self.session_store.shift_payload())
            elif parsed.path == "/api/advance":
                self._send_json(self.session_store.advance_payload())
            else:
                self._send_json({"error": "Not found"}, HTTPStatus.NOT_FOUND)
        except ValueError as exc:
            self._send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
        except Exception as exc:  # pragma: no cover - defensive local server path
            self._send_json({"error": f"Server error: {exc}"}, HTTPStatus.INTERNAL_SERVER_ERROR)

    def log_message(self, format: str, *args: Any) -> None:
        # Suppress noisy per-request logs; the UI is local and stateful, and
        # request spam makes terminal output harder to use while developing.
        return

    def _read_json(self) -> dict[str, Any]:
        """Read a JSON request body, treating empty bodies as empty objects."""
        length = int(self.headers.get("content-length", "0"))
        if length == 0:
            return {}
        raw = self.rfile.read(length)
        return json.loads(raw.decode("utf-8"))

    def _send_json(self, payload: dict[str, Any], status: HTTPStatus = HTTPStatus.OK) -> None:
        """Serialize and send a JSON response with explicit length headers."""
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("content-type", "application/json; charset=utf-8")
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_html(self, html: str) -> None:
        """Send the inline HTML shell."""
        body = html.encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("content-type", "text/html; charset=utf-8")
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_static(self, path: str) -> None:
        """Send a known static browser asset."""
        content_type, asset_path = STATIC_ASSETS[path]
        body = asset_path.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("content-type", content_type)
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def run_ui_server(seed: int | None = None, host: str = "127.0.0.1", port: int = 8765) -> None:
    """Start the local browser UI server."""
    # A fresh handler subclass lets us attach a mutable class-level session owner
    # without modifying BaseHTTPRequestHandler itself.
    handler = type("SessionHandler", (GameRequestHandler,), {})
    handler.session_store = SessionStore(seed=seed)
    server = ThreadingHTTPServer((host, port), handler)
    url = f"http://{host}:{port}"
    print(f"ECHO Adventure UI running at {url} (normal mode)")
    print("Press Ctrl+C to stop.")
    try:
        server.serve_forever()
    finally:
        server.server_close()


def main(argv: list[str] | None = None) -> None:
    """CLI entry point for running only the browser UI server."""
    parser = argparse.ArgumentParser(description="Run the local ECHO Adventure browser UI.")
    parser.add_argument("--seed", type=int, help="Run a reproducible scenario seed.")
    parser.add_argument("--host", default="127.0.0.1", help="Host for the local UI server.")
    parser.add_argument("--port", type=int, default=8765, help="Port for the local UI server.")
    args = parser.parse_args(argv)
    run_ui_server(seed=args.seed, host=args.host, port=args.port)


def _parse_optional_seed(value: Any) -> int | None:
    """Return an integer seed from a JSON value, or None for a random run."""
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("Seed must be an integer.") from exc


__all__ = ["GameSession", "SessionStore", "STATIC_ASSETS", "main", "run_ui_server"]
