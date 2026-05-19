from __future__ import annotations

from pathlib import Path


def test_tenant_knowledge_snapshot_includes_governance_surface(tmp_path, monkeypatch):
    from backend.edon_gateway.persistence.database import Database
    from backend.edon_gateway.onboarding.profile import OnboardingStore
    from backend.edon_gateway.onboarding.signoff import SignoffStore
    from backend.edon_gateway.tenant_knowledge import build_tenant_knowledge_snapshot, render_tenant_knowledge_snapshot

    db = Database(Path(tmp_path) / "tenant-knowledge.db")
    profile_store = OnboardingStore(str(Path(tmp_path) / "onboarding.db"))
    signoff_store = SignoffStore(str(Path(tmp_path) / "signoff.db"))
    db.create_user("user-1", "ops@example.com", "clerk", "subject-1", role="admin")
    db.create_tenant("tenant-1", "user-1")

    profile = profile_store.create(
        tenant_id="tenant-1",
        org_name="Acme Health",
        agent_systems=[
            {
                "name": "chart-assistant",
                "agent_type": "llm_agent",
                "actions": ["ehr.note.draft", "ehr.record.writeback"],
                "data_classes": ["PHI", "internal"],
                "external_sinks": ["epic"],
                "description": "Clinical documentation assistant",
            }
        ],
        identity_provider="entra",
        environments=["saas"],
        compliance_requirements=["HIPAA"],
        deployment_mode="production",
        market_pack="healthcare",
    )
    signoff_store.create(
        profile_id=profile.profile_id,
        tenant_id="tenant-1",
        requested_by="ops-admin",
        enforcement_scope=["chart-assistant"],
        escalation_rules_accepted=True,
        kill_switch_authority="tenant_admin",
        data_classes_governed=["PHI"],
        governed_action_matrix=[{"action": "ehr.record.writeback", "risk": "high"}],
        risk_tier_definitions=[{"tier": "high", "approval": "required"}],
        fail_open_exceptions=[{"scope": "break_glass"}],
        rollback_limits=["Partial rollback only"],
        escalation_paths=["agent -> governance admin"],
        customer_signoff_artifacts=["governed_action_matrix"],
    )
    signoff_store.approve(next(iter(signoff_store.list_for_profile(profile.profile_id)))["signoff_id"], "tenant-admin")

    db.register_agent_full(
        agent_id="chart-assistant",
        tenant_id="tenant-1",
        name="Chart Assistant",
        agent_type="llm_agent",
        capabilities=["ehr.note.draft", "ehr.record.writeback"],
        policy_pack="hospital",
        metadata={"model": "claude"},
        department="clinical",
    )
    db.create_policy_rule(
        tenant_id="tenant-1",
        name="block_export",
        action="BLOCK",
        description="Block unsafe exports",
        condition_tool="export",
        condition_op="write",
        priority=900,
        enabled=True,
    )
    db.write_preference("tenant-1", "assistant.tone", "direct")
    db.save_conversation("conv-1", "tenant-1", [{"role": "user", "content": "Remember our EPIC rollout"}], title="Rollout")
    db.upsert_memory("mem-1", "tenant-1", "preference", "Tenant prefers concise clinical summaries", confidence=0.95, source_conversation_id="conv-1")
    db.pin_memory("mem-1", "tenant-1", True)
    db.review_memory("mem-1", "tenant-1", "approved", "tenant-admin")

    import backend.edon_gateway.tenant_knowledge as tk

    monkeypatch.setattr(tk, "get_db", lambda: db)
    monkeypatch.setattr(tk, "get_onboarding_store", lambda: profile_store)
    monkeypatch.setattr(tk, "get_signoff_store", lambda: signoff_store)

    snapshot = build_tenant_knowledge_snapshot("tenant-1")
    rendered = render_tenant_knowledge_snapshot(snapshot)

    assert snapshot.onboarding_profile["market_pack"] == "healthcare"
    assert snapshot.deployment_mode == "production"
    assert snapshot.latest_signoff["status"] == "approved"
    assert snapshot.agents[0]["agent_id"] == "chart-assistant"
    assert snapshot.policy_rules[0]["name"] == "block_export"
    assert snapshot.preferences["assistant.tone"] == "direct"
    assert snapshot.memories[0]["pinned"] == 1
    assert snapshot.memories[0]["review_status"] == "approved"
    assert snapshot.snapshot_hash
    assert "Acme Health" in rendered
    assert "Snapshot hash:" in rendered


