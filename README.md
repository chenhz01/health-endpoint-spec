# health-endpoint-spec

Liveness and readiness are different questions — "am I up" must not consult the database — yet most codebases grow one `/health` endpoint that mixes both and calls every dependency on every probe. This tool validates a specification of your health endpoints (kinds, status codes, body schema, semantic separation) and checks recorded responses against it. Pure Python, standard library only.

As of 2026-10-13, no direct equivalent found as of 2026-10-13: frameworks ship health-check *implementations* (Spring actuator, K8s probes), but searches across GitHub (194 queries) and the web found no standalone spec validator for liveness/readiness semantic separation.

## Problem

A readiness check that pings the database makes every DB hiccup restart every pod — a self-inflicted outage loop. A liveness endpoint that exposes dependency names leaks topology. A 200 response with `"status": "down"` in the body lies to load balancers. Each bug is trivially visible in a *declaration*; none is visible in a running system until the cascade.

## How it works

1. **Spec validation (`validate`).** Endpoints declare `{path, kind: liveness|readiness, status_code, body}`. Rules: `E001` unknown kind · `E002` liveness body referencing dependencies (`database`, `redis`, `upstream`, …) — hard fail · `E003` readiness without a `checks` map (warn) · `E004` status codes restricted to 200/503 · `E005` body.status ∈ {ok, degraded, down} and consistent with the code (ok↔200, degraded/down↔503) · `E006` duplicate paths · `E007` path/kind convention mismatch (warn) · `E008` body must be an object · `E009` path must start with `/`.
2. **Response probing (`probe`).** Recorded samples — JSONL of `{path, code, body}` — are checked against the spec: undeclared paths, code mismatches, body-status/code inconsistency, and dependency leakage in liveness responses.
3. **Exit contract.** validate: 0 unless a FAIL finding exists; probe: 0 only if every sample conforms. Both support `--json`.

## Quickstart

Requires Python 3.8+. No dependencies, no server needed. Validating a 5,000-endpoint spec takes ~0.006 s [Measured].

```bash
python health_endpoint_spec.py validate spec.json
python health_endpoint_spec.py probe --spec spec.json --samples recordings.jsonl --json
```

`spec.json`: `{"endpoints": [{"path": "/healthz", "kind": "liveness", "status_code": 200, "body": {"status": "ok"}}, {"path": "/readyz", "kind": "readiness", "status_code": 200, "body": {"status": "ok", "checks": {"db": "ok"}}}]}`

## Why not X

- **Kubernetes probes (liveness/readiness HTTP checks)**: they *enforce* behaviour at runtime but define no response schema and will happily restart pods over a badly designed readiness check. No direct equivalent found as of 2026-10-13 for a spec-time validator.
- **Spring Boot Actuator / microservice health libraries**: opinionated implementations bound to their framework; no cross-framework spec, no offline validation of recorded responses.
- **OpenAPI validators**: check general API syntax; they have no concept of liveness-vs-readiness semantics or dependency-leak rules.
- **Contract testers (Pact)**: verify consumer/provider interactions, not health-semantics hygiene.

## Performance

Measured on Windows 10, Python 3.13, single core:

| Workload | Time | Reproduce |
|---|---|---|
| 5,000-endpoint spec [Measured] | 0.006 s | `python -c "import time,health_endpoint_spec as h; s={'endpoints':[{'path':'/healthz%d'%i,'kind':'liveness','status_code':200,'body':{'status':'ok'}} for i in range(5000)]}; t=time.perf_counter(); h.validate_spec(s); print('%.4fs'%(time.perf_counter()-t))"` |
| typical 2-endpoint spec + 100 samples [Measured] | < 0.01 s | `python health_endpoint_spec.py validate spec.json && python health_endpoint_spec.py probe --spec spec.json --samples recordings.jsonl` |

## Minimal Fallback

No Python? A code-review checklist works: liveness handler touches no I/O; readiness handler returns 503 with a `checks` map; body status always matches the HTTP code. The tool exists so that checklist runs in CI on every change instead of in a reviewer's memory.

## Design Trade-offs

- **Spec-file driven, not server-scanning.** Works offline and in CI; the cost is keeping the spec in sync (mitigated by the `probe` subcommand against recorded responses).
- **Dependency names are a fixed keyword list.** Predictable and zero-config; exotic names need the list extended (documented, small).
- **Only 200/503 allowed.** Health endpoints with 4xx semantics are a design smell; strictness is the point.
- **Path conventions are warn-level.** `/healthz` vs `/livez` is style, not safety — advisories stay non-blocking.

## Limits & Second-order Effects

- A passing spec does not make the implementation honour it; pair `validate` with `probe` recordings from real traffic.
- Strict readiness semantics can mask *partial* degradation — model it via the `checks` map and `degraded` status instead of a binary flag.
- If probes are recorded rarely, drift between spec and runtime goes unnoticed; record continuously in staging.
- Hard-failing liveness dependency references may push teams to hide checks behind vague keys — audit key names, not just presence.

## FAQ

**When NOT to use this?** Not for load-testing probe performance, not as a replacement for the platform's probe configuration, and not for non-HTTP health models (TCP checks, gRPC health protocol).

**Why forbid dependencies in liveness?** Liveness answers "is this process wedged"; dependency outages must not trigger process restarts — that converts a dependency blip into a fleet-wide restart storm.

**What is `degraded` for?** Partial capability: serve read-only or shed load (503 for balancing) without lying that everything is fine.

**Can one path be both?** No — the separation is the entire point; declare two paths.

## [Core Assumptions]

- **Liveness must be dependency-free.** Confidence: high — industry consensus after repeated restart-storm incidents.
- **Health responses use a tiny, closed schema** (`status` + `checks`). Confidence: medium-high — richer telemetry belongs in metrics, not probes.
- **Specs are maintained next to the implementation.** Confidence: medium — tooling can check conformance but not diligence.
- **Probe traffic is cheap; heavy checks belong in readiness only.** Confidence: high.

As of 2026-10-13.

---

Part of the [zhengming-toolbox](https://github.com/chenhz01/zhengming-toolbox) — 105 purpose-built AI-engineering tools across neglected niches.

Related tools: [latency-budget-spec](https://github.com/chenhz01/latency-budget-spec) · [free-tier-exhaustion-predictor](https://github.com/chenhz01/free-tier-exhaustion-predictor) · [token-price-table-validator](https://github.com/chenhz01/token-price-table-validator)
