# Deployment and Operations

## Deployment Philosophy

RetainAI is intended first for self-hosted or steward-hosted deployments in environments that require strong control over beneficiary data.

The repository supports:

- local development
- on-premise or NGO-managed cloud deployment
- cloud-managed infrastructure where the operator controls the data environment

## Supported Runtime Modes

### Local development

- SQLite or local Postgres
- local worker
- Vite web app

### Self-hosted production-style deployment

- API service
- web service
- worker service
- Postgres
- optional Redis / Celery path
- persistent artifact storage

### Kubernetes and Terraform path

The repository includes:

- Kubernetes manifests for API, worker, web, PVCs, probes, and ingress scaffolding
- Terraform for AWS infrastructure scaffolding
- operational runbooks for deployment, backup, and release checks

These assets should be treated as a strong starting point, not a substitute for environment-specific validation.

## Key Configuration Areas

Operators should review:

- database URL and storage backend
- JWT/session settings
- connector secret keys
- privacy tokenization keys
- federated exchange keys
- CORS and trusted host controls
- region and residency settings
- SSO mode
- job backend

## Runtime Endpoints

Relevant endpoints include:

- `/health`
- `/livez`
- `/readyz`
- `/metrics`
- `/api/v1/ops/runtime-status`
- `/api/v1/ops/worker-health`

These endpoints support automation, smoke tests, and operator review.

## Operational Runbooks

Detailed runbooks live in:

- [../infra/ops/deployment-runbook.md](../infra/ops/deployment-runbook.md)
- [../infra/ops/backup-disaster-recovery.md](../infra/ops/backup-disaster-recovery.md)
- [../infra/ops/observability-runbook.md](../infra/ops/observability-runbook.md)
- [../infra/ops/release-validation.md](../infra/ops/release-validation.md)

## Required Pre-Go-Live Checks

Before production use, operators should complete:

1. infrastructure deployment validation
2. TLS and ingress validation
3. backup and restore drill
4. role and access review
5. SSO review if used
6. export and audit review
7. model validation review
8. shadow-mode review
9. incident and support ownership assignment

## Testing and Validation Tooling

The repository includes:

- `python -m pytest`
- `npm --prefix apps/web run build`
- `npm --prefix apps/web run test:e2e`
- `scripts/compose_smoke.py`
- model and partner validation scripts

## Current Operational Limits

Documented limits remain:

- real deployment validation is environment-specific
- connector write-back should be tested against real partner systems before live use
- federated-learning exchange is still lighter than secure aggregation
- some third-party dependency warnings remain and should be monitored

## Recommended Production Sequence

1. deploy infrastructure
2. load seeded or synthetic data in a non-sensitive environment
3. run smoke checks
4. validate auth, sessions, and RBAC
5. validate connectors and write-back
6. load partner data
7. run retrospective evaluation
8. run shadow mode
9. approve live decision support
