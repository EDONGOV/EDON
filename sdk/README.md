# EDON SDK

**Every AI agent action, governed.** EDON intercepts agent actions in real time, evaluates them against your policies, and returns a verdict before any side effect occurs.

```python
from edon_sdk import EdonClient

client = EdonClient(token="your-api-key")
result = client.evaluate(action_type="email.send", agent_id="my-agent", payload={"to": "user@co.com"})

if result["verdict"] == "ALLOW":
    send_email(...)   # safe to proceed
```

## Installation

```bash
pip install edon-sdk        # Python
npm install @edon/sdk       # JavaScript / TypeScript
```

## Documentation

| Guide | Description |
|-------|-------------|
| [Python Quickstart](docs/python-quickstart.md) | Get started in 5 minutes |
| [JavaScript Quickstart](docs/javascript-quickstart.md) | Node.js & browser usage |
| [Integration Guide](docs/integration-guide.md) | Wrap existing agents (LangChain, OpenAI, custom) |
| [API Reference](docs/api-reference.md) | Full endpoint reference |

## Examples

```
sdk/examples/basic_agent.py         — minimal working example
sdk/examples/langchain_wrapper.py   — wrapping LangChain with EDON
sdk/examples/handle_verdicts.py     — all verdict types with handlers
```

## Links

- Gateway: https://edon-gateway-prod.fly.dev
- Dashboard: https://console.edoncore.com
- Docs: https://edon-gateway-prod.fly.dev/docs
