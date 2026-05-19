from pathlib import Path


def test_evidence_pack_contains_signed_ledgers():
    root = Path(__file__).resolve().parents[2]
    docs = root / "docs" / "evidence"
    assert (docs / "verification-ledger.md").exists()
    assert (docs / "production-advisory-review.md").exists()
    compliance = (docs / "compliance-pack.md").read_text(encoding="utf-8")
    assert "verification-ledger.md" in compliance
    assert "production-advisory-review.md" in compliance
    readme = (docs / "README.md").read_text(encoding="utf-8")
    assert "verification-ledger.md" in readme
    assert "production-advisory-review.md" in readme
