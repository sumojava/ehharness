#!/usr/bin/env python3
"""Local harness settings server.

Runs only on 127.0.0.1. Stores API keys in the OS keychain via the `keyring`
package. The browser can save, check, and delete keys, but nothing ever sends a
key value back to the browser: the UI only sees "saved" or "not saved".
"""
import json
import os
import urllib.error
import urllib.request
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


# A cheap, read-only call per provider: list available models. It costs nothing
# meaningful and confirms the key works. The key goes in a header, never the URL,
# so it can't end up in proxy or server logs.
TEST_REQUESTS = {
    "anthropic": (
        "https://api.anthropic.com/v1/models",
        lambda key: {"x-api-key": key, "anthropic-version": "2023-06-01"},
    ),
    "openai": (
        "https://api.openai.com/v1/models",
        lambda key: {"Authorization": f"Bearer {key}"},
    ),
    "gemini": (
        "https://generativelanguage.googleapis.com/v1beta/models",
        lambda key: {"x-goog-api-key": key},
    ),
}


# Chat models the harness will send to. Only these IDs are allowed, so a
# request can't point the app at an arbitrary model string.
CLAUDE_MODELS = ["claude-haiku-5-5", "claude-sonnet-5-5", "claude-opus-5-5"]
MAX_MESSAGES = 50
MAX_MESSAGE_CHARS = 20_000
MAX_REPLY_TOKENS = 2048


def validate_chat(body):
    """Return (model, messages) or raise ValueError with a safe message."""
    model = body.get("model")
    if model not in CLAUDE_MODELS:
        raise ValueError("unknown model")
    raw = body.get("messages")
    if not isinstance(raw, list) or not raw or len(raw) > MAX_MESSAGES:
        raise ValueError("send between 1 and 50 messages")
    messages = []
    for m in raw:
        role = m.get("role") if isinstance(m, dict) else None
        content = m.get("content") if isinstance(m, dict) else None
        if role not in ("user", "assistant") or not isinstance(content, str):
            raise ValueError("each message needs a role and text")
        if not content.strip() or len(content) > MAX_MESSAGE_CHARS:
            raise ValueError("message is empty or too long")
        messages.append({"role": role, "content": content})
    if messages[-1]["role"] != "user":
        raise ValueError("the last message must be from you")
    return model, messages


def call_claude(key, model, messages):
    """Send a chat request to Anthropic. Returns dict with text and usage."""
    payload = json.dumps(
        {"model": model, "max_tokens": MAX_REPLY_TOKENS, "messages": messages}
    ).encode("utf-8")
    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=payload,
        headers={
            "x-api-key": key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read())
    except urllib.error.HTTPError as err:
        if err.code in (401, 403):
            raise RuntimeError("Claude rejected the key. Test it on the settings page.")
        if err.code == 429:
            raise RuntimeError("Claude rate limit reached. Try again shortly.")
        raise RuntimeError(f"Claude returned an error (HTTP {err.code}).")
    except (urllib.error.URLError, TimeoutError):
        raise RuntimeError("Could not reach Claude. Check your connection.")

    text = "".join(
        block.get("text", "") for block in data.get("content", []) if block.get("type") == "text"
    )
    usage = data.get("usage", {})
    return {
        "text": text,
        "usage": {
            "input_tokens": usage.get("input_tokens", 0),
            "output_tokens": usage.get("output_tokens", 0),
        },
        "model": model,
    }


def test_provider(provider_id, key):
    """Return (ok, message). Never includes the key in the message."""
    url, make_headers = TEST_REQUESTS[provider_id]
    req = urllib.request.Request(url, headers=make_headers(key), method="GET")
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return True, "Working"
    except urllib.error.HTTPError as err:
        if err.code in (401, 403):
            return False, "Key was rejected. Check that it's the right key for this provider."
        return False, f"Provider returned an error (HTTP {err.code})."
    except (urllib.error.URLError, TimeoutError):
        return False, "Could not reach the provider. Check your internet connection."


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
        if self.path == "/chat":
            return self._send_file(STATIC_DIR / "chat.html", "text/html; charset=utf-8")
        if self.path == "/style.css":
            return self._send_file(STATIC_DIR / "style.css", "text/css; charset=utf-8")
        if self.path == "/chat.js":
            return self._send_file(STATIC_DIR / "chat.js", "application/javascript")
        if self.path == "/api/models":
            return self._send_json(200, {"claude": CLAUDE_MODELS})
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

        if self.path == "/api/chat":
            if body.get("provider") != "anthropic":
                return self._send_json(400, {"error": "chat is only set up for Claude right now"})
            key = get_key(provider["alias"])
            if key is None:
                return self._send_json(400, {"error": "Save a Claude key on the settings page first."})
            try:
                model, messages = validate_chat(body)
                result = call_claude(key, model, messages)
            except ValueError as err:
                return self._send_json(400, {"error": str(err)})
            except RuntimeError as err:
                return self._send_json(502, {"error": str(err)})
            return self._send_json(200, result)

        if self.path == "/api/test":
            key = get_key(provider["alias"])
            if key is None:
                return self._send_json(200, {"ok": False, "message": "No key saved yet."})
            ok, message = test_provider(body.get("provider"), key)
            return self._send_json(200, {"ok": ok, "message": message})

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
