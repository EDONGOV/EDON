"""Wrap LangChain tools with EDON governance.

Every tool call is evaluated by EDON before execution.

Requirements:
    pip install langchain langchain-openai edon-sdk

Run:
    EDON_API_KEY=eak_... OPENAI_API_KEY=sk-... python sdk/examples/langchain_wrapper.py
"""
import os
import sys
sys.path.insert(0, "sdk/python")

from edon_sdk import EdonClient

edon = EdonClient(
    token=os.environ.get("EDON_API_KEY", "dev-token"),
    base_url=os.environ.get("EDON_GATEWAY_URL", "https://edon-gateway.fly.dev"),
)


def make_governed_tool(tool_fn, tool_name: str, agent_id: str):
    """Wrap any callable with EDON governance checking.

    Args:
        tool_fn:   The original tool function (e.g., a LangChain BaseTool.run)
        tool_name: Action type identifier (e.g., "search.web", "email.send")
        agent_id:  Your agent's identifier for audit logging

    Returns:
        A wrapper that evaluates the action before executing it.
    """
    def wrapper(*args, **kwargs):
        payload = {"args": list(args), "kwargs": kwargs}
        result = edon.evaluate(
            action_type=tool_name,
            agent_id=agent_id,
            payload=payload,
        )
        verdict = result["verdict"]

        if verdict == "ALLOW":
            return tool_fn(*args, **kwargs)
        elif verdict == "BLOCK":
            return f"[EDON BLOCKED] {result.get('explanation', 'Action not permitted')}"
        elif verdict == "ESCALATE":
            return f"[EDON ESCALATE] Human review required: {result.get('escalation_question', '')}"
        elif verdict == "DEGRADE":
            # Use safe alternative if provided
            safe = result.get("safe_alternative", {})
            new_kwargs = {**kwargs, **safe}
            return tool_fn(*args, **new_kwargs)
        else:
            return f"[EDON {verdict}] Action deferred — {result.get('explanation', '')}"

    wrapper.__name__ = f"governed_{tool_name.replace('.', '_')}"
    wrapper.__doc__ = f"EDON-governed wrapper for {tool_name}"
    return wrapper


# ── Example: governed search tool ────────────────────────────────────────────

def mock_web_search(query: str) -> str:
    """Mock search — replace with real DuckDuckGoSearchRun or similar."""
    return f"Search results for: {query}"


def mock_send_email(to: str, subject: str, body: str) -> str:
    """Mock email send — replace with real email connector."""
    return f"Email sent to {to}: {subject}"


# Wrap tools with EDON governance
governed_search = make_governed_tool(mock_web_search, "search.web", "langchain-agent-1")
governed_email = make_governed_tool(mock_send_email, "email.send", "langchain-agent-1")

if __name__ == "__main__":
    print("Testing governed search...")
    print(governed_search("AI safety research"))

    print("\nTesting governed email send...")
    print(governed_email(to="user@example.com", subject="Test", body="Hello"))

    print("\nTesting blocked action (sensitive path)...")
    def write_file(path: str, content: str) -> str:
        return f"Written {len(content)} bytes to {path}"

    governed_write = make_governed_tool(write_file, "filesystem.write", "langchain-agent-1")
    print(governed_write(path="/etc/passwd", content="evil"))
