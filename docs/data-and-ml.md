# Data and ML

## Design Principle

RetainAI is built around a practical constraint: most NGO systems already collect enough longitudinal data to support useful retention prediction, but that data is messy, delayed, and inconsistent. The system therefore prioritizes:

- narrow, widely available fields
- point-in-time features
- configurable labels
- capacity-aware ranking
- explicit validation

## Core Data Model

### Beneficiary data

Typical fields used at enrollment or case creation:

- program identifier
- external beneficiary identifier
- name
- sex/gender
- region/site
- enrollment date
- household type or size
- optional PMT or vulnerability proxies
- preferred contact details

### Longitudinal data

Typical repeated records:

- attendance checks
- appointments
- service delivery
- payment collections
- household visits
- outreach attempts
- staff notes

### Operational data

RetainAI adds:

- intervention states
- verification outcomes
- dismissal reasons
- assigned worker/site
- queue metadata
- soft indicators

## Ingestion and ETL

RetainAI supports:

- CSV upload
- XLSX upload
- connector preview and sync
- guided field mapping
- schema detection
- type inference
- duplicate detection
- quality issue persistence

The system is designed to work even when a program lacks richer survey-style fields.

## Label Definitions

RetainAI does not assume one universal definition of dropout. Instead, it supports configurable operational definitions through program settings.

Current presets:

- `health_28d`
- `education_10d`
- `cct_missed_cycle`
- `custom`

This matters because what the system predicts is not a philosophical “true dropout” state. It predicts the configured operational target the program actually needs to manage.

## Feature Families

Implemented feature groups include:

- engagement timing and recency
- attendance and interaction trends
- enrollment age and tenure
- demographic and geography features
- household and vulnerability proxies
- intervention history
- soft indicators
- field-note sentiment and keyword features
- missingness indicators

## Models

The codebase currently supports:

- elastic-net logistic regression
- XGBoost
- LightGBM
- stacked ensembles

Model paths are selected based on available data volume and the training profile.

## Explainability

RetainAI includes:

- SHAP-based local feature contributions where available
- plain-language beneficiary explanations
- beneficiary-facing explanation sheets
- fallback explanation generation when the full SHAP path is unavailable

## Fairness and Drift

The model layer includes:

- group-level bias auditing
- configurable fairness thresholds
- fairness-aware weighting controls
- feature snapshot persistence
- drift reporting
- evaluation reports that surface fairness alongside ranking performance

## Evaluation Workflows

### Formal backtests

`POST /api/v1/model/evaluate/backtest` performs point-in-time temporal evaluation rather than training-time random holdout.

Outputs include:

- split metadata
- AUC-ROC
- PR-AUC
- precision / recall / F1
- Brier score
- top-K precision and recall
- top-K lift
- expected calibration error
- bootstrap confidence intervals
- fairness summary

### Persisted evaluation reports

Backtests are stored in `evaluation_reports` and exposed through `GET /api/v1/model/evaluations`.

### Shadow mode

Shadow mode is implemented to answer the question that offline backtests cannot fully answer:

- if today’s live queue were used operationally, how well would it perform against later outcomes?

Shadow runs:

- snapshot the live queue
- persist the top-K set
- mature over time
- compute observed precision and recall once outcomes are available

### Cross-segment validation

The repository also includes:

- held-out program validation
- held-out cohort validation
- partner-readiness suites
- synthetic stress scenarios

## Synthetic and Public Benchmark Data

RetainAI ships tools to work with:

- public proxy datasets for pipeline testing
- SDV-based synthetic data for stress testing

These datasets are useful for:

- regression benchmarking
- schema and ingestion testing
- fairness stress scenarios
- performance and workflow validation

They are not a substitute for partner-data validation before live use.

## Practical Deployment Recommendation

Before operational use:

1. validate the bundle
2. define the program’s label preset
3. run retrospective backtests
4. review fairness and calibration
5. enable shadow mode
6. review observed shadow outcomes
7. then decide whether live decision support is justified
