# EDON Gateway — Load Tests

Locust-based load tests for the EDON Gateway API. Validates the `< 200ms p95`
SLO for `/v1/action` and exercises the full governance pipeline under load.

## Setup

```bash
pip install -r load_tests/requirements.txt
```

Set the auth token (or use the default dev token):

```bash
export EDON_LOAD_TEST_TOKEN=your-api-key-here
```

## Running Tests

### Smoke test (5 users, 30s — verify stack is up)

```bash
locust -f load_tests/scenarios/smoke.py \
  --headless --host http://localhost:8000 \
  --users 5 --spawn-rate 5 --run-time 30s
```

### SLO validation (50 users, 2 min — validates p95 < 200ms)

```bash
locust -f load_tests/scenarios/slo_validation.py \
  --headless --host http://localhost:8000 \
  --users 50 --spawn-rate 10 --run-time 2m
```

Exits with code 1 if p95 > 200ms or failure rate > 1%.

### Stress test (200 users, ramp over 60s — find breaking point)

```bash
locust -f load_tests/scenarios/stress.py \
  --headless --host http://localhost:8000 \
  --users 200 --spawn-rate 3 --run-time 5m \
  --csv load_tests/results/stress_run
```

### Interactive UI (explore manually)

```bash
locust -f load_tests/locustfile.py --host http://localhost:8000
# Open http://localhost:8089 in browser
```

### Against production

```bash
locust -f load_tests/scenarios/slo_validation.py \
  --headless --host https://edon-gateway.fly.dev \
  --users 20 --spawn-rate 5 --run-time 2m
```

⚠️ Use a low user count against production. Don't exceed your plan's RPM limits.

## SLO Pass/Fail Criteria

| Metric | Target | Test |
|--------|--------|------|
| `/v1/action` p95 latency | < 200ms | `slo_validation.py` |
| Overall failure rate | < 1% | `slo_validation.py` |
| `/health` p99 latency | < 50ms | visual check |

## Interpreting Results

- **p50**: median latency — half of requests faster than this
- **p95**: 95th percentile — the SLO target (< 200ms)
- **p99**: worst-case tail — expect this to be 2-3x p95
- **RPS**: requests per second — the throughput your instance handles

A typical result on a single Fly.io machine (2 CPU, 1GB RAM):

```
/v1/action   p50=45ms  p95=120ms  p99=280ms  RPS=85
```

## Saving Results

```bash
mkdir -p load_tests/results
locust -f load_tests/scenarios/slo_validation.py \
  --headless --host http://localhost:8000 \
  --users 50 --spawn-rate 10 --run-time 2m \
  --csv load_tests/results/$(date +%Y%m%d_%H%M) \
  --html load_tests/results/$(date +%Y%m%d_%H%M).html
```
