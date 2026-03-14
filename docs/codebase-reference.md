# Codebase Reference

This document is the maintainer's navigation map for the RetainAI repository.
It is intentionally practical. The goal is to answer:

- Where does a given workflow start?
- Which files own domain logic vs. transport logic vs. presentation logic?
- What should a future steward read first before changing a subsystem?

For higher-level context, read [Project Overview](project-overview.md) and
[System Architecture](architecture.md) first. This document assumes the reader
is already inside the codebase and wants a working map.

## Repository Layout

```text
RetainAI/
|- apps/
|  |- api/                  FastAPI service, ML pipeline, persistence, jobs
|  `- web/                  React + TypeScript dashboard and mobile-lite UI
|- docs/                    Narrative docs, governance docs, implementation docs
|- examples/                CSV templates and bundle templates
|- infra/                   Kubernetes, Terraform, and operator runbooks
|- scripts/                 Evaluation, dataset-fetching, validation, smoke tools
|- data/                    Generated public and synthetic benchmark assets
|- .github/                 CI and dependency automation
`- docker-compose.yml       Local self-hosted stack
```

## Recommended Reading Order For New Maintainers

If you are inheriting the project, use this sequence rather than opening files
at random:

1. [README.md](../README.md)
2. [docs/project-overview.md](project-overview.md)
3. [docs/architecture.md](architecture.md)
4. [docs/backend-code-reference.md](backend-code-reference.md)
5. [docs/frontend-code-reference.md](frontend-code-reference.md)
6. [docs/workflow-reference.md](workflow-reference.md)
7. [docs/data-and-ml.md](data-and-ml.md)
8. [docs/model-governance.md](model-governance.md)
9. [docs/privacy-and-safeguards.md](privacy-and-safeguards.md)
10. [docs/deployment-and-operations.md](deployment-and-operations.md)

## Ownership Boundaries

The repository is organized around a few strong boundaries.

### Backend API and service layer

Lives in `apps/api/app`.

- `main.py` owns the HTTP surface and route composition.
- `schemas.py` owns the public API contract.
- `models.py` owns the persistence model.
- `services/` owns business logic, model logic, governance logic, and async job
  behavior.
- `core/` owns configuration, observability, and shared utilities.

### Frontend dashboard

Lives in `apps/web/src`.

- `App.tsx` is the orchestration shell.
- `api.ts` owns network calls and token handling.
- `types.ts` mirrors backend response models.
- `components/` owns extracted UI sections.
- `MobileLiteView.tsx` is the constrained field-oriented surface.

### Evaluation and validation tooling

Lives primarily in `apps/api/app/services/evaluation.py` and `scripts/`.

- The backend service persists evaluation reports and shadow runs.
- The scripts provide batch tooling for public benchmarks, partner bundles,
  synthetic stress runs, and cross-segment validation.

### Deployment and runtime operations

Lives in `docker-compose.yml`, `infra/`, and `apps/api/app/services/operations.py`.

- Compose supports local and simple self-hosted installs.
- Kubernetes and Terraform in `infra/` support more formal deployments.
- Runtime-health logic stays in the API so operational status is visible in-app.

## Code Paths By Question

Use the following shortcuts when investigating a behavior.

### "Why did this beneficiary appear in the risk queue?"

Start here:

1. `apps/api/app/services/analytics.py`
2. `apps/api/app/services/scoring.py`
3. `apps/api/app/services/modeling.py`
4. `apps/web/src/components/RiskQueueSection.tsx`

### "How is dropout / disengagement defined for this program?"

Start here:

1. `apps/api/app/models.py` (`ProgramOperationalSetting`)
2. `apps/api/app/services/analytics.py`
3. `apps/web/src/components/OperationsSection.tsx`

### "How does a connector sync or write back to CommCare / DHIS2?"

Start here:

1. `apps/api/app/services/connectors.py`
2. `apps/api/app/main.py`
3. `apps/web/src/components/ConnectorAutomationSection.tsx`

### "How are backtests and shadow runs persisted?"

Start here:

1. `apps/api/app/services/evaluation.py`
2. `apps/api/app/models.py` (`EvaluationReport`, `ShadowRun`, `ShadowRunCase`)
3. `apps/web/src/components/ValidationSection.tsx`
4. `scripts/run_model_backtest.py`

### "How do auth, sessions, and SSO work?"

Start here:

1. `apps/api/app/services/auth.py`
2. `apps/api/app/services/sso.py`
3. `apps/api/app/main.py`
4. `apps/web/src/components/AuthScreen.tsx`

### "Where are privacy and governance controls enforced?"

Start here:

1. `apps/api/app/services/governance.py`
2. `apps/api/app/services/privacy.py`
3. `apps/api/app/services/audit.py`
4. `apps/web/src/components/GovernanceSection.tsx`

## Cross-Cutting Concerns

Several concerns appear across multiple modules and should be treated as shared
contracts rather than isolated implementation details.

### Time handling

- Shared helpers: `apps/api/app/core/time.py`
- Reason: consistent UTC handling across jobs, shadow runs, exports, and audit
  events

### Configuration

- Shared helpers: `apps/api/app/core/config.py`
- Reason: the same settings object affects auth, queue backends, modelops,
  federation, storage, and privacy controls

### Observability

- Shared helpers: `apps/api/app/core/observability.py`
- Routes: `apps/api/app/main.py`
- Worker integration: `apps/api/worker.py`

### Auditability

- Model: `apps/api/app/models.py` (`AuditLog`)
- Write path: `apps/api/app/services/audit.py`
- Route usage: scattered through `apps/api/app/main.py`

## What To Read Before Editing Major Areas

### Before editing model training

Read:

- [docs/data-and-ml.md](data-and-ml.md)
- [docs/model-governance.md](model-governance.md)
- `apps/api/app/services/modeling.py`
- `apps/api/app/services/evaluation.py`

### Before editing queue logic or intervention workflows

Read:

- [docs/workflow-reference.md](workflow-reference.md)
- `apps/api/app/services/analytics.py`
- `apps/api/app/main.py`
- `apps/web/src/components/RiskQueueSection.tsx`

### Before editing connectors

Read:

- [docs/interoperability-and-open-standards.md](interoperability-and-open-standards.md)
- `apps/api/app/services/connectors.py`
- `apps/api/app/services/imports.py`

### Before editing privacy or export behavior

Read:

- [docs/privacy-and-safeguards.md](privacy-and-safeguards.md)
- [docs/data-governance-and-retention.md](data-governance-and-retention.md)
- `apps/api/app/services/privacy.py`
- `apps/api/app/services/governance.py`

## Common Maintainer Pitfalls

- Do not change a backend schema without updating `apps/web/src/types.ts`.
- Do not add a new route in `main.py` without considering audit logging and
  role enforcement.
- Do not change queue ranking logic without re-running the evaluation harness.
- Do not change export fields without re-checking privacy and tokenization
  rules.
- Do not treat synthetic or public benchmark results as production evidence.

## Related Documents

- [Backend Code Reference](backend-code-reference.md)
- [Frontend Code Reference](frontend-code-reference.md)
- [Workflow Reference](workflow-reference.md)
- [Deployment and Operations](deployment-and-operations.md)
- [Research and Validation](research-evidence-and-validation.md)
