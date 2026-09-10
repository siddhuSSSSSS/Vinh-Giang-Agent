"""Phase 6.b tests - the OpenAI-compatible bridge for OpenCode (Option B).

Real HTTP tests over a live ThreadingHTTPServer wired to a FAKE AgentCore, so
no OpenAI key / network is needed to exercise status codes and shapes.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request

import pytest

from bot import compat_server
from bot.agent_core import TurnOutcome
from bot.compat_server import extract_last_user_text, start_compat_server


# ---------------------------------------------------------------------------
# Fake AgentCore - exactly the surface the bridge touches
# ---------------------------------------------------------------------------
class FakeAgentCore:
    def __init__(self, reply: str = "Nice take - let's sharpen it.", error: bool = False):
        self.reply = reply
        self.error = error
        self.calls: list[tuple[str, str, str]] = []

    async def handle_incoming(self, platform: str, platform_user_id: str, text: str):
        self.calls.append((platform, platform_user_id, text))
        return TurnOutcome(
            reply=self.reply, model_used="gpt-5.6-luna",
            reasoning_effort="none", tool_calls_made=[], error_reply=self.error,
        )


@pytest.fixture()
def server_port(monkeypatch):
    """Start the bridge on an ephemeral port bound to 127.0.0.1; shut it down.

    Every test gets a FRESH server AND a pinned-session DEMO_PASSCODE, so no
    test can see another's server or passcode state (two bugs seen earlier in
    this file's history: leaked servers + passcode leaking via .env reload).
    """
    monkeypatch.setattr(compat_server.config, "DEMO_PASSCODE", PASS)
    agent = FakeAgentCore()
    srv = start_compat_server(agent, bind="127.0.0.1", port=0)  # port=0 => OS picks
    port = srv.server_address[1]
    yield port, agent
    srv.shutdown()
    srv.server_close()


def _post(port: int, path: str, body: dict, token: str | None) -> tuple[int, dict]:
    headers: dict[str, str] = {"Content-Type": "application/json"}
    if token is not None:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(
        f"http://127.0.0.1:{port}{path}",
        data=json.dumps(body).encode(),
        headers=headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            return resp.status, json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode())


def _get(port: int, path: str, token: str | None) -> tuple[int, dict]:
    req = urllib.request.Request(f"http://127.0.0.1:{port}{path}")
    if token is not None:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            return resp.status, json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode())


PASS = "karwaan"


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------
class TestExtractLastUserText:
    def test_single_user_message(self):
        assert extract_last_user_text([{"role": "user", "content": "hi"}]) == "hi"

    def test_takes_last_user_even_after_assistant(self):
        msgs = [
            {"role": "user", "content": "first"},
            {"role": "assistant", "content": "mid"},
            {"role": "user", "content": "second"},
        ]
        assert extract_last_user_text(msgs) == "second"

    def test_multimodal_content_list(self):
        msgs = [{"role": "user", "content": [
            {"type": "text", "text": "look:"},
            {"type": "image_url", "image_url": {"url": "data:..."}},
        ]}]
        assert extract_last_user_text(msgs) == "look:"

    def test_no_user_message_returns_empty(self):
        assert extract_last_user_text([{"role": "system", "content": "set-up"}]) == ""

    def test_non_dict_entries_ignored(self):
        assert extract_last_user_text(["junk", 5]) == ""  # type: ignore[list-item]


class TestBridgeAuth:
    def test_missing_bearer_is_401(self, server_port):
        port, _ = server_port
        status, body = _post(port, "/v1/chat/completions", {"messages": []}, None)
        assert status == 401
        assert body["error"]["code"] == 401

    def test_wrong_bearer_is_401(self, server_port):
        port, _ = server_port
        status, _ = _post(port, "/v1/chat/completions", {"messages": []}, "nope")
        assert status == 401

    def test_models_requires_auth(self, server_port):
        port, _ = server_port
        status, _ = _get(port, "/v1/models", None)
        assert status == 401


class TestBridgeShapes:
    def test_models_lists_both_models(self, server_port):
        port, _ = server_port
        status, body = _get(port, "/v1/models", PASS)
        assert status == 200
        ids = {m["id"] for m in body["data"]}
        assert compat_server.config.OPENAI_MODEL in ids
        assert compat_server.config.OPENAI_MODEL_ANALYSIS in ids
        assert body["object"] == "list"

    def test_chat_completion_shape(self, server_port):
        port, agent = server_port
        status, body = _post(
            port, "/v1/chat/completions",
            {"model": "anything", "messages": [
                {"role": "system", "content": "sys"},
                {"role": "user", "content": "I mumbled today"},
            ]},
            PASS,
        )
        assert status == 200
        assert body["object"] == "chat.completion"
        choice = body["choices"][0]
        assert choice["finish_reason"] == "stop"
        assert choice["message"]["role"] == "assistant"
        assert choice["message"]["content"] == agent.reply

    def test_agent_receives_opencode_platform_and_text(self, server_port):
        port, agent = server_port
        _post(port, "/v1/chat/completions",
              {"messages": [{"role": "user", "content": "hello"}]}, PASS)
        assert agent.calls == [("opencode", "bearer:default", "hello")]

    def test_error_reply_surfaces_as_502(self, server_port):
        """Self-contained second server with an erroring agent."""
        port, _ = server_port
        agent = FakeAgentCore(error=True)
        srv = start_compat_server(agent, bind="127.0.0.1", port=0)
        try:
            status, body = _post(srv.server_address[1], "/v1/chat/completions",
                                 {"messages": [{"role": "user", "content": "x"}]},
                                 compat_server.config.DEMO_PASSCODE)
            assert status == 502
            assert body["error"]["type"] == "agent_unavailable"
        finally:
            srv.shutdown()
            srv.server_close()

    def test_no_user_message_is_400(self, server_port):
        port, _ = server_port
        status, body = _post(port, "/v1/chat/completions",
                             {"messages": [{"role": "assistant", "content": "only bot"}]},
                             PASS)
        assert status == 400

    def test_unknown_route_is_404(self, server_port):
        port, _ = server_port
        status, _ = _post(port, "/v1/embeddings", {"messages": []}, PASS)
        assert status == 404

    def test_malformed_json_is_400(self, server_port):
        port, _ = server_port
        req = urllib.request.Request(
            f"http://127.0.0.1:{port}/v1/chat/completions",
            data=b"{not json",
            headers={"Content-Type": "application/json",
                     "Authorization": f"Bearer {PASS}"},
            method="POST",
        )
        try:
            urllib.request.urlopen(req, timeout=5)
            status = 200
        except urllib.error.HTTPError as e:
            status = e.code
        assert status == 400
