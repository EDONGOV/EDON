from starlette.testclient import TestClient


def test_enterprise_catalog_lists_required_systems(_dev_environment):
    from edon_gateway.main import app

    with TestClient(app, headers={"X-Agent-ID": "catalog-test"}) as client:
        resp = client.get("/integrations/enterprise/catalog")

    assert resp.status_code == 200
    data = resp.json()
    targets = data["targets"]
    titles = {item["title"] for item in targets}
    examples = {example for item in targets for example in item.get("examples", [])}

    assert "EHR / EMR Systems" in titles
    assert "Identity & Access Management" in titles
    assert "Clinical Communication Systems" in titles
    assert "Scheduling / Staffing Systems" in titles
    assert "Revenue Cycle / Billing Systems" in titles
    assert "PACS / Imaging Systems" in titles
    assert "Laboratory Systems" in titles
    assert "ERP / Procurement Systems" in titles
    assert "Security / SIEM Systems" in titles
    assert "AI / LLM Providers" in titles
    assert "Robotics / Physical AI Systems" in titles
    assert "Messaging / Workflow Systems" in titles

    assert "Epic Systems" in examples
    assert "Oracle Health (Cerner)" in examples
    assert "MEDITECH" in examples
    assert "Microsoft Entra ID" in examples
    assert "Okta" in examples
    assert "Ping Identity" in examples
    assert "TigerConnect" in examples
    assert "Vocera Communications" in examples
    assert "UKG / Kronos" in examples
    assert "SAP" in examples
    assert "Oracle ERP" in examples
    assert "Microsoft Sentinel" in examples
    assert "Splunk" in examples
    assert "CrowdStrike" in examples
    assert "OpenAI" in examples
    assert "Anthropic" in examples
    assert "Ollama / Qwen runtime" in examples
    assert "Microsoft Teams" in examples
    assert "Slack" in examples
    assert "ServiceNow" in examples
    assert data["approved_only"] is False

    for item in targets:
        assert item["status_tier"] in {"supported", "pilot", "experimental", "blocked"}
        contract = item["connector_contract"]
        assert contract["status_tier"] == item["status_tier"]
        assert contract["tenant_scope"] == "tenant-bound"
        assert contract["requires_execution_binding"] is True
        assert contract["failure_mode"] in {"fail-closed", "advisory"}
        assert contract["approval_requirement"]
        assert contract["auth_modes"]
        assert contract["tested_versions"]


def test_enterprise_catalog_target_lookup_by_category(_dev_environment):
    from edon_gateway.main import app

    with TestClient(app, headers={"X-Agent-ID": "catalog-test"}) as client:
        resp = client.get("/integrations/enterprise/catalog/ehr_emr")

    assert resp.status_code == 200
    data = resp.json()
    assert data["category"] == "ehr_emr"
    assert data["title"] == "EHR / EMR Systems"
    assert "SMART on FHIR / OAuth 2.0" in data["integration_patterns"]
    assert "Decision record binding for all writes" in data["required_controls"]
    assert data["status_tier"] == "supported"
    assert data["enterprise_supported"] is True
    assert data["connector_contract"]["failure_mode"] == "fail-closed"


def test_enterprise_catalog_approved_only_filters_non_supported_targets(_dev_environment):
    from edon_gateway.main import app

    with TestClient(app, headers={"X-Agent-ID": "catalog-test"}) as client:
        resp = client.get("/integrations/enterprise/catalog?approved_only=true")

    assert resp.status_code == 200
    data = resp.json()
    tiers = {item["status_tier"] for item in data["targets"]}
    assert tiers <= {"supported"}
    assert data["approved_only"] is True


def test_enterprise_catalog_rejects_pilot_targets_when_approved_only(_dev_environment):
    from edon_gateway.main import app

    with TestClient(app, headers={"X-Agent-ID": "catalog-test"}) as client:
        resp = client.get("/integrations/enterprise/catalog/clinical_communications?approved_only=true")

    assert resp.status_code == 404


def test_enterprise_catalog_target_lookup_missing_returns_404(_dev_environment):
    from edon_gateway.main import app

    with TestClient(app, headers={"X-Agent-ID": "catalog-test"}) as client:
        resp = client.get("/integrations/enterprise/catalog/not-a-real-target")

    assert resp.status_code == 404
