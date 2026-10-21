#!/usr/bin/env python3
"""Local harness settings server.

Runs only on 127.0.0.1. Stores API keys in the OS keychain via the `keyring`
package. The browser can save, check, and delete keys, but nothing ever sends a
key value back to the browser: the UI only sees "saved" or "not saved".
"""
import json
import os
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import keyring

SERVICE = "harness"
HOST = "127.0.0.1"
PORT = 8765
STATIC_DIR = Path(__file__).parent / "static"

# Providers the settings page knows about. The alias is what the rest of the
# harness uses; the key value never leaves the keychain except to call the API.
PROVIDERS = {
    "anthropic": {"label": "Claude (Anthropic API)", "alias": "anthropic-main"},
    "openai": {"label": "ChatGPT (OpenAI API)", "alias": "openai-main"},
    "gemini": {"label": "Gemini (Google AI API)", "alias": "gemini-main"},
}


def get_key(alias):
    return keyring.get_password(SERVICE, alias)


class Handler(BaseHTTPRequestHandler):
    def _send_json(self, status, payload):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def _send_file(self, path, content_type):
        data = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; style-src 'self'; script-src 'self'",
        )
        self.end_headers()
        self.wfile.write(data)

    def _read_json(self):
        length = int(self.headers.get("Content-Length", 0))
        if length > 10_000:
            raise ValueError("request too large")
        return json.loads(self.rfile.read(length) or b"{}")

    def _check_origin(self):
        # Reject cross-site requests so a random web page can't change keys.
        origin = self.headers.get("Origin")
        allowed = {f"http://{HOST}:{PORT}", f"http://localhost:{PORT}"}
        return origin is None or origin in allowed

    def do_GET(self):
        if self.path == "/":
            return self._send_file(STATIC_DIR / "index.html", "text/html; charset=utf-8")
        if self.path == "/app.js":
            return self._send_file(STATIC_DIR / "app.js", "application/javascript")
        if self.path == "/api/providers":
            status = {
                pid: {"label": p["label"], "saved": get_key(p["alias"]) is not None}
                for pid, p in PROVIDERS.items()
            }
            return self._send_json(200, status)
        self._send_json(404, {"error": "not found"})

    def do_POST(self):
        if not self._check_origin():
            return self._send_json(403, {"error": "bad origin"})
        try:
            body = self._read_json()
        except (ValueError, json.JSONDecodeError):
            return self._send_json(400, {"error": "bad request"})

        provider = PROVIDERS.get(body.get("provider"))
        if provider is None:
            return self._send_json(400, {"error": "unknown provider"})

        if self.path == "/api/key":
            key = str(body.get("key", "")).strip()
            if len(key) < 8 or len(key) > 512 or any(c.isspace() for c in key):
                return self._send_json(400, {"error": "that doesn't look like a key"})
            keyring.set_password(SERVICE, provider["alias"], key)
            return self._send_json(200, {"saved": True})

        if self.path == "/api/key/delete":
            try:
                keyring.delete_password(SERVICE, provider["alias"])
            except keyring.errors.PasswordDeleteError:
                pass
            return self._send_json(200, {"saved": False})

        self._send_json(404, {"error": "not found"})

    def log_message(self, fmt, *args):
        # Keep request logs free of request bodies; only log method and path.
        print(f"{self.command} {self.path} -> {args[1] if len(args) > 1 else ''}")


def main():
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    url = f"http://{HOST}:{PORT}"
    print(f"Harness settings running at {url}")
    if os.environ.get("HARNESS_NO_BROWSER") != "1":
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")


if __name__ == "__main__":
    main()
