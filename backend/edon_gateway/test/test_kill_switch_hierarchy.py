from __future__ import annotations


def test_scoped_kill_switch_controls_do_not_enable_tenant_wide_block(monkeypatch):
    import backend.edon_gateway.routes.kill_switch as kill_switch

    kill_switch._state.clear()
    kill_switch._cache_expires.clear()
    monkeypatch.setattr(kill_switch, "_db_read", lambda _tenant_id: None)
    monkeypatch.setattr(kill_switch, "_db_write", lambda _tenant_id, _state: True)
    monkeypatch.setattr(kill_switch, "_persist", lambda: None)

    state = kill_switch.activate_kill_switch(
        tenant_id="tenant-a",
        reason="Pause epic connector",
        activated_by="admin",
        scope="connector",
        target_id="epic",
    )

    assert state["active"] is False
    assert any(
        control.get("active") and control.get("scope") == "connector" and control.get("target_id") == "epic"
        for control in state.get("scoped_controls", [])
    )
    assert kill_switch.is_kill_switch_active("tenant-a") is False
    assert kill_switch.is_kill_switch_active("tenant-a", scope="connector", target_id="epic") is True

    kill_switch.deactivate_kill_switch(
        tenant_id="tenant-a",
        deactivated_by="admin",
        scope="connector",
        target_id="epic",
    )

    assert kill_switch.is_kill_switch_active("tenant-a", scope="connector", target_id="epic") is False
