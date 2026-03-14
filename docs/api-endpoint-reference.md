# API Endpoint Reference

This document is the detailed maintainer and integrator reference for the
RetainAI API.

The shorter overview remains in [api-surface.md](api-surface.md). This file is
the deeper companion document for stewards, deployment engineers, and teams
building integrations.

## Conventions

## Base URL

All application endpoints are exposed under:

`/api/v1`

Health and runtime probe endpoints also exist outside the versioned API:

- `GET /health`
- `GET /livez`
- `GET /readyz`
- metrics path from settings, typically `/metrics`

## Authentication Model

The API supports:

- password login with session-backed JWTs
- OIDC SSO
- trusted-header SSO for controlled deployments

Most operational endpoints require:

```http
Authorization: Bearer <token>
```

## Role Model

Current roles:

- `admin`
- `me_officer`
- `field_coordinator`
- `country_director`

Role expectations in practice:

- `admin`: full platform and security administration
- `me_officer`: model, validation, program settings, and analytics control
- `field_coordinator`: operational queue use and intervention logging
- `country_director`: supervisory visibility and selected export/report actions

Exact enforcement is implemented in [main.py](/C:/Users/Anton/Downloads/RetainAI/apps/api/app/main.py) and [auth.py](/C:/Users/Anton/Downloads/RetainAI/apps/api/app/services/auth.py).

## Response Style

The API is primarily JSON-based.

Typical failure format:

```json
{
  "detail": "Human-readable error message"
}
```

## Section Map

1. health and runtime probes
2. authentication and sessions
3. programs and settings
4. ingestion and import analysis
5. connectors and embedded operations
6. jobs and automation
7. dashboard, queue, and interventions
8. governance and exports
9. model lifecycle and validation
10. synthetic data and benchmarking helpers
11. audit and runtime administration

## 1. Health And Runtime Probes

### `GET /health`

Purpose:

- lightweight deployment summary for simple health checks and smoke tools

Response model:

- `HealthResponse`

Typical fields:

- status
- environment
- database_configured
- programs

### `GET /livez`

Purpose:

- liveness probe suitable for containers and orchestration platforms

Response model:

- `ProbeResponse`

### `GET /readyz`

Purpose:

- readiness probe that returns degraded or failure semantics when the app is not
  ready to serve traffic safely

Response model:

- `ProbeResponse`

### `GET /metrics`

Purpose:

- Prometheus-style metrics endpoint

Typical use:

- infrastructure scraping
- operator dashboards

## 2. Authentication And Sessions

### `POST /api/v1/auth/login`

Purpose:

- authenticate a user with email and password

Auth:

- public

Request body:

```json
{
  "email": "me.officer@example.org",
  "password": "correct horse battery staple"
}
```

Response model:

- `TokenResponse`

Typical response:

```json
{
  "access_token": "...",
  "token_type": "bearer",
  "expires_in_seconds": 3600,
  "session_id": "uuid",
  "user": {
    "id": "uuid",
    "full_name": "M&E Officer",
    "email": "me.officer@example.org",
    "role": "me_officer",
    "is_active": true,
    "created_at": "2026-03-14T12:00:00Z"
  }
}
```

Operational notes:

- login is throttled
- session limits may apply
- an audit trail is created

### `GET /api/v1/auth/me`

Purpose:

- return the current authenticated user

Auth:

- bearer token required

Response model:

- `CurrentUser`

### `GET /api/v1/auth/sessions`

Purpose:

- list active sessions for the current user

Auth:

- bearer token required

Response model:

- list of `SessionRecord`

### `POST /api/v1/auth/logout`

Purpose:

- revoke the current session

Auth:

- bearer token required

Response model:

- `LogoutResponse`

### `GET /api/v1/auth/sso/config`

Purpose:

- expose frontend-readable SSO configuration state

Auth:

- usually public to support the login screen

Response model:

- `SSOConfigRead`

### `POST /api/v1/auth/sso/header-login`

Purpose:

- trusted-header login path for deployments behind an authenticated reverse
  proxy or identity gateway

Security note:

- should only be enabled in tightly controlled deployments

