# EDON Repeatable Architecture Standard

This standard defines the parts of EDON that must stay invariant across tenants
and the parts that may vary per customer.

This is the platform contract for enterprise deployments: same kernel, same decision record, same audit proof, same enforcement semantics, different customer packs.

## Invariant layers

These layers should stay stable across every deployment:

1. Runtime governance engine
2. Decision Kernel
3. Agent communication layer
4. Operational intelligence layer
5. Edge runtime
6. Integration layer
7. Command console

Each layer keeps the same responsibility, control semantics, and proof
expectations. The customer may change the policy pack or integrations, but not
the causal control model.

The Decision Kernel is the causal core: every governed action becomes one typed
`DecisionCandidate`, is evaluated by one kernel, and is committed as one
immutable `DecisionRecord`. Any execution downstream must bind to that
committed record.

## Customer-variable packs

These packs are allowed to vary by tenant:

- Policy pack
- Integration pack
- Workflow pack
- Permission pack
- Scale pack
- Environment pack

The contract is that these packs change the deployment, not the platform.

No customer pack may override kernel safety invariants or create an alternate
execution path.

## Required proofs

Every enterprise deployment should be able to show:

- tenant isolation evidence
- restore drill evidence
- audit chain validation
- shadow replay evidence
- signoff evidence
- dependency audit evidence
- execution binding evidence

The execution binding requirement means:

- no approved `DecisionRecord`, no valid execution token
- downstream systems reject unbound actions
- shadow results never authorize live execution

## How it is produced

The onboarding flow can generate the repeatable architecture contract from the
tenant profile, topology, policy bootstrap, and deployment package.

API:

- `GET /v1/onboarding/profiles/{profile_id}/architecture-standard`

That endpoint returns the machine-readable standard for the tenant.