def test_assistant_system_uses_tenant_knowledge_snapshot(monkeypatch):
    import backend.edon_gateway.routes.assistant as assistant
    from backend.edon_gateway.tenant_knowledge import TenantKnowledgeSnapshot

    snapshot = TenantKnowledgeSnapshot(
        tenant_id="tenant-1",
        generated_at="2026-05-19T00:00:00+00:00",
        deployment_mode="pilot",
        market_pack={"slug": "healthcare", "version": "2026.05"},
        onboarding_profile={"org_name": "Acme Health", "stage": "shadow", "deployment_mode": "pilot", "market_pack": "healthcare", "market_pack_version": "2026.05"},
        latest_signoff=None,
        active_policy_preset=None,
        agents=[],
        policy_rules=[],
        connected_services=[],
        enterprise_targets=[],
        memories=[],
        conversations=[],
        preferences={},
        review_queue=[],
        compliance_health={"status": "healthy"},
        drift={"status": "healthy"},
        snapshot_hash="abcd1234",
    )
    monkeypatch.setattr(assistant, "build_tenant_knowledge_snapshot", lambda tenant_id: snapshot)

    system = assistant._build_system("tenant-1")
    assert "TENANT KNOWLEDGE SNAPSHOT" in system
    assert "Acme Health" in system
    assert "market_pack=healthcare@2026.05" in system
    assert "Snapshot hash: abcd1234" in system


def test_memory_governance_supports_pin_review_expire_forget(tmp_path):
    from backend.edon_gateway.persistence.database import Database

    db = Database(Path(tmp_path) / "memory-governance.db")
    db.create_user("user-1", "ops@example.com", "clerk", "subject-1", role="admin")
    db.create_tenant("tenant-1", "user-1")
    db.upsert_memory("mem-1", "tenant-1", "preference", "Prefer shorter summaries", confidence=0.9)

    assert db.pin_memory("mem-1", "tenant-1", True) is True
    assert db.review_memory("mem-1", "tenant-1", "approved", "tenant-admin") is True
    assert db.expire_memory("mem-1", "tenant-1") is True
    assert db.get_memories("tenant-1", limit=20) == []
    assert db.get_memories("tenant-1", limit=20, include_expired=True)[0]["pinned"] == 1
    assert db.forget_memory("mem-1", "tenant-1") is True
    assert db.get_memory("mem-1", "tenant-1") is None


def test_policy_suggestions_are_partitioned_by_tenant(monkeypatch):
    import backend.edon_gateway.ai.policy_suggester as suggester

    monkeypatch.setattr(
        suggester,
        "_suggestion_cache",
        {
            "tenant-a": [{"name": "a", "action": "BLOCK", "auto_escalate": True}],
            "tenant-b": [{"name": "b", "action": "ALLOW", "auto_escalate": False}],
        },
    )
    monkeypatch.setattr(
        suggester,
        "_suggestion_cache_ts",
        {
            "tenant-a": suggester.datetime.now(suggester.UTC),
            "tenant-b": suggester.datetime.now(suggester.UTC),
        },
    )

    tenant_a = suggester.get_cached_suggestions("tenant-a")
    tenant_b = suggester.get_cached_suggestions("tenant-b")

    assert tenant_a["count"] == 1
    assert tenant_a["suggestions"][0]["name"] == "a"
    assert tenant_b["count"] == 1
    assert tenant_b["suggestions"][0]["name"] == "b"