### `GET /api/v1/auth/sso/oidc/start`

Purpose:

- begin the OIDC login flow and return the redirect URL or exchange metadata

Response model:

- `SSOOidcStartRead`

### `POST /api/v1/auth/sso/oidc/exchange`

Purpose:

- exchange an authorization code for a RetainAI session

Response model:

- `TokenResponse`

## 3. Programs And Settings

### `GET /api/v1/programs`

Purpose:

- list configured programs

Auth:

- authenticated user

Response model:

- list of `ProgramRead`

### `POST /api/v1/programs`

Purpose:

- create a new program

Typical roles:

- `admin`
- `me_officer`

Request body example:

```json
{
  "name": "Northern Region ART Retention",
  "program_type": "Health",
  "country": "Uganda",
  "delivery_modality": "Appointment-based"
}
```

### `GET /api/v1/program-settings`

Purpose:

- list operational settings for all programs

Response model:

- list of `ProgramOperationalSettingRead`

### `PUT /api/v1/program-settings/{program_id}`

Purpose:

- update operational settings such as label presets, capacity assumptions, and
  escalation behavior

Typical roles:

- `admin`
- `me_officer`

Important fields typically include:

- label definition preset
- dropout inactivity days
- prediction window days
- worker count
- weekly follow-up capacity
- escalation thresholds
- support-channel defaults

### `GET /api/v1/program-validation`

Purpose:

- list validation settings per program

### `PUT /api/v1/program-validation/{program_id}`

Purpose:

- update shadow-mode and evaluation expectations for a program

Important fields include:

- shadow mode enabled
- shadow prediction window days
- minimum precision at capacity
- minimum recall at capacity
- fairness review requirement

### `GET /api/v1/program-data-policies`

Purpose:

- list data policy records for all programs

### `PUT /api/v1/program-data-policies/{program_id}`

Purpose:

- update residency, storage, and privacy-policy settings

Typical roles:

- `admin`
- selected governance-capable operators depending on deployment policy

## 4. Ingestion And Import Analysis

### `GET /api/v1/imports`

Purpose:

- list import batches

Response model:

- list of `ImportBatchRead`

### `POST /api/v1/imports/analyze`

Purpose:

- inspect a CSV or XLSX file before import

Use cases:

- inferred field mapping
- duplicate and anomaly review
- data-quality issue surfacing before persistence

Response model:

- `ImportAnalysisRead`

### `POST /api/v1/imports/upload`

Purpose:

- import beneficiary or event data using a validated or user-supplied mapping

Expected input:

- multipart form with file and associated metadata

Operational note:

- this endpoint is central to partner-data onboarding and operator workflows

### `GET /api/v1/imports/{import_batch_id}/issues`

Purpose:

- retrieve ETL and quality issues for one import batch

Response model:

- list of `DataQualityIssueRecord`

## 5. Connectors And Embedded Operations

### `GET /api/v1/connectors`

Purpose:

- list configured connectors

Response model:

- list of `DataConnectorRead`

### `POST /api/v1/connectors`

Purpose:

- create a connector for one program

Supported connector types:

- KoboToolbox
- CommCare
- ODK Central
- DHIS2
- Salesforce NPSP

### `POST /api/v1/connectors/preview`

Purpose:

- preview a connector configuration without persisting it

Use cases:

- test record path assumptions
- inspect sample headers
- review inferred mapping and warnings

Response model:

- `ConnectorProbeResult`

### `PUT /api/v1/connectors/{connector_id}`

Purpose:

- update an existing connector definition

### `POST /api/v1/connectors/{connector_id}/test`

Purpose:

- probe an already-saved connector

Response model:

- `ConnectorProbeResult`

### `POST /api/v1/connectors/{connector_id}/sync`

Purpose:

- queue or trigger a connector sync

Response model:

- `JobRead`

Operational note:

- depending on deployment mode, this may enqueue background work instead of
  executing inline

### `GET /api/v1/connectors/sync-runs`

Purpose:

- inspect connector sync history

Response model:

- list of `ConnectorSyncRunRead`

### `GET /api/v1/connectors/dispatch-runs`

Purpose:

