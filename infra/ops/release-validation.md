# Release Validation

This checklist is the minimum validation bar before calling a RetainAI deployment pilot-ready.

## Automated Gates

- GitHub Actions CI must pass:
  - backend pytest suite
  - frontend production build
  - Playwright browser suite
  - Docker Compose config validation
  - Terraform fmt/validate
- Dependency audit baseline:
  - `npm --prefix apps/web audit`
  - backend dependencies reviewed through Dependabot updates and pinned requirements

## Local Compose Validation

Run the full local smoke workflow:

```powershell
cd C:\Users\Anton\Downloads\RetainAI
python scripts\compose_smoke.py --base-url http://127.0.0.1:8000
```

This should:

- bring up PostgreSQL, Redis, migrate, API, worker, and web
- wait for `/health`, `/readyz`, and `/metrics`
- log in with the seeded admin account
- verify runtime status and worker health
- tear the stack down cleanly unless `--keep-running` is set

## Queue Recovery Check

For each release candidate, validate that dead-letter recovery still works:

1. force a job into `dead_letter`
2. re-queue it through `POST /api/v1/jobs/{job_id}/requeue`
3. confirm the job returns to `queued`
4. confirm the worker can execute it successfully

## Cloud Validation

Before a production cut:

1. `terraform apply` into the target environment
2. run Alembic migrations
3. deploy the Kubernetes manifest set
4. verify ingress, TLS, and probe health
5. run the API smoke script against the public hostname
6. perform one backup/restore drill
7. perform one worker-failure drill

## Rollback Readiness

Every release candidate must have:

- the previous container image digest recorded
- the previous Terraform state and plan saved
- the current DB backup timestamp captured
- the rollback operator identified in advance
