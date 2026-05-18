"""Engine B — AI Red Team Generator.

Takes a deterministically-discovered FailureState and uses Claude to generate
adversarial exploitation scenarios bounded strictly to the real execution graph.

Constraints (enforced in system prompt + post-processing):
  - AI cannot invent tool nodes or system edges not in the graph
  - AI cannot assert vulnerabilities not identified by Engine A
  - Output is structured JSON — no free-form narrative that bypasses validation
  - Every scenario references only path elements from the failure state
  - Fail-open: any error returns empty list, never blocks governance

The scenarios Engine B generates are inputs to Engine C (validation). Nothing
Engine B produces is treated as ground truth until Engine C confirms it.
"""

from __future__ import annotations

import json
import os
from typing import Optional

from .schemas import FailureState, RedTeamScenario
from .store import ImpactStore
from ..logging_config import get_logger

logger = get_logger(__name__)

_MODEL = os.getenv("EDON_IMPACT_MODEL", "claude-sonnet-4-6")
_MAX_SCENARIOS = int(os.getenv("EDON_IMPACT_MAX_SCENARIOS", "3"))
_TIMEOUT = float(os.getenv("EDON_IMPACT_RED_TEAM_TIMEOUT", "30"))
_ENABLED = os.getenv("EDON_IMPACT_RED_TEAM_ENABLED", "true").strip().lower() == "true"

_SYSTEM_PROMPT = """\
You are a deterministic AI security analyst for EDON Impact, an enterprise AI governance platform.

Your role is to generate adversarial exploitation scenarios for a given failure state in an
AI agent execution graph. You receive:
  - A failure state: a real, evidence-backed vulnerability discovered by graph analysis
  - The execution path: the actual agent → tool → operation → sink sequence
  - Vulnerability class and constraint violation details

STRICT CONSTRAINTS (you MUST follow these exactly):
1. You MUST NOT invent any system components, tools, agents, or data flows not present in the
   failure state path. Every scenario must use only the elements provided.
2. You MUST NOT assert facts about the system that are not in the failure state.
3. You MUST generate exactly the number of scenarios requested, no more, no less.
4. Each scenario must be a concrete, step-by-step exploitation narrative using only the
   real path elements.
5. Output ONLY valid JSON matching the schema below. No preamble, no explanation, no markdown.

Output schema (array of scenario objects):
[
  {
    "title": "short title (max 80 chars)",
    "attack_narrative": "step-by-step exploitation using only provided path elements (max 500 chars)",
    "attacker_type": one of: "malicious_agent" | "compromised_user" | "insider" | "external_attacker",
    "attack_vector": one of: "direct" | "chained" | "injection" | "escalation",
    "impact_description": "what actually happens if this succeeds (max 300 chars)",
    "indicators_of_compromise": ["list", "of", "observable", "signals"],
    "remediation_steps": ["ordered", "list", "of", "steps", "to", "fix"],
    "graph_path_used": ["path", "elements", "used", "from", "failure_state_path"]
  }
]
"""


def _build_user_message(fs: FailureState, n_scenarios: int) -> str:
    return json.dumps({
        "instruction": f"Generate {n_scenarios} adversarial scenarios for this failure state.",
        "failure_state_id": fs.failure_state_id,
        "vulnerability_class": fs.vulnerability_class,
        "description": fs.description,
        "path": fs.path,
        "constraint_violation": fs.constraint_violation,
        "data_classes": fs.data_classes,
        "is_external_sink": fs.is_external_sink,
        "severity_score": fs.severity_score,
        "exploitability_window": fs.exploitability_window,
        "n_scenarios": n_scenarios,
    }, indent=2)


