# Observability Runbook

This runbook covers the Phase 3 observability baseline for RetainAI.

## What Exists

- JSON application logs with request IDs
- `X-Request-ID` response header propagation
- Prometheus-style metrics at `/metrics`
- Runtime and queue inspection endpoints:
  - `/api/v1/ops/runtime-status`
  - `/api/v1/ops/worker-health`
- Browser E2E coverage for login, queue filtering, and mobile-lite mode
- API smoke script in [smoke_check.py](/C:/Users/Anton/Downloads/RetainAI/scripts/smoke_check.py)

## Key Metrics

- `retainai_http_requests_total`
  - Labels: `method`, `path`, `status`
  - Use for endpoint-level traffic and error-rate alerts
- `retainai_http_request_duration_seconds`
  - Labels: `method`, `path`
  - Use for latency alerts on `/api/v1/model/train`, `/api/v1/connectors/*`, and `/api/v1/risk-cases`
- `retainai_http_requests_in_progress`
  - Use for saturation spikes or hung requests
- `retainai_job_executions_total`
  - Labels: `job_type`, `status`
  - Use for queue failure and dead-letter alerts
- `retainai_job_execution_duration_seconds`
  - Labels: `job_type`, `status`
  - Use to identify slow syncs or retrains
- `retainai_jobs_by_status`
  - Labels: `status`
  - Use for current queue depth
- `retainai_oldest_queue_age_seconds`
  - Alert when queued work is aging beyond the operating target
- `retainai_runtime_policy_violations_total`
  - Alert immediately if non-zero

## Suggested Alerts

- API error rate:
  - Trigger when `5xx` responses exceed 2% for 10 minutes
- Queue degradation:
  - Trigger when `retainai_jobs_by_status{status="dead_letter"}` is greater than `0`
- Stalled work:
  - Trigger when `retainai_oldest_queue_age_seconds` exceeds `900`
- Runtime policy breach:
  - Trigger when `retainai_runtime_policy_violations_total` is greater than `0`
- Worker absence:
  - Trigger when `retainai_workers_detected_total` is `0` in a Celery deployment

## Smoke Check

Use this after deployment, after credential rotation, and after incident recovery:

```powershell
cd C:\Users\Anton\Downloads\RetainAI
npm run smoke:api -- --base-url http://localhost:8000 --email admin@retainai.local --password retainai-demo
```

Expected result:

- `/health`, `/readyz`, and `/metrics` succeed
- login succeeds
- runtime status is returned
- worker health is returned
- logout succeeds

## Failure Triage

1. Check `/readyz`
   - If it fails, the database path is the first problem to solve.
2. Check `/api/v1/ops/runtime-status`
   - If status is `attention`, review residency or deployment-policy violations first.
3. Check `/api/v1/ops/worker-health`
   - If `dead_letter > 0`, inspect `/api/v1/jobs` and the application logs by `job_id`.
4. Check `/metrics`
   - Confirm queue depth and request-failure trends.
5. Re-run [smoke_check.py](/C:/Users/Anton/Downloads/RetainAI/scripts/smoke_check.py) after mitigation.

## Log Review

All application logs now include:

- `timestamp`
- `level`
- `logger`
- `message`
- `request_id`

HTTP request logs also include:

- `event=http.request`
- `method`
- `path`
- `status_code`
- `duration_ms`

Job execution logs also include:

- `event=job.execute`
- `job_type`
- `job_id`
- `status`
- `attempts`
- `duration_ms`
