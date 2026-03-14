# Workflow Reference

This document explains the most important end-to-end workflows in RetainAI and
maps each one to the major backend and frontend files involved.

It is intended for maintainers, reviewers, and future stewards who need to
understand how the system behaves as a product, not just as isolated code
modules.

## Core Product Loop

RetainAI is built around a specific operational loop:

1. ingest beneficiary and event data
2. generate and prioritize risk cases
3. assign and attempt follow-up
4. verify the beneficiary's actual status
5. record outcome and intervention effectiveness
6. evaluate whether the model and workflow are performing acceptably

Everything else in the codebase supports that loop.

## Workflow 1: Data Ingestion

### Purpose

Turn CSV/XLSX uploads or connector payloads into normalized beneficiaries and
monitoring events.

### Primary files

- Backend routes: `apps/api/app/main.py`
- ETL logic: `apps/api/app/services/imports.py`
- Connector ingestion: `apps/api/app/services/connectors.py`
- Persistence: `apps/api/app/models.py`
- Frontend import UI: `apps/web/src/App.tsx`
- Connector admin UI: `apps/web/src/components/ConnectorAutomationSection.tsx`

### Sequence

1. User uploads a file or runs a connector preview/sync.
2. Backend analyzes the payload and infers a likely field mapping.
3. Validation identifies issues such as missing columns, duplicates, or row
   anomalies.
4. Import results are persisted as beneficiaries and events plus issue records.
5. The dashboard refreshes to reflect the new operational dataset.

### Maintainer notes

- Mapping logic must remain transparent enough for NGO operators to understand.
- Data-quality issues should surface before modeling, not after.
- Connector logic must remain idempotent where repeated syncs are plausible.

## Workflow 2: Risk Queue Generation

### Purpose

Build a prioritized list of beneficiaries likely to disengage within a program-
specific horizon and constrained by operational capacity.

### Primary files

- Queue builder: `apps/api/app/services/analytics.py`
- Model scoring: `apps/api/app/services/modeling.py`
- Risk interpretation: `apps/api/app/services/scoring.py`
- Route layer: `apps/api/app/main.py`
- Frontend section: `apps/web/src/components/RiskQueueSection.tsx`

### Sequence

1. Backend loads beneficiaries and related histories.
2. Feature contexts are built from recent events, interventions, and beneficiary
   state.
3. Deployed model bundles score each case.
4. Scores are translated into `High`, `Medium`, or `Low`.
5. Plain-language reasons and recommended actions are attached.
6. Queue filters and ranking are applied before the list reaches the UI.

### Maintainer notes

- Queue logic is where model behavior becomes user-visible behavior.
- Any ranking or filtering change should be checked against evaluation outputs.
- Capacity assumptions matter as much as raw model discrimination.

## Workflow 3: Action, Verification, And Outcome Logging

### Purpose

Turn a risk flag into a documented human response and a verified beneficiary
status.

### Primary files

- Route layer: `apps/api/app/main.py`
- Queue and intervention logic: `apps/api/app/services/analytics.py`
- Persistence: `apps/api/app/models.py`
- Queue UI: `apps/web/src/components/RiskQueueSection.tsx`

### Sequence

1. User opens a queued case.
2. User chooses a channel and action type.
3. User records an attempt, assignment, or escalation.
4. User updates verification state once the beneficiary status is known.
5. User closes, escalates, or dismisses the case with a reason.

### Status concepts

Typical workflow states include:

- queued
- attempted
- reached
- verified
- dismissed
- escalated
- closed

Typical verification outcomes include:

- still enrolled
- re-engaged
- silent transfer
- completed elsewhere
- deceased
- unreachable
- declined support
- dropped out confirmed

### Maintainer notes

- This loop is central to the project's real-world usefulness.
- Dismissal reasons and verification outcomes are product data, not just audit
  noise; they feed learning and trust.

## Workflow 4: Embedded Operations / Write-Back

### Purpose

