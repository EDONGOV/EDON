from __future__ import annotations


def test_policy_change_records_main_audit_event(monkeypatch):
    from edon_gateway.routes.audit import record_policy_change

    calls = []

    class _DB:
        def log_policy_change(self, **kwargs):
            calls.append(("policy_change", kwargs))
            return "chg-123"

        def save_audit_event(self, **kwargs):
            calls.append(("audit_event", kwargs))
            return "dec-123"

    monkeypatch.setattr("edon_gateway.routes.audit.get_db", lambda: _DB())

    record_policy_change(
        tenant_id="tenant-1",
        change_type="update",
        entity_type="policy_rule",
        entity_id="rule-1",
        entity_name="Rule One",
        diff_json={"before": {"enabled": True}, "after": {"enabled": False}},
        changed_by="admin-1",
    )

    kinds = [kind for kind, _ in calls]
    assert kinds == ["policy_change", "audit_event"]

    audit_kwargs = calls[1][1]
    assert audit_kwargs["customer_id"] == "tenant-1"
    assert audit_kwargs["agent_id"] == "admin-1"
    assert audit_kwargs["action"]["tool"] == "policy"
    assert audit_kwargs["action"]["op"] == "update"
    assert audit_kwargs["decision"]["reason_code"] == "POLICY_CHANGE_RECORDED"

