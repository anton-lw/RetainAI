# Data Model Reference

This document summarizes the main persistent entities in RetainAI and the role
each one plays in the operational, governance, and validation workflows.

The authoritative model definitions live in `apps/api/app/models.py`. This file
exists to help maintainers understand the shape of the domain before reading the
ORM definitions in detail.

## Design Principles

The data model is intentionally shared across several concerns:

- operational case management
- platform security and administration
- ML governance and evaluation
- privacy and beneficiary safeguards

That is why `models.py` is broad. RetainAI is not just a predictor; it is an
operational system that needs one coherent audit and evidence trail.

## Program And User Entities

### `Program`

Represents a deployment-specific program or implementation context.

Key responsibilities:

- anchors beneficiaries and imports
- holds operational, privacy, and validation settings through one-to-one
  companion records
- provides the unit for many dashboards, exports, evaluations, and shadow runs

Related records:

- `Beneficiary`
- `ImportBatch`
- `DataConnector`
- `ProgramOperationalSetting`
- `ProgramValidationSetting`
- `ProgramDataPolicy`
- `ShadowRun`

### `User`

Represents an authenticated platform user.

Key responsibilities:

- identity and role assignment
- audit attribution
- session ownership

Related records:

- `UserSession`
- `AuditLog`

### `UserSession`

Represents a revocable authenticated session.

Why it exists:

- allows JWT-backed auth with revocation and session caps
- supports session-aware logout and active-session views

## Core Operational Entities

### `Beneficiary`

The central operational record in the platform.

It stores:

- demographic and program metadata
- enrollment and outcome dates
- status and governance flags
- fields consumed by analytics and model training

Related records:

- `MonitoringEvent`
- `Intervention`
- governance and export logic through service-layer usage

### `MonitoringEvent`

Represents a time-stamped operational interaction or observation, such as:

- attendance check-in
- service encounter
- payment collection
- scheduled follow-up outcome

These records are one of the most important feature sources for the model.

### `Intervention`

Represents a supportive action taken in response to risk or operational need.

Examples:

- phone call
- SMS reminder
- home visit
- manual outreach

It also captures workflow and verification state so the platform can record the
full `flag -> action -> verification -> outcome` loop.

### `ImportBatch`

Represents a file import or ETL batch.

It is used for:

- import history
- troubleshooting
- associating ETL issues with a specific run

### `DataQualityIssue`

Represents a row-level or batch-level issue discovered during ingest or ETL
analysis.

Typical uses:

- missing required fields
- duplicate identifiers
- anomalous dates or unexpected values

## Connector And Integration Entities

### `DataConnector`

Stores configuration for an external data source or write-back integration.

Examples:

- KoboToolbox
- CommCare
- ODK Central
- DHIS2
- Salesforce NPSP

### `ConnectorSyncRun`

Represents one sync execution against an external connector.

Used for:

- operational history
- troubleshooting
- last-sync visibility

### `ConnectorDispatchRun`

Represents a write-back or embedded-operations dispatch run into an upstream
system.

This is important because queue generation is only part of the product; pushing
tasks back into external workflow systems is also a first-class behavior.

## Model And Evaluation Entities

### `ModelVersion`

Represents a trained model artifact and its metadata.

Stores:

- training metadata
- evaluation summaries
- deployment and artifact references
- explainability and threshold behavior metadata

### `FeatureSnapshot`

Represents persisted feature values captured during training or scoring
contexts.

Why it matters:

- helps with auditability
- supports drift analysis
- creates a lightweight feature-store-like record

### `ModelBiasAudit`

Stores subgroup fairness or performance-audit results tied to a model version.

### `ModelDriftReport`

Stores drift results comparing later data distributions to training-time
distributions.

### `EvaluationReport`

Represents a persisted backtest or validation report.

It stores:

- evaluation settings
- metrics
- fairness summaries
- readiness status

### `ShadowRun`

Represents a shadow-mode scoring run for a program.

This is one of the main bridges between retrospective evaluation and real-world
evidence generation.

### `ShadowRunCase`

Stores the individual cases scored during a shadow run so later observed
outcomes can be compared with the original ranking.

## Queue, Scheduling, And Job Entities

### `ModelSchedule`

Represents retraining cadence and automation behavior.

### `JobRecord`

Represents a background job, whether executed through the lightweight worker or
the optional Celery path.

Stores:

- job type
- status
- retry metadata
- payload and result summaries

## Program Policy Entities

### `ProgramOperationalSetting`

Stores program-specific operational assumptions such as:

- label definitions
- worker/site capacity assumptions
- escalation windows
- support-channel defaults

This record is central to making RetainAI configurable rather than pretending
that "dropout" is one universal task.

### `ProgramValidationSetting`

Stores per-program validation expectations such as:

- shadow-mode enablement
- target precision / recall requirements
- fairness review requirements

### `ProgramDataPolicy`

Stores deployment-specific privacy and governance controls such as:

- storage mode
- residency expectations
- cross-border transfer policy
- tokenization / export assumptions

## Federated Learning Entities

### `FederatedLearningRound`

Represents one federated learning exchange round.

### `FederatedModelUpdate`

Represents one contributed update within a federated round.

These entities support practical update exchange and aggregation, though they
should not be mistaken for a full secure-aggregation system.

## Audit Entity

### `AuditLog`

Represents an immutable record of security-sensitive or governance-sensitive
actions taken inside the system.

Typical examples:

- login
- export request
- governance update
- model training
- connector administration

## Relationship View

The most important relationship chains are:

- `Program -> Beneficiary -> MonitoringEvent`
- `Program -> Beneficiary -> Intervention`
- `Program -> DataConnector -> ConnectorSyncRun`
- `Program -> ModelVersion -> ModelBiasAudit / ModelDriftReport`
- `Program -> EvaluationReport`
- `Program -> ShadowRun -> ShadowRunCase`
- `User -> UserSession`
- `User -> AuditLog`

## Maintainer Notes

- Treat model changes and schema changes as coupled work. Many model fields are
  visible to the UI and to exported reports.
- Treat policy-setting models as product behavior, not internal metadata.
- Treat evaluation entities as core evidence infrastructure, not optional
  analytics extras.

## Related Documents

- [Backend Code Reference](backend-code-reference.md)
- [Workflow Reference](workflow-reference.md)
- [Data Governance and Retention](data-governance-and-retention.md)
