# Backend Code Reference

This document describes the structure and responsibilities of the FastAPI,
SQLAlchemy, ML, governance, and job-execution code in `apps/api/app`.

It is not a line-by-line walkthrough. Instead, it explains what each major
module owns, how modules depend on one another, and where to investigate when a
backend behavior is unclear.

## Backend Topology

```text
apps/api/app/
|- main.py                 FastAPI app and route registration
|- schemas.py              Public request / response models
|- models.py               SQLAlchemy persistence models
|- db.py                   Engine and session bootstrap
|- seed.py                 Local demo / dev seed data
|- core/
|  |- config.py            Environment configuration
|  |- observability.py     Request IDs, metrics, structured logging
|  `- time.py              UTC helpers and timestamp normalization
`- services/
   |- analytics.py         Queue building, retention summaries, donor exports
   |- auth.py              Login, JWTs, sessions, role checks
   |- connectors.py        External system sync, preview, write-back
   |- evaluation.py        Backtests, shadow runs, evaluation persistence
   |- imports.py           File ingestion, mapping, validation, ETL issues
   |- jobs.py              Job lifecycle and execution dispatch
   |- modeling.py          Features, training, scoring, explainability
   |- governance.py        Consent, misuse safeguards, governance actions
   |- privacy.py           Tokenization, residency-aware checks, export policy
   `- ...                  Other specialized helpers
