# Monitoring Guide

## Signals the platform emits

| Signal | Where | Notes |
|---|---|---|
| Liveness | `GET /api/v1/health` | process up |
| Readiness | `GET /api/v1/health/ready` | real DB `SELECT 1` + Redis `PING`; 503 gates load balancers |
| LLM / embedding smoke | `GET /api/v1/health/llm`, `/health/embedding` | provider reachability, never 5xx |
| Remote-support provider | `GET /api/v1/remote-support/provider/health` | Graph reachability (real provider) |
| Prometheus metrics | `GET /api/v1/health/metrics` | `http_requests_total`, `http_request_duration_seconds` by method/route/status. Blocked at nginx — scrape the backend directly on the internal network |
| Structured logs | stdout (JSON in production) | one `http_request` line per request (method, route template, status, duration_ms) plus domain events below |
| Tracing (opt-in) | `OTEL_ENABLED=true` → OTLP to `OTEL_EXPORTER_ENDPOINT` | optional; requires otel packages in the image |

## Log events worth alerting on

| Event | Meaning | Suggested alert |
|---|---|---|
| `production_config_violation` | boot refused — bad config | page immediately (deploy is down) |
| `token_denylist_unavailable` | Redis down; revocation degraded (fail-open) | warn > 5/min |
| `rate_limit_redis_unavailable` | limiter degraded to per-process window | warn |
| `rate_limit_exceeded` | client throttled | info; alert on sustained bursts against `bucket=auth` (credential stuffing) |
| `idle_sweeper_pass_failed` / `remote_session_sweeper_pass_failed` | background job failing | warn > 3 consecutive |
| `remote_consent_revoked` | employee pulled consent mid-session | audit review, not an alert |
| `scheduled_job_iteration_failed` | any background loop error | warn |
| `llm_json_parse_failed` | model output degraded | trend, alert on spike |

## Metric-based alerts (Prometheus)

- `rate(http_requests_total{status=~"5.."}[5m]) > 1%` of traffic → page.
- p95 `http_request_duration_seconds{path="/api/v1/chat/message"}` > 10s
  → warn (LLM latency regression).
- Readiness probe failing > 2 min → page.
- Absence of scrape (target down) → page.

## Domain health (SQL / admin console)

- Specialist queue age: unclaimed handoffs > 10 min during business hours.
- Remote sessions stuck `consent_pending` past deadline (sweeper should
  expire them; presence indicates sweeper failure).
- Audit-event volume dropping to zero while traffic continues (audit
  pipeline break).

## Dashboards

Admin console (`/dashboard`) carries the product-level analytics (SLA
compliance, queue workload, resolution rates). Infrastructure dashboards
should be built from the Prometheus metrics + container stats; keep the
route-template label set small (it is bounded by the API surface).
