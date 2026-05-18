from backend.edon_gateway.onboarding.deployment_package import generate_deployment_package
from backend.edon_gateway.onboarding.policy_bootstrap import bootstrap_policies
from backend.edon_gateway.onboarding.profile import AgentSystemSpec, GovernanceDeploymentProfile
from backend.edon_gateway.onboarding.repeatable_architecture import build_repeatable_architecture_standard
from backend.edon_gateway.onboarding.topology import generate_topology


def _profile() -> GovernanceDeploymentProfile:
    profile = GovernanceDeploymentProfile(
        profile_id="gdp-test-123456",
        tenant_id="tenant-001",
        org_name="Acme Health",
        created_at="2026-05-18T12:00:00+00:00",
        updated_at="2026-05-18T12:00:00+00:00",
        agent_systems=[
            AgentSystemSpec(
                name="Clinical Summary Bot",
                agent_type="llm_agent",
                actions=["ehr.read", "ehr.summarize", "email.send"],
                data_classes=["PHI"],
                external_sinks=["ehr.example.com"],
                description="Clinical support agent",
            )
        ],
        identity_provider="okta",
        environments=["k8s"],
        external_sinks=["ehr.example.com"],
        compliance_requirements=["HIPAA"],
        all_data_classes=["PHI"],
        all_actions=["ehr.read", "ehr.summarize", "email.send"],
        risk_tier="high",
        risk_score=7,
    )
    return profile


def test_repeatable_architecture_standard_has_invariant_layers():
    profile = _profile()
    topology = generate_topology(profile)
    bundle = bootstrap_policies(profile)
    package = generate_deployment_package(profile, topology)

    standard = build_repeatable_architecture_standard(profile, topology, package, bundle)

    assert standard.version == "v1"
    assert standard.tenant_id == "tenant-001"
    assert [layer.name for layer in standard.invariant_layers] == [
        "runtime_governance_engine",
        "decision_kernel",
        "agent_communication_layer",
        "operational_intelligence_layer",
        "edge_runtime",
        "integration_layer",
        "command_console",
    ]
    assert [pack.name for pack in standard.customer_variable_packs] == [
        "policy_pack",
        "integration_pack",
        "workflow_pack",
        "permission_pack",
        "scale_pack",
        "environment_pack",
    ]
    assert "restore drill evidence" in standard.proof_requirements
    assert "execution binding evidence" in standard.proof_requirements
    assert "execution without a valid decision token" in standard.forbidden_variation
    assert standard.policy_shape["policy_layers"]["hard_safety"] >= 1
    assert "http_proxy" in standard.deployment_modes or "sidecar" in standard.deployment_modes
