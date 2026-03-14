# RetainAI

RetainAI is an open-source retention operations platform for global development
programs.

It helps implementing organizations use the monitoring data they already have to
identify beneficiaries at risk of disengaging, prioritize supportive follow-up
within real staff capacity, document what happened next, and evaluate whether
the system is actually helping.

RetainAI is designed as public-good infrastructure rather than a closed
commercial product. The repository is being prepared for long-term open-source
stewardship, institutional handoff, and Digital Public Goods Alliance review.

## Publication Status

This repository is technically and documentationally close to public-good
submission readiness, but a few publication-specific values still need to be
finalized before a formal DPGA submission:

- named interim or permanent steward
- public issue tracker and support entrypoint
- public security disclosure route

Those final publication values are tracked in:

- [Publication And DPGA Submission Checklist](docs/publication-and-dpga-submission-checklist.md)
- [Public Metadata And Steward Template](docs/public-metadata-and-steward-template.md)

The public repository is:

- [github.com/anton-lw/retainai](https://github.com/anton-lw/retainai)

## Why RetainAI Exists

Many development programs discover attrition too late.

By the time someone is officially counted as lost to follow-up, dropped out, or
inactive, the opportunity for a simple re-engagement action may already be
gone. At the same time, most organizations do not lack data entirely. They
often have:

- enrollment records
- visit or attendance histories
- service delivery logs
- case-management data in tools such as CommCare or DHIS2
- field observations that are never turned into operational prioritization

RetainAI is built to close that gap. It is not just a scoring tool. It is an
operational system for:

1. turning existing data into a capacity-aware follow-up queue
2. helping staff act on that queue in a structured way
3. recording verification outcomes and intervention results
4. validating whether the underlying model is trustworthy enough to use

## What RetainAI Does

RetainAI combines five major capabilities in one self-hostable platform.

### 1. Data ingestion and ETL

- CSV and XLSX import
- guided field mapping and schema inference
- data quality checks and anomaly logging
- connectors for KoboToolbox, CommCare, ODK Central, DHIS2, and Salesforce NPSP
- connector preview, sync history, and write-back support

### 2. Risk scoring and model lifecycle

- configurable disengagement / dropout labeling windows
- program-specific training with base-model assistance
- XGBoost, LightGBM, elastic-net logistic regression, and stacked ensemble
  paths
- SHAP-style explainability
- note sentiment features and feature snapshots
- fairness, drift, and uncertainty reporting
- MLflow-compatible training run logging

### 3. Retention operations workflow

- beneficiary-level risk queue
- capacity-aware prioritization
- assign / attempt / verify / dismiss / close workflow states
- soft-indicator capture
- WhatsApp, SMS, and field-visit export lists
- connector dispatch into upstream systems for embedded operations

### 4. Analytics, evidence, and reporting

- dashboard summaries
- retention curves and aggregate retention analytics
- intervention effectiveness summaries
- donor-oriented PDF and Excel outputs
- temporal backtesting
- cross-segment validation
- shadow-mode evaluation

### 5. Governance, privacy, and safeguards

- consent and opt-out tracking
- beneficiary explanation support
- tokenized and policy-aware exports
- audit logging
- role-based access control
- session tracking and revocation
- optional OIDC SSO
- residency-aware policy enforcement

## What RetainAI Does Not Do

RetainAI is deliberately constrained.

- It does not automate exclusion, disenrollment, or punitive action.
- It does not replace human judgment.
- It does not assume one universal definition of dropout across all programs.
- It does not claim that public benchmark performance proves real-world impact.
- It does not make a deployment legally compliant by itself.

## Current Maturity

RetainAI is a strong pre-production / pilot-grade system.

Today, the repository includes:

- a real FastAPI backend with SQLAlchemy persistence, Alembic migrations, and
  queue-backed operations
- a React + TypeScript dashboard with role-aware controls and mobile-lite views
- self-hosting assets for Docker Compose, Kubernetes, and Terraform
- formal evaluation tooling for backtesting, shadow mode, partner-readiness
  checks, and synthetic stress testing
- a substantial public-good documentation and governance package

RetainAI still requires the following before live operational use in a real
deployment:

- validation on the deploying organization's own data
- fairness and threshold review in local context
- shadow-mode evidence
- infrastructure hardening and local security review
- legal, safeguarding, and data-protection review

## Who RetainAI Is For

### M&E / MEAL teams

- configure labels, windows, and validation settings
- review model evidence
- manage data ingestion and connectors
- monitor drift, fairness, and shadow-mode readiness

### Program and field coordinators

- work from prioritized queues
- log follow-up attempts
- verify beneficiary status
- dismiss, escalate, or close cases
- capture soft observations from the field

### Program leadership

- review retention trends
- assess intervention effectiveness
- compare queue size to staff capacity
- export donor and governance reports

### Researchers and public-interest stewards

- inspect evaluation outputs
- run benchmark and stress tooling
- review governance posture
- maintain and extend the platform responsibly

## Supported Program Contexts

The codebase is structured for programs with repeated, timestamped interactions.
Examples include:

- health adherence and appointment-based programs
- education retention and transition programs
- cash transfer and social-protection style programs

The strongest operational fit today is any context where there is already a
meaningful pattern of repeated interaction, missed engagement, and follow-up.

## Architecture At A Glance

```text
Data sources -> Ingestion and ETL -> Scoring and evaluation -> Queue and actions -> Analytics and governance

CSV/XLSX, Kobo, CommCare, ODK, DHIS2, Salesforce
          -> FastAPI + SQLAlchemy + jobs + connectors
          -> ML pipelines + validation + shadow mode
          -> React dashboard + mobile-lite view + exports + write-back
```

## Quick Start

## Prerequisites

- Python 3.11+
- Node.js 20+
- PostgreSQL recommended for production
- SQLite supported as a local fallback

## Backend

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r apps/api/requirements.txt
python -m alembic -c apps/api/alembic.ini upgrade head
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload --app-dir apps/api
```

Run the lightweight worker in a second terminal:

```bash
python apps/api/worker.py
```

Optional Celery worker path:

```bash
python apps/api/celery_worker.py
```

## Frontend

```bash
npm install --prefix apps/web
npm --prefix apps/web run dev
```

## Tests

Backend:

```bash
python -m pytest
```

Frontend build:

```bash
npm --prefix apps/web run build
```

Browser tests:

```bash
npx playwright install chromium
npm --prefix apps/web run test:e2e
```

## Local Development Accounts

When `AUTO_SEED=true`, the backend seeds development users. The default
password is `retainai-demo` unless `SEED_USER_PASSWORD` is overridden.

- `admin@retainai.local`
- `me.officer@retainai.local`
- `field.coordinator@retainai.local`
- `country.director@retainai.local`

## Validation Before Real Use

RetainAI is designed to make safe validation possible. It does not remove the
need for validation.

Before a real deployment relies on the queue operationally, we recommend:

1. validate the incoming partner data bundle
2. review the inferred mapping and data quality issues
3. run retrospective backtests
4. review fairness, calibration, and precision-at-capacity
5. run shadow mode
6. train staff on the workflow and override paths
7. complete local privacy and safeguarding review

Useful scripts:

- `scripts/validate_partner_bundle.py`
- `scripts/run_model_backtest.py`
- `scripts/run_partner_readiness_suite.py`
- `scripts/run_cross_segment_validation.py`
- `scripts/run_synthetic_stress_suite.py`

## Deployment Options

The repository includes multiple deployment paths because adopting
organizations vary widely in technical capacity.

### Local or small-team self-hosting

- [docker-compose.yml](docker-compose.yml)

### Kubernetes-oriented deployment

- [infra/k8s/retainai.yaml](infra/k8s/retainai.yaml)

### AWS infrastructure scaffolding

- [infra/terraform/aws/main.tf](infra/terraform/aws/main.tf)

### Runbooks

- [Deployment Runbook](infra/ops/deployment-runbook.md)
- [Backup and Disaster Recovery](infra/ops/backup-disaster-recovery.md)
- [Observability Runbook](infra/ops/observability-runbook.md)
- [Release Validation](infra/ops/release-validation.md)

## Documentation

The repository now includes a full documentation set for implementers,
maintainers, reviewers, and future stewards.

### Start here

- [Documentation Hub](docs/README.md)
- [Project Overview](docs/project-overview.md)
- [Implementation Guide](docs/implementation-guide.md)
- [Deployment and Operations](docs/deployment-and-operations.md)

### Code and architecture

- [System Architecture](docs/architecture.md)
- [Codebase Reference](docs/codebase-reference.md)
- [Backend Code Reference](docs/backend-code-reference.md)
- [Frontend Code Reference](docs/frontend-code-reference.md)
- [Workflow Reference](docs/workflow-reference.md)
- [Data Model Reference](docs/data-model-reference.md)
- [Migrations and Schema Evolution](docs/migrations-and-schema-evolution.md)
- [Tooling and Scripts Reference](docs/tooling-and-scripts-reference.md)
- [Testing and Quality Reference](docs/testing-and-quality-reference.md)

### Data, ML, and validation

- [Data and ML](docs/data-and-ml.md)
- [Model Governance](docs/model-governance.md)
- [Research and Validation](docs/research-evidence-and-validation.md)
- [API Surface](docs/api-surface.md)
- [API Endpoint Reference](docs/api-endpoint-reference.md)

### Safety, privacy, and public-good readiness

- [Privacy, Security, and Safeguards](docs/privacy-and-safeguards.md)
- [Privacy Policy](docs/privacy-policy.md)
- [Data Governance and Retention](docs/data-governance-and-retention.md)
- [Threat Model](docs/threat-model.md)
- [Community Safety](docs/community-safety.md)
- [DPGA Audit Evidence Matrix](docs/dpga-audit-evidence.md)
- [Steward Handoff Playbook](docs/steward-handoff-playbook.md)
- [Release And Maintenance Playbook](docs/release-and-maintenance-playbook.md)
- [Publication And DPGA Submission Checklist](docs/publication-and-dpga-submission-checklist.md)
- [Public Metadata And Steward Template](docs/public-metadata-and-steward-template.md)

### Practical onboarding and support

- [Partner Data Request](docs/partner-data-request.md)
- [FAQ](docs/faq.md)
- [Glossary](docs/glossary.md)
- [Support](SUPPORT.md)

## Governance And Public-Good Materials

The repository includes the core files expected of a serious open-source public
good candidate:

- [Governance](GOVERNANCE.md)
- [Contributing](CONTRIBUTING.md)
- [Security Policy](SECURITY.md)
- [Code of Conduct](CODE_OF_CONDUCT.md)
- [License](LICENSE)
- [publiccode.yml](publiccode.yml)

## Repository Structure

```text
apps/
  api/        FastAPI backend, ML services, jobs, persistence
  web/        React dashboard and mobile-lite UI
docs/         Product, architecture, governance, and steward docs
examples/     Import templates and bundle templates
infra/        Kubernetes, Terraform, and operations runbooks
scripts/      Evaluation, benchmark, smoke, and validation tooling
data/         Generated public and synthetic benchmark outputs
```

## Integrations

RetainAI currently supports native-style connector behavior for:

- KoboToolbox
- CommCare
- ODK Central
- DHIS2
- Salesforce NPSP

It also supports CSV and Excel imports for organizations without stable API
integrations.

## Safety And Responsible Use

RetainAI should be used to support retention, not to justify exclusion.

Any adopting organization should ensure:

- staff understand that risk flags are decision support only
- beneficiaries can be explained the system in plain language where required
- export and visibility permissions are reviewed locally
- the queue is tied to realistic follow-up capacity
- model behavior is revalidated when context changes

## Contributing

We welcome contributions, but because the domain is sensitive, we ask that
contributors treat tests, documentation, and safety review as part of the work,
not optional extras.

Please read:

- [Contributing](CONTRIBUTING.md)
- [Governance](GOVERNANCE.md)
- [Security Policy](SECURITY.md)
- [Privacy, Security, and Safeguards](docs/privacy-and-safeguards.md)

## Support

See [SUPPORT.md](SUPPORT.md). At the project level, the software includes
documentation, runbooks, validation tooling, and a governance package, but it
does not promise universal hosted support or universal deployment readiness.

## Important Limitation

Good software architecture and high benchmark scores are not the same as proven
field impact.

RetainAI should not be described as validated for a deployment until that
deployment has completed:

- local data validation
- retrospective evaluation
- fairness review
- shadow mode
- operational training
- local governance and legal review

That restraint is part of the project, not a disclaimer added afterward.