```

## Primary Entry Modules

### `main.py`

`main.py` is the HTTP entrypoint. It should remain thin in principle, though the
file is large because the project covers many workflows. Its responsibilities
are:

- configure the FastAPI app, middleware, and startup/shutdown lifecycle
- declare routes and dependency injection
- enforce role checks and call the right service functions
- record audit events where appropriate
- return schema-backed responses

What it should not do:

- heavy business logic
- feature engineering
- query orchestration more suitable for service modules
- privacy-policy calculations that belong in governance/privacy services

When editing routes, check:

- does the route need role restrictions?
- does it need an audit event?
- should it be delegated to an existing service instead of adding logic inline?
- does the frontend type layer need to change?

### `schemas.py`

`schemas.py` is the public contract layer for the API.

Why it matters:

- drives FastAPI response validation
- shapes OpenAPI generation
- acts as the source contract for `apps/web/src/types.ts`
- defines what external integrators can rely on

Because of that, schema edits should be treated as API changes, not internal
refactors.

### `models.py`

`models.py` is the persistence backbone. It is intentionally broad because
RetainAI is an end-to-end platform sharing one operational datastore.

The model groups are:

- operational domain models: `Program`, `Beneficiary`, `MonitoringEvent`,
  `Intervention`, `ImportBatch`
- platform and security models: `User`, `UserSession`, `AuditLog`,
  `JobRecord`, `DataConnector`
- model governance and evidence models: `ModelVersion`, `ModelBiasAudit`,
  `ModelDriftReport`, `EvaluationReport`, `ShadowRun`, `ShadowRunCase`
- privacy and policy models: `ProgramDataPolicy`, governance-related flags,
  consent fields

Treat model changes carefully because they often affect:

- migrations
- seed data
- frontend types
- export logic
- evaluation logic

## Core Services

### `services/analytics.py`

This module powers the operational dashboard and many export/report surfaces.

It owns:

- risk-case assembly
- queue filtering
- intervention serialization
- retention summaries and curves
- donor-oriented report generation
- program operational settings views

If a user-facing queue item "looks wrong," this file is usually the first place
to inspect.

### `services/scoring.py`

This module contains small scoring helpers that translate model output into
operational categories and human-usable actions.

It is intentionally narrower than `modeling.py`. The split is:

- `modeling.py`: estimation, features, model bundles, metrics
- `scoring.py`: operational interpretation, risk buckets, recommendations

### `services/modeling.py`

This is the heaviest backend module. It covers:

- feature-context construction from beneficiary histories
- training sample preparation
- model-family fitting and selection
- transfer/base-model blending
- SHAP-based explanation generation
- fairness and drift summaries
- deployed-model loading and compatibility handling

When changing this file, you must consider:

- evaluation methodology
- artifact compatibility
- fairness behavior
- frontend explanation expectations
- MLflow logging side effects

### `services/evaluation.py`

This module turns the system from a predictor into a validation-capable tool.

It owns:

- temporal holdout and rolling evaluation logic
- persisted evaluation reports
- cross-segment / segment-holdout style logic
- shadow-run creation and later maturation against observed outcomes

Any change to training or queue ranking should be considered incomplete until
evaluation behavior is reviewed here.

### `services/imports.py`

This module handles structured file ingestion.

It owns:

- CSV/XLSX analysis
- inferred mapping and validation
- ETL issue detection
- beneficiary and event import application

It is the file to inspect when a partner-data bundle fails validation or when
connector payloads need to be normalized into the internal beneficiary/event
shape.

### `services/connectors.py`

This module covers both read integration and write-back integration.

It owns:

- connector creation and probe behavior
- sync execution and sync history
- schema preview and inferred mapping
- queue dispatch payload generation
- embedded-operations write-back to upstream systems

That makes it both an ingestion adapter layer and an operations-integration
layer.

### `services/auth.py`

This module owns authentication, session lifecycle, and role checks.

Key concepts:

- users can have multiple active sessions
- JWTs are session-backed, not purely stateless
- token rotation and session revocation are part of the model
- route role checks should use shared helpers instead of ad hoc comparisons

### `services/governance.py` and `services/privacy.py`

These modules enforce the "do no harm" posture of the platform.

Typical responsibilities include:

- beneficiary opt-out / consent handling
- explanation and export safeguards
- pseudonymization / tokenization
- residency-aware export blocking
- misuse alerting

Any export, visibility, or beneficiary-rights change should be checked here.

### `services/jobs.py`

This module is the abstraction layer over background execution.

It owns:

- job record creation
- retry and dead-letter transitions
- dispatch to the actual work implementation
- shared behavior between lightweight worker mode and Celery mode

When debugging async behavior, start here, then inspect `worker.py`,
`celery_worker.py`, and `services/job_tasks.py`.

## Supporting Services

### `services/automation.py`

Small scheduling helper for retraining cadence and sync-triggered model updates.

### `services/modelops.py`

MLflow-specific run logging and tracking behavior.

### `services/nlp.py`

Optional note-sentiment analysis with a transformer-first but fallback-safe
implementation.

### `services/federated.py`

Federated-learning exchange, payload protection, and aggregation helpers.

### `services/operations.py`

Runtime-status calculations shown in operational dashboards and health views.

### `services/secrets.py`

Encryption and masking helpers for connector and integration credentials.

### `services/sso.py`

OIDC exchange logic for optional single sign-on deployments.

### `services/synthetic_data.py`

Synthetic portfolio generation used for demos, regression benchmarks, and
stress scenarios. Not a substitute for real validation.

## Data Flow Through The Backend

### 1. Ingestion path

1. file upload or connector fetch reaches `main.py`
2. request is validated against `schemas.py`
3. `services/imports.py` or `services/connectors.py` normalizes the payload
4. SQLAlchemy models in `models.py` persist the result
5. analytics and modeling later consume those persisted events

### 2. Queue-generation path

1. `services/analytics.py` loads beneficiaries and related histories
2. `services/modeling.py` builds feature contexts and scores cases
3. `services/scoring.py` converts scores to operational risk levels
4. `services/analytics.py` returns queue records to `main.py`
5. frontend consumes them through `api.ts`

### 3. Validation path

1. evaluation route in `main.py` receives settings
2. `services/evaluation.py` builds temporal snapshots and folds
3. `services/modeling.py` trains / scores within those constraints
4. metrics, fairness summaries, and calibration outputs are persisted
5. results return through schemas and appear in the validation UI

## Persistence Notes

RetainAI uses SQLAlchemy ORM models with Alembic migrations.

When adding fields:

1. update `models.py`
2. add or edit the Alembic migration
3. update `schemas.py` if exposed through the API
4. update seeds if local demo data should exercise the new path
5. update frontend types if the UI reads the field

## Backend Testing Surfaces

Main backend verification layers:

- `apps/api/tests/test_api_flows.py` for API workflows and regressions
- Alembic migration upgrades for schema compatibility
- dataset / evaluation scripts in `scripts/` for validation workflows

When to add tests:

- any new route or route behavior
- any change in queue ranking or intervention workflow state handling
- any change in connector dispatch semantics
- any change in evaluation metrics or shadow-mode maturation logic

## Editing Guidelines For Future Stewards

- Prefer adding behavior in services over growing `main.py`.
- Keep privacy and governance checks centralized.
- Avoid mixing modeling assumptions into frontend code.
- Do not let public benchmark results stand in for real deployment evidence.
- If a change affects queue ranking, update docs and rerun validation tooling.

## Related Documents

- [Codebase Reference](codebase-reference.md)
- [Frontend Code Reference](frontend-code-reference.md)
- [Workflow Reference](workflow-reference.md)
- [Data and ML](data-and-ml.md)
- [Deployment and Operations](deployment-and-operations.md)
