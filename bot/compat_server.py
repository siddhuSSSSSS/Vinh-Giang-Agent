"""OpenAI-compatible bridge (Phase 6.b - "OpenCode compatibility", Option B).

Exposes a minimal OpenAI Chat-Completions-shaped HTTP surface directly on top
of the existing bot engine, so OpenCode can treat Vin's Sidekick as a
provider: in opencode.json you point an @ai-sdk/openai-compatible provider at
http://<host>:4096/v1 and chat with our coach from OpenCode's TUI.

Endpoints
---------
GET  /v1/models                 -> the two configured models
POST /v1/chat/completions       -> last user message -> agent_core.handle_incoming

Contract details (why it really works, verified against the source):
- OpenCode's @ai-sdk/openai-compatible adapter sends standard chat completions
  shapes: {"messages":[...]} with the newest turn being role=user. We take the
  last user message only - our agent is turn-based (one text => one reply),
  which is exactly what OpenCode's single-prompt mode needs.
- The stream field is ignored (OpenCode sends stream:false for one-shots; if a
  client sends stream:true we answer non-streamed anyway - documented missing
  feature, not an error).
- usage is a real stub (0/0/0) because OpenCode only surfaces it in its own
  UI, never bills against it.

Security model (matches the Telegram gate exactly)
--------------------------------------------------
- Bearer token MUST equal DEMO_PASSCODE. Wrong/missing token => 401 shaped like
  an OpenAI error.
- Each Bearer-token identity maps to its own user row (platform="opencode"),
  with the SAME repo/gates/24h/weekly-reeval machinery as Telegram users. No
  cross-talk between opencode sessions and telegram users.
- Passcode gating deliberately bypassed here: the Bearer token IS the
  passcode. (Same gate, different door.)

Privacy: request bodies are never logged. Method + path only.

This module does NOT block polling: ThreadingHTTPServer runs in one daemon
thread with daemon_threads=True so shutdown never hangs the bot process.
"""

from __future__ import annotations

import asyncio
import json
import logging
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from bot import config
from bot.agent_core import AgentCore

logger = logging.getLogger(__name__)

DEFAULT_PORT = config.COMPAT_SERVER_PORT  # 4096 to match opencode's habit


def build_from_agentcore(agentcore: AgentCore) -> type[BaseHTTPRequestHandler]:
    """Build a request-handler class bound to a live AgentCore instance."""

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
            logger.info("compat %s %s", self.command, self.path.split("?")[0])

        # -- helpers ------------------------------------------------------
        def _token(self) -> str:
            auth = self.headers.get("Authorization", "")
            if auth.startswith("Bearer "):
                return auth[7:].strip()
            return ""

        def _check_auth(self) -> bool:
            token = self._token()
            if token and token == config.DEMO_PASSCODE:
                return True
            body = json.dumps(
                {"error": {"message": "Invalid bearer token.", "code": 401}}
            ).encode()
            self.send_response(401)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return False

        def _send_json(self, payload: dict[str, Any], status: int) -> None:
            blob = json.dumps(payload).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(blob)))
            self.end_headers()
            self.wfile.write(blob)

        # -- routes -------------------------------------------------------
        def do_GET(self) -> None:  # noqa: N802
            if self.path.rstrip("/") not in ("/v1/models", "/models"):
                self._send_json(
                    {"error": {"message": f"no route for {self.path}", "code": 404}},
                    404,
                )
                return
            if not self._check_auth():
                return
            self._send_json(
                {
                    "object": "list",
                    "data": [
                        {
                            "id": config.OPENAI_MODEL,
                            "object": "model",
                            "owned_by": "vins-sidekick",
                        },
                        {
                            "id": config.OPENAI_MODEL_ANALYSIS,
                            "object": "model",
                            "owned_by": "vins-sidekick",
                        },
                    ],
                },
                200,
            )

        def do_POST(self) -> None:  # noqa: N802
            if self.path.rstrip("/") != "/v1/chat/completions":
                self._send_json(
                    {"error": {"message": f"no route for {self.path}", "code": 404}},
                    404,
                )
                return
            if not self._check_auth():
                return

            length = int(self.headers.get("Content-Length", 0) or 0)
            if length <= 0 or length > 2_000_000:
                self._send_json(
                    {"error": {"message": "bad or too-large body", "code": 413}}, 413
                )
                return
            try:
                payload = json.loads(self.rfile.read(length).decode("utf-8", "replace"))
                messages: list[dict[str, Any]] = payload.get("messages") or []
            except Exception:  # noqa: BLE001
                self._send_json(
                    {"error": {"message": "malformed JSON", "code": 400}}, 400
                )
                return

            text = extract_last_user_text(messages)
            if not text:
                self._send_json(
                    {"error": {"message": "no user message", "code": 400}}, 400
                )
                return

            # one opencode-bearer == one user row (platform="opencode"), so
            # state/stage journaling stays per-identity and isolated.
            outcome = asyncio.run(
                agentcore.handle_incoming("opencode", "bearer:default", text)
            )
            if outcome.error_reply:
                # agent hit a snag OR a gate blocked - surface as 502 with the
                # graceful line, OpenCode shows it as an error, user keeps a clue
                self._send_json(
                    {
                        "error": {
                            "message": outcome.reply,
                            "code": 502,
                            "type": "agent_unavailable",
                        }
                    },
                    502,
                )
                return

            self._send_json(
                {
                    "id": "chatcmpl-vins-sidekick",
                    "object": "chat.completion",
                    "created": 0,
                    "model": payload.get("model") or config.OPENAI_MODEL,
                    "choices": [
                        {
                            "index": 0,
                            "finish_reason": "stop",
                            "message": {"role": "assistant", "content": outcome.reply},
                        }
                    ],
                    "usage": {
                        "prompt_tokens": 0,
                        "completion_tokens": 0,
                        "total_tokens": 0,
                    },
                },
                200,
            )

    return Handler


def extract_last_user_text(messages: list[dict[str, Any]]) -> str:
    """The last user-role message's text content; multimodal-safe."""
    for m in reversed(messages):
        if not isinstance(m, dict) or m.get("role") != "user":
            continue
        content = m.get("content", "")
        if isinstance(content, list):
            parts = [
                p.get("text", "")
                for p in content
                if isinstance(p, dict) and p.get("type") == "text"
            ]
            return "\n".join(p for p in parts if p).strip()
        if isinstance(content, str):
            return content.strip()
    return ""


def start_compat_server(
    agentcore: AgentCore,
    bind: str = "127.0.0.1",
    port: int | None = None,
) -> ThreadingHTTPServer:
    """Serve the OpenAI-compat API on a daemon thread; returns the server."""
    handler_cls = build_from_agentcore(agentcore)
    # NB: `port or DEFAULT_PORT` would send an explicit ephemeral 0 to the
    # default (falsy), breaking port=0 callers - bind exactly what's given.
    bind_port = DEFAULT_PORT if port is None else port
    server = ThreadingHTTPServer((bind, bind_port), handler_cls)
    server.daemon_threads = True
    thread = threading.Thread(
        target=server.serve_forever, name="vins-opencode-compat", daemon=True
    )
    thread.start()
    logger.info(
        "opencode compat server on http://%s:%s/v1 (GET /models, POST /chat/completions)",
        bind,
        server.server_address[1],
    )
    return server