- inspect write-back / dispatch history

Response model:

- list of `ConnectorDispatchRunRead`

### `POST /api/v1/connectors/{connector_id}/dispatch`

Purpose:

- write a queue slice back into an upstream system

This is one of the most strategically important endpoints because it supports
the embedded-operations approach rather than forcing all work into the RetainAI
dashboard.

## 6. Jobs And Automation

### `GET /api/v1/jobs`

Purpose:

- list background jobs

Response model:

- list of `JobRead`

### `POST /api/v1/jobs/run-pending`

Purpose:

- manually trigger pending jobs in lightweight-worker style deployments

### `POST /api/v1/jobs/{job_id}/requeue`

Purpose:

- requeue a failed or dead-lettered job

### `GET /api/v1/model/schedule`

Purpose:

- retrieve current retraining schedule

### `PUT /api/v1/model/schedule`

Purpose:

- update retraining cadence and auto-retrain behavior

### `POST /api/v1/automation/run-due`

Purpose:

- enqueue all due sync and automation work

Typical roles:

- `admin`
- `me_officer`

## 7. Dashboard, Queue, And Interventions

### `GET /api/v1/dashboard/summary`

Purpose:

- fetch the summary metrics shown on the main dashboard

Response model:

- `DashboardSummary`

### `GET /api/v1/risk-cases`

Purpose:

- return the risk queue

Response model:

- list of `RiskCase`

Typical query uses:

- program filter
- region filter
- cohort filter
- phase filter
- risk-level filter
- search

### `GET /api/v1/interventions`

Purpose:

- list logged interventions

Response model:

- list of `InterventionRecord`

### `POST /api/v1/interventions`

Purpose:

- create a new intervention or workflow action

This is part of the core `flag -> action -> verification -> outcome` loop.

### `PATCH /api/v1/interventions/{intervention_id}`

Purpose:

- update workflow state, verification outcome, success, dismissal, or closure

### `GET /api/v1/interventions/effectiveness`

Purpose:

- summarize what kinds of interventions appear to work in the current data

Response model:

- `InterventionEffectivenessSummary`

## 8. Governance, Beneficiary Rights, And Exports

### `GET /api/v1/beneficiaries/governance`

Purpose:

- list beneficiary governance records

### `PATCH /api/v1/beneficiaries/{beneficiary_id}/governance`

Purpose:

- update beneficiary governance state

### `GET /api/v1/beneficiaries/{beneficiary_id}/explanation`

Purpose:

- fetch a beneficiary-facing explanation sheet or explanation payload

### `GET /api/v1/governance/alerts`

Purpose:

- list safeguard or misuse alerts for review

### `POST /api/v1/exports/risk-cases`

Purpose:

- export risk cases, usually with privacy controls applied

### `POST /api/v1/exports/interventions`

Purpose:

- export intervention records, subject to governance and masking rules

### `POST /api/v1/exports/followup/whatsapp`

Purpose:

- export a WhatsApp-ready follow-up list

### `POST /api/v1/exports/followup/sms`

Purpose:

- export an SMS-ready follow-up list

### `POST /api/v1/exports/followup/field-visits`

Purpose:

- export a field-visit-oriented list

Governance note across all exports:

- export behavior is intentionally not "raw dump everything"
- policy, role, masking, and residency checks matter here

## 9. Model Lifecycle And Validation

### `GET /api/v1/model/status`

Purpose:

- retrieve the currently deployed model's status

Response model:

- `ModelStatus`

Typical contents:

- algorithm
- readiness status
- metrics
- fairness summary
- threshold information
- training coverage

### `POST /api/v1/model/train`

Purpose:

- queue or trigger model training

Response model:

- `JobRead`

### `GET /api/v1/model/drift`

Purpose:

- return the latest drift report

### `GET /api/v1/feature-store/summary`

Purpose:

- summarize persisted feature snapshots and related training/scoring artifacts

### `POST /api/v1/model/evaluate/backtest`

Purpose:

- run the formal backtest harness from the API

Request body typically includes:

- temporal strategy
- horizon days
- holdout share
- rolling folds
- top-k share or capacity assumptions
- calibration bins
- bootstrap iterations
- optional program or cohort scoping

