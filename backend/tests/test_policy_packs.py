"""Quick sanity checks for policy pack presets."""

from edon_gateway.policy_packs import POLICY_PACKS, apply_policy_pack, list_policy_packs


def test_default_pack_exists():
    assert "casual_user" in POLICY_PACKS, "casual_user pack missing"


def test_default_pack_shape():
    intent = apply_policy_pack("casual_user")
    scope = intent.get("scope", {})
    constraints = intent.get("constraints", {})

    assert "clawdbot" in scope, "casual_user should include clawdbot scope"
    assert "invoke" in scope["clawdbot"], "casual_user must allow clawdbot.invoke"

    allowed_tools = constraints.get("allowed_clawdbot_tools", [])
    assert "message" in allowed_tools, "casual_user should allow message tool"


def test_list_policy_packs_includes_default():
    packs = list_policy_packs()
    names = {p["name"] for p in packs}
    assert "casual_user" in names, "casual_user not listed by list_policy_packs"
    assert "market_analyst" in names, "market_analyst not listed by list_policy_packs"
    assert "ops_commander" in names, "ops_commander not listed by list_policy_packs"
    assert "founder_mode" in names, "founder_mode not listed by list_policy_packs"
    assert "helpdesk" in names, "helpdesk not listed by list_policy_packs"
    assert "autonomy_mode" in names, "autonomy_mode not listed by list_policy_packs"


if __name__ == "__main__":
    test_default_pack_exists()
    test_default_pack_shape()
    test_list_policy_packs_includes_default()
    print("Policy pack checks passed.")
