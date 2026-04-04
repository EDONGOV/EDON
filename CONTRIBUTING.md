# Contributing to EDON

## Getting Started

1. Get access to the [EDONGOV GitHub organization](https://github.com/EDONGOV)
2. Clone the repo: `git clone https://github.com/EDONGOV/EDON.git`
3. Read the [README](./README.md) and set up your local environment

## Branch Workflow

**Never push directly to `master`.** It is protected.

```
master (protected)
   ↑
pull request
   ↑
feature branch
```

### Creating a Feature Branch

```bash
git checkout master
git pull origin master
git checkout -b feature/your-feature-name
```

Branch naming conventions:
- `feature/policy-engine`
- `feature/risk-evaluator`
- `fix/audit-logging-bug`
- `chore/update-dependencies`

### Submitting a Pull Request

1. Push your branch: `git push origin feature/your-feature-name`
2. Open a pull request on GitHub against `master`
3. Fill in the PR description — what changed and why
4. Request a review from a teammate
5. Address any review comments
6. Once approved and CI passes, merge

## CI/CD

Every pull request automatically runs:
- Backend tests (Python/pytest)
- Frontend tests (Vitest + Playwright)

Both must pass before merging.

## Security

Never commit secrets, API keys, tokens, or passwords.
All sensitive values go in **GitHub Secrets** and are accessed via environment variables.

If you accidentally commit a secret, notify the team immediately.

## Repo Structure

```
/backend        FastAPI gateway, AI advisory, billing
/frontend       React dashboard (edon-sentinel-core)
/demos          Standalone demo apps (healthcare, etc.)
/docs           Architecture docs, runbooks, migration guides
/sdk            SDK docs and examples
/load_tests     Locust load testing scenarios
```

## Questions?

Open a GitHub issue or ask in the team channel.
