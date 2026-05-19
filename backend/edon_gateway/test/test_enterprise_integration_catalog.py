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


def test_enterprise_catalog_target_lookup_missing_returns_404(_dev_environment):
    from edon_gateway.main import app

    with TestClient(app, headers={"X-Agent-ID": "catalog-test"}) as client:
        resp = client.get("/integrations/enterprise/catalog/not-a-real-target")

    assert resp.status_code == 404
