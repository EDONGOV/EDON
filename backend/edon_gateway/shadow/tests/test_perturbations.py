"""Tests for the shadow perturbation library.

Verifies that each perturbation type actually mutates the expected fields
and that the mutation is meaningful (not a no-op).
"""

import pytest

from ..perturbations import PERTURBATIONS, get_perturbations


_BASE_PAYLOAD = {"to": "user@example.com", "subject": "Hello", "body": "Test body"}
_BASE_CONTEXT = {"stated_intent": "Send a report", "session_id": "sess-001"}
_BASE_ACTION_TYPE = "email.send"


def _apply(perturb):
    return perturb.apply(
        dict(_BASE_PAYLOAD),
        dict(_BASE_CONTEXT),
        _BASE_ACTION_TYPE,
    )


# ── Library integrity ──────────────────────────────────────────────────────────


def test_perturbation_library_is_nonempty():
    assert len(PERTURBATIONS) > 20, "Expected at least 20 perturbations"


def test_all_perturbations_have_required_fields():
    for p in PERTURBATIONS:
        assert p.name, f"Perturbation missing name: {p}"
        assert p.type, f"Perturbation missing type: {p.name}"
        assert p.description, f"Perturbation missing description: {p.name}"
        assert callable(p.apply), f"Perturbation apply not callable: {p.name}"


def test_perturbation_types_are_valid():
    valid_types = {
        "prompt_injection", "malformed_payload",
        "boundary_input", "privilege_escalation", "context_poisoning",
    }
    for p in PERTURBATIONS:
        assert p.type in valid_types, f"Unknown type '{p.type}' on '{p.name}'"


def test_all_perturbation_names_are_unique():
    names = [p.name for p in PERTURBATIONS]
    assert len(names) == len(set(names)), "Duplicate perturbation names found"


# ── Return shape ───────────────────────────────────────────────────────────────


def test_all_perturbations_return_four_tuple():
    for p in PERTURBATIONS:
        result = _apply(p)
        assert isinstance(result, tuple) and len(result) == 4, (
            f"{p.name} did not return a 4-tuple"
        )
        payload, context, action_type, field = result
        assert isinstance(payload, dict), f"{p.name}: payload not a dict"
        assert isinstance(context, dict), f"{p.name}: context not a dict"
        assert isinstance(action_type, str), f"{p.name}: action_type not a str"
        assert isinstance(field, str) and field, f"{p.name}: field empty"


# ── Prompt injection ───────────────────────────────────────────────────────────


def test_prompt_injection_payload_mutates_payload():
    injectors = [p for p in PERTURBATIONS if p.type == "prompt_injection" and "payload" in p.name]
    assert injectors, "No payload prompt injection perturbations found"
    for p in injectors:
        mp, mc, at, field = _apply(p)
        assert mp != _BASE_PAYLOAD, f"{p.name}: payload unchanged"
        assert "payload" in field, f"{p.name}: field should reference payload"


def test_prompt_injection_context_mutates_context():
    injectors = [p for p in PERTURBATIONS if p.type == "prompt_injection" and "context" in p.name]
    assert injectors, "No context prompt injection perturbations found"
    for p in injectors:
        mp, mc, at, field = _apply(p)
        assert mc != _BASE_CONTEXT, f"{p.name}: context unchanged"
        assert "context" in field, f"{p.name}: field should reference context"


# ── Malformed payload ──────────────────────────────────────────────────────────


def test_malformed_payload_mutates_first_field():
    malformers = [p for p in PERTURBATIONS if p.type == "malformed_payload"]
    assert malformers, "No malformed payload perturbations found"
    for p in malformers:
        mp, mc, at, field = _apply(p)
        # At least one key should have a different value
        original_vals = set(str(v) for v in _BASE_PAYLOAD.values())
        mutated_vals = set(str(v) for v in mp.values())
        assert original_vals != mutated_vals or set(mp.keys()) != set(_BASE_PAYLOAD.keys()), (
            f"{p.name}: payload not mutated"
        )


# ── Boundary inputs ────────────────────────────────────────────────────────────


def test_boundary_input_replaces_payload():
    boundary = [p for p in PERTURBATIONS if p.type == "boundary_input"]
    assert boundary, "No boundary input perturbations found"
    for p in boundary:
        mp, mc, at, field = _apply(p)
        assert mp != _BASE_PAYLOAD, f"{p.name}: payload not replaced"


# ── Privilege escalation ───────────────────────────────────────────────────────


def test_privilege_escalation_changes_action_type():
    esc = [p for p in PERTURBATIONS if p.type == "privilege_escalation"]
    assert esc, "No privilege escalation perturbation found"
    for p in esc:
        mp, mc, at, field = _apply(p)
        assert at != _BASE_ACTION_TYPE, f"{p.name}: action_type unchanged"
        assert field == "action_type", f"{p.name}: perturbed_field should be 'action_type'"


def test_privilege_escalation_does_not_mutate_payload_or_context():
    esc = [p for p in PERTURBATIONS if p.type == "privilege_escalation"]
    for p in esc:
        mp, mc, at, field = _apply(p)
        assert mp == _BASE_PAYLOAD, f"{p.name}: payload should be unchanged"
        assert mc == _BASE_CONTEXT, f"{p.name}: context should be unchanged"


# ── Context poisoning ──────────────────────────────────────────────────────────


def test_context_poisoning_replaces_stated_intent():
    poisoners = [p for p in PERTURBATIONS if p.type == "context_poisoning"]
    assert poisoners, "No context poisoning perturbations found"
    for p in poisoners:
        mp, mc, at, field = _apply(p)
        assert mc.get("stated_intent") != _BASE_CONTEXT.get("stated_intent"), (
            f"{p.name}: stated_intent unchanged"
        )
        assert "context" in field


def test_context_poisoning_does_not_change_action_type():
    poisoners = [p for p in PERTURBATIONS if p.type == "context_poisoning"]
    for p in poisoners:
        mp, mc, at, field = _apply(p)
        assert at == _BASE_ACTION_TYPE, f"{p.name}: action_type should be unchanged"


# ── get_perturbations filter ───────────────────────────────────────────────────


def test_get_perturbations_type_filter():
    injections = get_perturbations(["prompt_injection"])
    assert all(p.type == "prompt_injection" for p in injections)
    assert len(injections) > 0


def test_get_perturbations_none_returns_all():
    all_p = get_perturbations(None)
    assert len(all_p) == len(PERTURBATIONS)


def test_get_perturbations_unknown_type_returns_empty():
    result = get_perturbations(["nonexistent_type"])
    assert result == []
