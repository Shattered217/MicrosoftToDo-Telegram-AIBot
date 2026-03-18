"""HTTP API handler for ESP32 bridge.

Endpoints:
  GET  /api/snapshot?device_id=<id>&limit=<n>
  POST /api/cmd  {op, task_id, list_id, completed}
  GET  /healthz
"""

from __future__ import annotations

import json
import logging
import time
from http.server import BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

from .snapshot import build_snapshot, execute_command

logger = logging.getLogger(__name__)


class BridgeHTTPHandler(BaseHTTPRequestHandler):
    """Lightweight HTTP handler for ESP32 device communication."""

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/")
        params = parse_qs(parsed.query)

        if path == "/healthz":
            self._json_response(200, {"status": "ok"})
            return

        if path == "/api/snapshot":
            start = time.perf_counter()
            device_id = params.get("device_id", ["esp32-1"])[0]
            limit = int(params.get("limit", ["6"])[0])
            snapshot = build_snapshot(device_id=device_id, limit=limit)
            cost_ms = int((time.perf_counter() - start) * 1000)
            logger.info("/api/snapshot served in %dms for %s", cost_ms, device_id)
            self._json_response(200, snapshot.to_dict())
            return

        self._json_response(404, {"error": "not found"})

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/")

        if path == "/api/cmd":
            try:
                length = int(self.headers.get("Content-Length", 0))
                raw = self.rfile.read(length) if length > 0 else b"{}"
                body = json.loads(raw.decode("utf-8"))
            except (json.JSONDecodeError, ValueError) as e:
                self._json_response(400, {"error": f"invalid JSON: {e}"})
                return

            op = body.get("op", "")
            task_id = body.get("task_id", "")
            list_id = body.get("list_id")
            completed = body.get("completed")

            if not op:
                self._json_response(400, {"error": "missing 'op'"})
                return

            if op == "set_completed":
                if not isinstance(completed, bool):
                    self._json_response(
                        400,
                        {"error": "missing or invalid 'completed' for set_completed"},
                    )
                    return
                op = "complete" if completed else "update"

            if op == "complete" and not task_id:
                self._json_response(400, {"error": "missing 'task_id' for complete"})
                return

            if op == "update" and not task_id:
                self._json_response(400, {"error": "missing 'task_id' for update"})
                return

            if op == "create" and not body.get("title"):
                self._json_response(400, {"error": "missing 'title' for create"})
                return

            try:
                # Build kwargs from body, excluding already handled parameters
                kwargs = {
                    k: v
                    for k, v in body.items()
                    if k not in ["op", "task_id", "list_id", "completed"]
                }
                if op == "update" and completed is False and "status" not in kwargs:
                    kwargs["status"] = "notStarted"
                result = execute_command(
                    op=op, task_id=task_id, list_id=list_id, **kwargs
                )
                self._json_response(200, {"success": True, "data": result})
            except Exception as e:
                logger.exception("Command failed: %s", e)
                self._json_response(500, {"success": False, "error": str(e)})
            return

        self._json_response(404, {"error": "not found"})

    def _json_response(self, code: int, data: dict) -> None:
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self) -> None:
        """Handle CORS preflight."""
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def log_message(self, format: str, *args) -> None:
        logger.info(format, *args)
