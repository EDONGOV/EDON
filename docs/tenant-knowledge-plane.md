# Tenant Knowledge Plane

EDON's sidechat assistant should answer from a canonical tenant snapshot, not
from loose prompt history or global product memory.

## What the snapshot contains

- onboarding profile
- deployment mode
- market pack and policy pack
- approved signoff scope
- registered agents
- policy rules
- connected services
- enterprise connector targets
- durable memories
- conversation history
- pending reviews
- compliance health
- drift status

## Memory governance

Durable memories are tenant-scoped and operator-controlled. They can be:

- pinned
- reviewed
- expired
- forgotten

The assistant should only use active, non-expired tenant memories in its prompt.
Pinned memories are surfaced first. Review state is kept separate from the raw
memory fact so operators can curate what the assistant treats as durable truth.

## Learning loop

EDON's learning loop should stay bounded:

- tenant chat history feeds tenant memories
- policy suggestions are partitioned by tenant
- no cross-tenant memory bleed
- no automatic weight updates

The goal is tenant completeness, not global conversational recall.

## Operational rule

Any assistant request should be able to reconstruct the tenant snapshot from
the same source of truth that powers onboarding, signoff, policies, and
integrations. If the assistant cannot explain the tenant from that snapshot, the
knowledge plane is incomplete.
