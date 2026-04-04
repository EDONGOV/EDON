# Integration Guide — Wrapping Existing Agents with EDON

## The Pattern

EDON acts as a gateway between your agent and the outside world. Every action
that has side effects (API calls, emails, file writes, DB mutations) should be
evaluated by EDON before execution.

```
Agent → EDON.evaluate(action) → ALLOW → Execute action
                              → BLOCK  → Refuse
                              → ESCALATE → Human review
```

---

## Step-by-Step: Wrapping an OpenAI Function-Calling Agent

```python
import os
import json
import openai
from edon_sdk import EdonClient

edon = EdonClient(token=os.environ["EDON_API_KEY"])
oai = openai.OpenAI()

def governed_tool_call(tool_name: str, tool_args: dict, agent_id: str) -> dict:
    """Evaluate a tool call through EDON before executing it."""
    result = edon.evaluate(
        action_type=tool_name,       # e.g. "send_email", "search_web"
        agent_id=agent_id,
        payload=tool_args,
    )
    if result["verdict"] != "ALLOW":
        return {"error": f"Action blocked: {result.get('explanation', '')}"}
    return execute_tool(tool_name, tool_args)


def run_agent(user_message: str, agent_id: str = "openai-agent-1"):
    messages = [{"role": "user", "content": user_message}]
    tools = [
        {"type": "function", "function": {
            "name": "send_email",
            "description": "Send an email",
            "parameters": {"type": "object", "properties": {
                "to": {"type": "string"}, "subject": {"type": "string"}, "body": {"type": "string"}
            }}
        }}
    ]

    while True:
        response = oai.chat.completions.create(
            model="gpt-4o", messages=messages, tools=tools
        )
        choice = response.choices[0]
        if choice.finish_reason == "stop":
            return choice.message.content

        # Handle tool calls — each goes through EDON
        for call in (choice.message.tool_calls or []):
            args = json.loads(call.function.arguments)
            tool_result = governed_tool_call(call.function.name, args, agent_id)
            messages.append({"role": "tool", "tool_call_id": call.id,
                             "content": json.dumps(tool_result)})
```

---

## Step-by-Step: Wrapping a LangChain Agent

```python
from langchain.tools import tool
from langchain.agents import AgentExecutor, create_openai_tools_agent
from edon_sdk import EdonClient

edon = EdonClient(token=os.environ["EDON_API_KEY"])

def make_governed_tool(original_tool, agent_id: str):
    """Wrap a LangChain tool with EDON governance."""
    @tool(original_tool.name, description=original_tool.description)
    def governed(*args, **kwargs):
        payload = {"args": list(args), "kwargs": kwargs}
        result = edon.evaluate(
            action_type=original_tool.name,
            agent_id=agent_id,
            payload=payload,
        )
        if result["verdict"] == "ALLOW":
            return original_tool.run(*args, **kwargs)
        elif result["verdict"] == "BLOCK":
            return f"Action blocked: {result.get('explanation', 'policy violation')}"
        elif result["verdict"] == "ESCALATE":
            return f"Action requires human approval: {result.get('escalation_question', '')}"
        return f"Action deferred (verdict={result['verdict']})"
    return governed

# Usage
from langchain_community.tools import DuckDuckGoSearchRun

search = DuckDuckGoSearchRun()
governed_search = make_governed_tool(search, agent_id="langchain-agent-1")
tools = [governed_search]
# ... rest of LangChain agent setup
```

---

## Step-by-Step: Custom Agent

```python
from edon_sdk import EdonClient

edon = EdonClient(token=os.environ["EDON_API_KEY"])

class GovernedAgent:
    def __init__(self, agent_id: str):
        self.agent_id = agent_id

    def act(self, action_type: str, payload: dict) -> dict:
        """All agent actions go through this method."""
        verdict = edon.evaluate(
            action_type=action_type,
            agent_id=self.agent_id,
            payload=payload,
        )

        if verdict["verdict"] == "ALLOW":
            return self._execute(action_type, payload)
        elif verdict["verdict"] == "BLOCK":
            raise PermissionError(verdict["explanation"])
        elif verdict["verdict"] == "ESCALATE":
            return self._request_human_approval(verdict)
        elif verdict["verdict"] == "DEGRADE":
            return self._execute(action_type, verdict.get("safe_alternative", payload))
        else:
            raise RuntimeError(f"Unexpected verdict: {verdict['verdict']}")

    def _execute(self, action_type, payload):
        # Your actual execution logic here
        print(f"Executing {action_type} with {payload}")
        return {"status": "ok"}

    def _request_human_approval(self, verdict):
        print(f"Human review needed: {verdict.get('escalation_question')}")
        return {"status": "pending_review"}
```

---

## Choosing the Right Policy Pack

| Policy Pack | Best for |
|-------------|----------|
| `casual_user` | Low-stakes agents, demos, testing |
| `market_analyst` | Read-only research agents |
| `helpdesk` | Customer support bots |
| `ops_commander` | DevOps/infrastructure automation |
| `founder_mode` | Trusted agents with broad permissions |
| `autonomy_mode` | Fully autonomous agents (maximum permissions) |

```python
# Apply a policy pack for your tenant
client.apply_policy("ops_commander")
```

---

## Handling ESCALATE Verdicts

ESCALATE means a human should review before proceeding. Implement a review queue:

```python
import uuid
from datetime import datetime

escalation_queue = []  # In production, use a DB or message queue

def handle_escalation(verdict: dict, action_type: str, payload: dict) -> dict:
    ticket_id = str(uuid.uuid4())
    escalation_queue.append({
        "id": ticket_id,
        "action_type": action_type,
        "payload": payload,
        "question": verdict.get("escalation_question"),
        "options": verdict.get("escalation_options", []),
        "created_at": datetime.utcnow().isoformat(),
        "status": "pending",
    })
    return {"escalated": True, "ticket_id": ticket_id, "message": "Awaiting human approval"}
```