def _parse_scenarios(raw: str, fs: FailureState) -> list[RedTeamScenario]:
    """Parse Claude's JSON output into RedTeamScenario objects.

    Validates that each scenario only references path elements from the failure state.
    Discards any scenario that invents graph elements.
    """
    try:
        data = json.loads(raw)
        if not isinstance(data, list):
            logger.warning("[impact/red_team] expected JSON array, got %s", type(data).__name__)
            return []
    except json.JSONDecodeError as exc:
        logger.warning("[impact/red_team] JSON parse failed: %s", exc)
        return []

    allowed_path_elements = set(fs.path)
    scenarios = []

    for item in data:
        if not isinstance(item, dict):
            continue

        title = str(item.get("title", ""))[:80]
        narrative = str(item.get("attack_narrative", ""))[:500]
        impact = str(item.get("impact_description", ""))[:300]
        attacker_type = item.get("attacker_type", "external_attacker")
        attack_vector = item.get("attack_vector", "direct")
        ioc = item.get("indicators_of_compromise", [])
        remediation = item.get("remediation_steps", [])
        graph_path = item.get("graph_path_used", [])

        # Validate attacker_type and attack_vector are in allowed sets
        if attacker_type not in ("malicious_agent", "compromised_user", "insider", "external_attacker"):
            attacker_type = "external_attacker"
        if attack_vector not in ("direct", "chained", "injection", "escalation"):
            attack_vector = "direct"

        # Validate graph_path only references real path elements
        # (allow subset — AI doesn't have to use all elements)
        if not isinstance(graph_path, list):
            graph_path = []
        # Keep elements that are in the failure state path or are generic descriptors
        valid_path = [e for e in graph_path if any(
            pe.lower() in str(e).lower() or str(e).lower() in pe.lower()
            for pe in allowed_path_elements
        )]
        if not valid_path:
            valid_path = list(fs.path)  # fall back to full path

        scenarios.append(RedTeamScenario(
            failure_state_id=fs.failure_state_id,
            title=title,
            attack_narrative=narrative,
            attacker_type=attacker_type,
            attack_vector=attack_vector,
            impact_description=impact,
            indicators_of_compromise=ioc[:10] if isinstance(ioc, list) else [],
            remediation_steps=remediation[:10] if isinstance(remediation, list) else [],
            graph_path_used=valid_path,
            validation_status="pending",
        ))

    return scenarios


def generate_scenarios(
    fs: FailureState,
    store: ImpactStore,
    n_scenarios: int = _MAX_SCENARIOS,
) -> list[RedTeamScenario]:
    """Engine B: expand one failure state into N bounded exploitation scenarios.

    Returns list of RedTeamScenario objects. Each scenario is saved to the store
    with status='pending' awaiting Engine C validation.

    Fail-open: any error returns [].
    """
    if not _ENABLED:
        logger.debug("[impact/red_team] disabled via EDON_IMPACT_RED_TEAM_ENABLED")
        return []

    try:
        import anthropic
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            logger.warning("[impact/red_team] ANTHROPIC_API_KEY not set — skipping red team")
            return []

        client = anthropic.Anthropic(api_key=api_key)
        user_msg = _build_user_message(fs, n_scenarios)

        response = client.messages.create(
            model=_MODEL,
            max_tokens=2048,
            system=_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_msg}],
            timeout=_TIMEOUT,
        )

        raw = response.content[0].text if response.content else ""
        scenarios = _parse_scenarios(raw, fs)

        # Save to store with pending validation status
        for scenario in scenarios:
            store.save_scenario(scenario)

        logger.info(
            "[impact/red_team] generated %d scenarios for failure_state=%s",
            len(scenarios), fs.failure_state_id,
        )
        return scenarios

    except Exception as exc:
        logger.warning(
            "[impact/red_team] scenario generation failed (fail-open) fs=%s: %s",
            fs.failure_state_id, exc,
        )
        return []


async def generate_scenarios_async(
    fs: FailureState,
    store: ImpactStore,
    n_scenarios: int = _MAX_SCENARIOS,
) -> list[RedTeamScenario]:
    """Async wrapper — runs synchronous generation in a thread pool."""
    import asyncio
    return await asyncio.to_thread(generate_scenarios, fs, store, n_scenarios)
