from __future__ import annotations

import httpx
import anthropic

from backend.agents import docs_agent


def test_docs_agent_skips_when_api_key_missing(monkeypatch, capsys):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setattr(docs_agent, "_get_diff", lambda: "@router.get('/v1/test')\n")
    monkeypatch.setattr(docs_agent, "_read", lambda path: "# docs\n")

    assert docs_agent.run() == 0

    out = capsys.readouterr().out
    assert "ANTHROPIC_API_KEY is not set" in out


def test_docs_agent_skips_cleanly_on_auth_failure(monkeypatch, capsys):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-invalid")
    monkeypatch.setattr(docs_agent, "_get_diff", lambda: "@router.get('/v1/test')\n")
    monkeypatch.setattr(docs_agent, "_read", lambda path: "# docs\n")

    class _FakeMessages:
        def create(self, **kwargs):
            request = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
            response = httpx.Response(
                401,
                request=request,
                json={"error": {"type": "authentication_error", "message": "invalid x-api-key"}},
            )
            raise anthropic.AuthenticationError(
                "invalid x-api-key",
                response=response,
                body={"error": {"type": "authentication_error", "message": "invalid x-api-key"}},
            )

    class _FakeClient:
        messages = _FakeMessages()

    monkeypatch.setattr(docs_agent.anthropic, "Anthropic", lambda **kwargs: _FakeClient())

    assert docs_agent.run() == 0

    out = capsys.readouterr().out
    assert "Anthropic authentication failed" in out
