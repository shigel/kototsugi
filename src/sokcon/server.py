from __future__ import annotations

import json
import time
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Callable, Dict, Iterator
from urllib.parse import parse_qs, unquote, urlparse

JSON_FILES = {
    "/state": "state_snapshot.json",
    "/events": "transcript_events.json",
    "/actions": "action_queue.json",
    "/privacy": "privacy_manifest.json",
    "/traceability": "requirements_traceability.json",
}


def build_dashboard_handler(artifact_dir: Path) -> type[BaseHTTPRequestHandler]:
    root = artifact_dir.resolve()

    class DashboardHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            parsed = urlparse(self.path)
            if parsed.path == "/":
                self.serve_file(root / "dashboard.html", "text/html; charset=utf-8")
                return
            if parsed.path == "/stream":
                once = parse_qs(parsed.query).get("once") == ["1"]
                self.serve_stream(root, once=once)
                return
            if parsed.path in JSON_FILES:
                self.serve_file(root / JSON_FILES[parsed.path], "application/json")
                return
            if parsed.path.startswith("/artifacts/"):
                relative = unquote(parsed.path.removeprefix("/artifacts/"))
                self.serve_artifact(relative)
                return
            self.send_error(HTTPStatus.NOT_FOUND, "Unknown dashboard route")

        def serve_artifact(self, relative: str) -> None:
            target = resolve_artifact_path(root, relative)
            if target is None:
                self.send_error(HTTPStatus.FORBIDDEN, "Path is outside artifact directory")
                return
            self.serve_file(target, guess_content_type(target))

        def serve_file(self, path: Path, content_type: str) -> None:
            if not path.exists() or not path.is_file():
                self.send_error(HTTPStatus.NOT_FOUND, f"Missing artifact: {path.name}")
                return
            body = path.read_bytes()
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def serve_stream(self, artifact_root: Path, once: bool = False) -> None:
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "text/event-stream; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Connection", "keep-alive")
            self.end_headers()
            for event in watch_sse_events(artifact_root, once=once):
                try:
                    self.wfile.write(event.encode("utf-8"))
                    self.wfile.flush()
                except BrokenPipeError:
                    break

        def log_message(self, format: str, *args: object) -> None:
            return

    return DashboardHandler


def guess_content_type(path: Path) -> str:
    if path.suffix == ".html":
        return "text/html; charset=utf-8"
    if path.suffix == ".json":
        return "application/json"
    if path.suffix == ".md":
        return "text/markdown; charset=utf-8"
    return "application/octet-stream"


def resolve_artifact_path(root: Path, relative: str) -> Path | None:
    resolved_root = root.resolve()
    target = (resolved_root / relative).resolve()
    if resolved_root not in target.parents and target != resolved_root:
        return None
    return target


def build_sse_snapshot(artifact_dir: Path) -> str:
    payload = {
        "state": read_json_if_exists(artifact_dir / "state_snapshot.json"),
        "actions": read_json_if_exists(artifact_dir / "action_queue.json"),
        "traceability": read_json_if_exists(artifact_dir / "requirements_traceability.json"),
    }
    return "event: snapshot\n" f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


def watch_sse_events(
    artifact_dir: Path,
    *,
    once: bool = False,
    poll_interval: float = 1.0,
) -> Iterator[str]:
    last_fingerprint: Dict[str, int] | None = None
    while True:
        fingerprint = artifact_fingerprint(artifact_dir)
        if fingerprint != last_fingerprint:
            yield build_sse_snapshot(artifact_dir)
            last_fingerprint = fingerprint
        if once:
            return
        time.sleep(poll_interval)


def artifact_fingerprint(artifact_dir: Path) -> Dict[str, int]:
    watched = [
        "state_snapshot.json",
        "action_queue.json",
        "requirements_traceability.json",
        "transcript_events.json",
    ]
    fingerprint: Dict[str, int] = {}
    for name in watched:
        path = artifact_dir / name
        fingerprint[name] = path.stat().st_mtime_ns if path.exists() else 0
    return fingerprint


def read_json_if_exists(path: Path) -> object:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def create_dashboard_server(
    artifact_dir: Path,
    host: str = "127.0.0.1",
    port: int = 8765,
) -> ThreadingHTTPServer:
    handler = build_dashboard_handler(artifact_dir)
    return ThreadingHTTPServer((host, port), handler)


def serve_dashboard(
    artifact_dir: Path,
    host: str = "127.0.0.1",
    port: int = 8765,
    announce: Callable[[str], None] | None = None,
) -> None:
    server = create_dashboard_server(artifact_dir, host, port)
    if announce is not None:
        announce(json.dumps({"url": f"http://{host}:{server.server_port}/"}))
    try:
        server.serve_forever()
    finally:
        server.server_close()
