#!/usr/bin/env python3
"""No-think proxy for vLLM-served Anthropic-compatible endpoints.

vLLM's /v1/messages adapter IGNORES the standard Anthropic `thinking`
parameter (verified: `{"type":"disabled"}` and tiny budgets both still
produced thousands of reasoning characters) — but it HONORS a top-level
vLLM-native field:

    "chat_template_kwargs": {"enable_thinking": false}

which drops single-turn latency from ~13s to ~0.2s on a Qwen3-class model
and eliminates runaway-reasoning stalls. This proxy forwards Anthropic-
format requests verbatim, injecting only that field, so any client that
speaks ANTHROPIC_BASE_URL (including the Claude Code CLI, tools and
streaming intact) gets thinking-free generation with no server changes.

Usage:
    NOTHINK_UPSTREAM=https://your-vllm-host \\
    NOTHINK_CA=/path/to/rootCA.pem \\        # optional, for private TLS
    python3 nothink_proxy.py [port]          # default 8399

    then: export ANTHROPIC_BASE_URL=http://127.0.0.1:8399
"""

import json
import os
import ssl
import sys
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

UPSTREAM = os.environ.get("NOTHINK_UPSTREAM", "https://vllm.i-bora.com")
CA = os.environ.get("NOTHINK_CA")
CTX = ssl.create_default_context(cafile=CA) if CA else \
    ssl.create_default_context()

HOP = {"connection", "keep-alive", "transfer-encoding", "host",
       "content-length", "accept-encoding"}


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):
        sys.stderr.write("[nothink] " + fmt % args + "\n")

    def _forward(self, body=None):
        req = urllib.request.Request(
            UPSTREAM + self.path, data=body, method=self.command,
            headers={k: v for k, v in self.headers.items()
                     if k.lower() not in HOP})
        try:
            resp = urllib.request.urlopen(req, timeout=900, context=CTX)
        except urllib.error.HTTPError as e:
            resp = e
        self.send_response(getattr(resp, "status", None) or resp.code)
        for k, v in resp.headers.items():
            if k.lower() not in HOP:
                self.send_header(k, v)
        self.send_header("Connection", "close")
        self.end_headers()
        try:
            while True:
                chunk = resp.read(8192)
                if not chunk:
                    break
                self.wfile.write(chunk)
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            pass

    def do_GET(self):
        self._forward()

    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(n) if n else b""
        if "/v1/messages" in self.path:
            try:
                data = json.loads(body)
                data["chat_template_kwargs"] = {"enable_thinking": False}
                body = json.dumps(data).encode()
            except json.JSONDecodeError:
                pass  # forward untouched rather than break the stream
        self._forward(body)


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8399
    print(f"[nothink] 127.0.0.1:{port} -> {UPSTREAM} "
          f"(enable_thinking=false on /v1/messages)", flush=True)
    ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()