Push queue outputs or tasks back into upstream systems so staff can work within
CommCare, DHIS2, or another operational tool rather than relying only on the
dashboard.

### Primary files

- Integration logic: `apps/api/app/services/connectors.py`
- Route layer: `apps/api/app/main.py`
- Frontend admin UI: `apps/web/src/components/ConnectorAutomationSection.tsx`

### Sequence

1. Operator configures write-back mode and channel details.
2. Queue items are transformed into upstream payloads.
3. Dispatch runs are recorded.
4. Operators inspect dispatch history and failures.

### Maintainer notes

- This workflow is central to adoption because the research strongly suggests a
  standalone dashboard is often insufficient for field use.

## Workflow 5: Governance And Privacy Control

### Purpose

Prevent harmful use and make beneficiary rights operational.

### Primary files

- Governance logic: `apps/api/app/services/governance.py`
- Privacy logic: `apps/api/app/services/privacy.py`
- Audit logging: `apps/api/app/services/audit.py`
- UI section: `apps/web/src/components/GovernanceSection.tsx`

### Sequence

1. Privileged user reviews a governance record or alert.
2. Beneficiary opt-out, consent, explanation, or export actions are requested.
3. Privacy rules are checked before data leaves the system.
4. Audit records and governance alerts are persisted.

### Maintainer notes

- Do not add new exports or visibility features without reviewing this path.
- Governance behavior is a first-class product feature, not a compliance bolt-on.

## Workflow 6: Formal Evaluation And Shadow Mode

### Purpose

Test whether the model and queue behavior are credible enough for shadow-mode
or controlled operational use.

### Primary files

- Evaluation logic: `apps/api/app/services/evaluation.py`
- Modeling support: `apps/api/app/services/modeling.py`
- Validation routes: `apps/api/app/main.py`
- Validation UI: `apps/web/src/components/ValidationSection.tsx`
- Batch scripts: `scripts/run_model_backtest.py`, `scripts/run_cross_segment_validation.py`,
  `scripts/run_partner_readiness_suite.py`, `scripts/run_synthetic_stress_suite.py`

### Sequence

1. User or operator configures evaluation parameters.
2. Temporal folds or holdouts are built.
3. Models train and score within those constraints.
4. Metrics, fairness summaries, and calibration summaries are persisted.
5. Shadow-mode runs create snapshots that later compare predicted vs. observed
   outcomes.

### Maintainer notes

- Evaluation is not optional. It is the bridge between software correctness and
  operational trust.
- Public and synthetic benchmarks are regression tools, not deployment proof.

## Workflow 7: Background Jobs

### Purpose

Run long or asynchronous tasks such as training, connector syncs, or automation
runs.

### Primary files

- Job lifecycle: `apps/api/app/services/jobs.py`
- Celery bridge: `apps/api/app/services/job_tasks.py`
- Lightweight worker: `apps/api/worker.py`
- Optional Celery worker: `apps/api/celery_worker.py`
- Runtime status: `apps/api/app/services/operations.py`

### Sequence

1. Route enqueues a job.
2. Job record persists with state and retry metadata.
3. Worker backend executes the job.
4. Result or failure updates the job record.
5. Operators can inspect, rerun, or requeue as needed.

## Workflow 8: Synthetic And Benchmark Validation

### Purpose

Exercise the system when real partner data is unavailable and stress-test the
evaluation harness under adverse scenarios.

### Primary files

- Synthetic bundle generation: `apps/api/app/services/synthetic_data.py`
- Dataset and benchmark scripts in `scripts/`
- Generated benchmark data in `data/public/` and `data/synthetic/`

### Maintainer notes

- These workflows are essential for engineering confidence and demo packaging.
- They do not establish real-world effectiveness on their own.

## Related Documents

- [Codebase Reference](codebase-reference.md)
- [Backend Code Reference](backend-code-reference.md)
- [Frontend Code Reference](frontend-code-reference.md)
- [Research and Validation](research-evidence-and-validation.md)
