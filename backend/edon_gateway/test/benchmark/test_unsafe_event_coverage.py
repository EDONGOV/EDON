"""Unsafe event coverage gate.

Verifies that every entry in the unsafe event catalog has measurable
test coverage. Fails if any catastrophic event class has zero covering cases.
"""

import pytest

from .cases import ALL_CASES
from .cases_extended import ALL_EXTENDED_CASES
from .sequence_cases import ALL_SEQUENCE_CASES
from .unsafe_events import UNSAFE_EVENTS, covering_cases, coverage_report

ALL_CASES_COMBINED = ALL_CASES + ALL_EXTENDED_CASES


def test_unsafe_event_catalog_is_complete():
    """Every unsafe event must have a non-empty description and detection path."""
    for ue_id, ue in UNSAFE_EVENTS.items():
        assert ue.get("name"), f"{ue_id} missing name"
        assert ue.get("description"), f"{ue_id} missing description"
        assert ue.get("detects_via"), f"{ue_id} has no detection path"


@pytest.mark.parametrize("ue_id", list(UNSAFE_EVENTS.keys()))
def test_unsafe_event_has_coverage(ue_id):
    """Each unsafe event must be covered by at least one benchmark case or external test."""
    ue = UNSAFE_EVENTS[ue_id]
    covering = covering_cases(ue_id, ALL_CASES_COMBINED)
    # UE-002 and UE-004 are covered by dedicated test files (not benchmark cases)
    external_coverage = {"UE-002", "UE-004", "UE-006"}
    if ue_id in external_coverage:
        pytest.skip(f"{ue_id} covered by dedicated test file: {ue['detects_via']}")
    assert len(covering) > 0, (
        f"{ue_id} ({ue['name']}) has ZERO covering benchmark cases.\n"
        f"Detection path: {ue['detects_via']}\n"
        f"{coverage_report(ALL_CASES_COMBINED)}"
    )


def test_coverage_report_printable():
    """Smoke test: the coverage report can be generated without errors."""
    report = coverage_report(ALL_CASES_COMBINED)
    print("\n" + report)
    assert "UE-001" in report
    assert "UE-008" in report


def test_critical_cases_all_map_to_ue001():
    """All critical-severity cases should prevent UE-001 (silent false negative)."""
    critical = [c for c in ALL_CASES_COMBINED if c.severity == "critical"]
    assert len(critical) > 0, "No critical cases found"
    # Critical cases must require non-ALLOW verdicts
    for c in critical:
        if c.is_safe_action:
            continue  # FP cases are critical for precision, not UE-001
        assert c.must_not_be or c.must_be_one_of or c.must_be, (
            f"Critical case {c.id} has no verdict constraint"
        )


def test_isolation_cases_cover_ue003():
    """Isolation cases must use unique tenant_ids to prove cross-tenant separation."""
    isolation_cases = [c for c in ALL_CASES_COMBINED if c.category == "isolation"]
    tenant_ids = [c.input.tenant_id for c in isolation_cases]
    assert len(set(tenant_ids)) == len(tenant_ids), (
        "Isolation cases share tenant_id — cross-tenant separation is not being tested"
    )
