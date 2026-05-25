"""Local web server for AppCompilerAI.

Run:
    python3 server.py
"""

from __future__ import annotations

import json
import mimetypes
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from app.bundler import zip_runtime_bundle
from app.evaluation import evaluate
from app.modes import COMPILER_MODES, normalize_mode
from app.pipeline import compile_prompt
from app.utils import slugify

ROOT = Path(__file__).resolve().parent
WEB_ROOT = ROOT / "web"


class AppCompilerHandler(BaseHTTPRequestHandler):
    server_version = "AppCompilerAI/1.0"

    def _send_json(self, payload, status=200):
        body = json.dumps(payload, indent=2, sort_keys=True).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def _send_file(self, path: Path):
        if not path.exists() or not path.is_file():
            self._send_json({"error": "not_found"}, 404)
            return
        content = path.read_bytes()
        content_type = mimetypes.guess_type(str(path))[0] or "application/octet-stream"
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def _send_bytes(self, content: bytes, content_type: str, filename: str):
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(content)

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.end_headers()

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/api/health":
            self._send_json({"ok": True, "service": "AppCompilerAI"})
            return
        if path == "/api/modes":
            self._send_json({"modes": COMPILER_MODES, "default": "balanced"})
            return
        if path == "/api/evaluate":
            query = parse_qs(urlparse(self.path).query)
            mode = normalize_mode((query.get("mode") or ["balanced"])[0])
            self._send_json(evaluate(mode=mode))
            return
        if path in ["/", "/index.html"]:
            self._send_file(WEB_ROOT / "index.html")
            return
        static_path = (WEB_ROOT / path.lstrip("/")).resolve()
        if str(static_path).startswith(str(WEB_ROOT.resolve())):
            self._send_file(static_path)
            return
        self._send_json({"error": "not_found"}, 404)

    def do_POST(self):
        path = urlparse(self.path).path
        if path not in ["/api/compile", "/api/bundle", "/api/runtime-proof"]:
            self._send_json({"error": "not_found"}, 404)
            return
        length = int(self.headers.get("Content-Length", "0"))
        try:
            payload = json.loads(self.rfile.read(length).decode("utf-8") or "{}")
        except json.JSONDecodeError:
            self._send_json({"error": "invalid_json"}, 400)
            return
        prompt = payload.get("prompt", "")
        mode = normalize_mode(payload.get("mode", "balanced"))
        repair_demo_fault = bool(payload.get("repairDemoFault", False))
        if not isinstance(prompt, str) or not prompt.strip():
            self._send_json({"error": "prompt_required"}, 400)
            return
        output = compile_prompt(prompt, repair_demo_fault=repair_demo_fault, mode=mode)
        if path == "/api/runtime-proof":
            self._send_json(
                {
                    "compileId": output["compileId"],
                    "status": output["status"],
                    "mode": output["mode"],
                    "runtime": output["execution"],
                    "validation": output["validation"],
                    "score": output["score"],
                }
            )
            return
        if path == "/api/bundle":
            if output["status"] == "blocked" or not output["execution"]["ready"]:
                self._send_json(
                    {
                        "error": "runtime_not_ready",
                        "status": output["status"],
                        "validation": output["validation"],
                        "execution": output["execution"],
                    },
                    422,
                )
                return
            try:
                bundle_bytes = zip_runtime_bundle(output["config"])
            except RuntimeError as exc:
                self._send_json({"error": "bundle_generation_failed", "detail": str(exc)}, 422)
                return
            filename = f"{slugify(output['config']['app']['name'])}_runtime_bundle.zip"
            self._send_bytes(bundle_bytes, "application/zip", filename)
            return
        self._send_json(output)

    def log_message(self, fmt, *args):
        print("[%s] %s" % (self.log_date_time_string(), fmt % args))


def run(host: str | None = None, port: int | None = None):
    bind_host = host or os.environ.get("HOST", "127.0.0.1")
    bind_port = port or int(os.environ.get("PORT", "8765"))
    server = ThreadingHTTPServer((bind_host, bind_port), AppCompilerHandler)
    display_host = "127.0.0.1" if bind_host == "0.0.0.0" else bind_host
    print(f"AppCompilerAI running at http://{display_host}:{bind_port}")
    print("Press Ctrl+C to stop.")
    server.serve_forever()


if __name__ == "__main__":
    run()
