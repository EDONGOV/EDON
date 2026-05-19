# Production Advisory Review

This review classifies the remaining advisory-only paths in production so they do
not stay hidden in code comments.

## Advisory-only by design

| Area | Status | Notes |
| --- | --- | --- |
| AI advisory layer | Advisory-only | Fail-open is intentional. These calls must never authorize live execution. |
| Alerts and notifications | Non-blocking | Can fail without letting an ungoverned action through. |
| Webhooks | Non-blocking | Used for external coordination and observability, not enforcement. |
| Shadow capture | Non-blocking | Advisory telemetry only. |
| Metering and learning | Non-blocking | Telemetry and feedback paths only. |
| Intervention generation | Non-blocking | Advisory output for humans/orchestrators. |
| Coordination graph writes | Non-blocking | Informational state, not enforcement state. |

## Enforcement boundary

The following must remain fail-closed in enterprise mode:

- auth and tenant resolution
- RBAC
- audit persistence
- execution binding
- kill switch activation and propagation
- onboarding and signoff storage
- edge identity checks

## Review result

The remaining advisory-only paths are acceptable only because they are outside
the execution authorization boundary. If any of them are promoted into the
decision path, they must be reclassified and retested as enforcement controls.

