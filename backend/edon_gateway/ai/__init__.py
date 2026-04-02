"""EDON AI Advisory Layer.

All components in this package are ADVISORY ONLY:
- They enrich governance context (meta, scores, summaries)
- They NEVER issue verdicts or modify deterministic governance decisions
- They fail-open: any error returns None/fallback and governance continues

Public API:
    intent_alignment.score_intent_alignment()    — semantic alignment score
    risk_classifier.classify_action_risk()       — independent risk score
    injection_detector.score_semantic_injection() — semantic injection score
    escalation_summarizer.enrich_review_item()   — AI summary for review queue
    policy_suggester.generate_policy_suggestions() — pattern-based suggestions
    audit_miner.mine_audit_trail()               — audit anomaly mining
    policy_author.author_policy_rule()           — NL → policy rule JSON
    compliance_narrator.narrate_compliance_report() — executive narrative
    client.is_ai_available()                     — check if AI is configured
"""

from .client import is_ai_available

__all__ = ["is_ai_available"]
