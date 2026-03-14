# API Surface

## Overview

The backend exposes a REST-style API under `/api/v1`. The API is intended for:

- the first-party web dashboard
- automation and smoke checks
- connector orchestration
- evaluation and validation tooling
- future integration into existing NGO systems

## Authentication

Primary auth modes supported by the product stack:

- password login with JWT session issuance
- OIDC SSO
- trusted-header SSO for controlled deployments

Relevant endpoints:

- `POST /api/v1/auth/login`
- `POST /api/v1/auth/logout`
- `GET /api/v1/auth/me`
- `GET /api/v1/auth/sessions`
- `GET /api/v1/auth/sso/config`
- `GET /api/v1/auth/sso/oidc/start`
- `POST /api/v1/auth/sso/oidc/exchange`

## Core Operational Endpoints

### Programs and settings

- `GET /api/v1/programs`
- `POST /api/v1/programs`
- `GET /api/v1/program-settings`
- `PUT /api/v1/program-settings/{program_id}`
- `GET /api/v1/program-validation`
- `PUT /api/v1/program-validation/{program_id}`
- `GET /api/v1/program-data-policies`
- `PUT /api/v1/program-data-policies/{program_id}`

### Ingestion

- `POST /api/v1/imports/analyze`
- `POST /api/v1/imports/upload`
- `GET /api/v1/imports`
- `GET /api/v1/imports/{import_batch_id}/issues`

### Connectors and automation

- `GET /api/v1/connectors`
- `POST /api/v1/connectors`
- `POST /api/v1/connectors/preview`
- `POST /api/v1/connectors/{connector_id}/test`
- `POST /api/v1/connectors/{connector_id}/sync`
- `POST /api/v1/connectors/{connector_id}/dispatch`
- `GET /api/v1/connectors/sync-runs`
- `GET /api/v1/connectors/dispatch-runs`
- `POST /api/v1/automation/run-due`

### Queue and interventions

- `GET /api/v1/risk-cases`
- `GET /api/v1/interventions`
- `POST /api/v1/interventions`
- `PATCH /api/v1/interventions/{intervention_id}`
- `GET /api/v1/interventions/effectiveness`

### Analytics and reports

- `GET /api/v1/dashboard/summary`
- `GET /api/v1/retention/curves`
- `GET /api/v1/retention/analytics`
- `GET /api/v1/reports/donor-summary`
- `GET /api/v1/reports/donor-summary.xlsx`
- `GET /api/v1/reports/donor-summary.pdf`

### Governance

- `GET /api/v1/beneficiaries/governance`
- `PATCH /api/v1/beneficiaries/{beneficiary_id}/governance`
- `GET /api/v1/beneficiaries/{beneficiary_id}/explanation`
- `GET /api/v1/governance/alerts`
- `POST /api/v1/exports/risk-cases`
- `POST /api/v1/exports/interventions`

### Model lifecycle and validation

- `GET /api/v1/model/status`
- `POST /api/v1/model/train`
- `GET /api/v1/model/schedule`
- `PUT /api/v1/model/schedule`
- `GET /api/v1/model/drift`
- `GET /api/v1/feature-store/summary`
- `POST /api/v1/model/evaluate/backtest`
- `GET /api/v1/model/evaluations`
- `POST /api/v1/program-validation/{program_id}/shadow-runs`
- `GET /api/v1/program-validation/shadow-runs`

### Jobs and runtime operations

- `GET /api/v1/jobs`
- `POST /api/v1/jobs/run-pending`
- `POST /api/v1/jobs/{job_id}/requeue`
- `GET /api/v1/ops/runtime-status`
- `GET /api/v1/ops/worker-health`

## API Characteristics

The API is designed to be:

- JSON-based
- role-aware
- auditable
- usable behind self-hosted infrastructure

## Stability Note

The API surface is already broad and useful, but it should still be treated as evolving. Adopting organizations should version their integrations carefully and validate connector/write-back flows in a non-production environment before live use.