Response model:

- `ModelEvaluationReport`

### `GET /api/v1/model/evaluations`

Purpose:

- list persisted evaluation reports

Response model:

- list of `ModelEvaluationRecordRead`

### `POST /api/v1/program-validation/{program_id}/shadow-runs`

Purpose:

- create a shadow run for one program

### `GET /api/v1/program-validation/shadow-runs`

Purpose:

- list shadow runs

## 10. Federated Learning

### `GET /api/v1/federated/status`

Purpose:

- summarize the state of the federated-learning subsystem

### `GET /api/v1/federated/rounds`

Purpose:

- list federated learning rounds

### `POST /api/v1/federated/export-update`

Purpose:

- export a local federated model update

### `POST /api/v1/federated/aggregate`

Purpose:

- aggregate contributed federated updates

Important note:

- this is a practical update-exchange path, not a claim of full secure
  aggregation

## 11. Synthetic Data And Benchmark Helpers

### `GET /api/v1/synthetic/portfolio`

Purpose:

- return synthetic portfolio summaries for demo or stress contexts

### `GET /api/v1/synthetic/stress-scenarios`

Purpose:

- list available synthetic stress scenarios

### `GET /api/v1/synthetic/stress-summary`

Purpose:

- summarize synthetic stress outputs already produced by the backend

## 12. Retention Analytics And Reports

### `GET /api/v1/retention/curves`

Purpose:

- fetch plain-language retention curves

### `GET /api/v1/retention/analytics`

Purpose:

- fetch aggregate retention analytics, breakdowns, and trends

### `GET /api/v1/reports/donor-summary`

Purpose:

- fetch the donor-oriented JSON summary

### `GET /api/v1/reports/donor-summary.xlsx`

Purpose:

- download donor-ready Excel output

### `GET /api/v1/reports/donor-summary.pdf`

Purpose:

- download donor-ready PDF output

## 13. Runtime Administration And Audit

### `GET /api/v1/ops/runtime-status`

Purpose:

- return runtime policy and deployment status

### `GET /api/v1/ops/worker-health`

Purpose:

- show queue and worker health

### `GET /api/v1/audit-logs`

Purpose:

- list audit events

## Example Integration Sequences

### Example: partner file import

1. `POST /api/v1/imports/analyze`
2. review inferred mapping and issues
3. `POST /api/v1/imports/upload`
4. `GET /api/v1/imports/{id}/issues`
5. `GET /api/v1/risk-cases`

### Example: queue-driven intervention workflow

1. `GET /api/v1/risk-cases`
2. `POST /api/v1/interventions`
3. `PATCH /api/v1/interventions/{id}`
4. `GET /api/v1/interventions`
5. `GET /api/v1/interventions/effectiveness`

### Example: model validation before shadow mode

1. `PUT /api/v1/program-validation/{program_id}`
2. `POST /api/v1/model/evaluate/backtest`
3. `GET /api/v1/model/evaluations`
4. `POST /api/v1/program-validation/{program_id}/shadow-runs`
5. `GET /api/v1/program-validation/shadow-runs`

### Example: embedded operations through CommCare or DHIS2

1. `POST /api/v1/connectors`
2. `POST /api/v1/connectors/{id}/test`
3. `POST /api/v1/connectors/{id}/sync`
4. `POST /api/v1/connectors/{id}/dispatch`
5. `GET /api/v1/connectors/dispatch-runs`

## Maintainer Notes

- Treat this reference as descriptive, not normative. The actual contract is the
  FastAPI schema layer and route implementation.
- When routes change, update this file together with [api-surface.md](api-surface.md).
- If a route changes privacy or governance behavior, also update:
  - [privacy-and-safeguards.md](privacy-and-safeguards.md)
  - [data-governance-and-retention.md](data-governance-and-retention.md)
  - [dpga-audit-evidence.md](dpga-audit-evidence.md)

## Related Documents

- [API Surface](api-surface.md)
- [Backend Code Reference](backend-code-reference.md)
- [Workflow Reference](workflow-reference.md)
