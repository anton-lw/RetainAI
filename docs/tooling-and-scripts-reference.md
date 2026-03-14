# Tooling And Scripts Reference

This document describes the purpose of the executable scripts in the repository
and when maintainers should use them.

These scripts are an important part of the project. RetainAI is not just a web
app; it also includes validation, benchmark, and deployment-support tooling
that future stewards will rely on.

## Script Directory

Scripts live in `scripts/`.

Current files:

- `compose_smoke.py`
- `fetch_oulad_benchmark_dataset.py`
- `fetch_uci_student_dropout_dataset.py`
- `run_cross_segment_validation.py`
- `run_model_backtest.py`
- `run_partner_readiness_suite.py`
- `run_public_benchmark_suite.py`
- `run_synthetic_stress_suite.py`
- `smoke_check.py`
- `validate_partner_bundle.py`

## Deployment And Runtime Scripts

### `compose_smoke.py`

Purpose:

- support smoke validation of the local Docker Compose stack

Use when:

- validating packaging before release
- checking whether a local self-hosted deployment comes up cleanly

### `smoke_check.py`

Purpose:

- run a lightweight post-startup application check against a running backend

Use when:

- verifying that an API instance is healthy enough for basic interaction
- checking that a deployment candidate exposes the expected entrypoints

## Public Benchmark Dataset Fetchers

### `fetch_uci_student_dropout_dataset.py`

Purpose:

- download and transform the public UCI student dropout dataset into a
  RetainAI-shaped beneficiary/event bundle

Primary value:

- pipeline smoke testing
- demo and benchmark regression support

Limit:

- useful as a public proxy, not as real deployment evidence

### `fetch_oulad_benchmark_dataset.py`

Purpose:

- fetch and transform the OULAD dataset into a harsher public benchmark bundle

Primary value:

- stronger temporal and segment-stability testing than the easier UCI proxy

## Evaluation And Validation Scripts

### `run_model_backtest.py`

Purpose:

- run the formal backtest harness against a beneficiary/events bundle

Typical outputs:

- JSON evaluation summary
- Markdown report

Use when:

- validating a new partner dataset
- checking whether a model change materially altered retrospective performance

### `run_cross_segment_validation.py`

Purpose:

- run backtests with program, cohort, or held-out segment slicing

Use when:

- testing generalization across operational segments
- checking whether a model looks good overall but fails on specific cohorts or
  program slices

### `run_partner_readiness_suite.py`

Purpose:

- execute a fuller validation pass on a partner bundle, including segmented
  readiness outputs

Use when:

- deciding whether a partner export is ready for shadow mode

### `validate_partner_bundle.py`

Purpose:

- validate that a partner-provided data bundle is structurally usable before
  heavier evaluation begins

Use when:

- onboarding a new partner dataset
- checking that required files and fields are present

### `run_public_benchmark_suite.py`

Purpose:

- evaluate one or more public benchmark scenarios in a consistent batch format

Use when:

- regression testing model or evaluation changes

## Synthetic Stress Testing

### `run_synthetic_stress_suite.py`

Purpose:

- generate synthetic program bundles and run evaluation across adverse scenarios

Typical scenarios:

- high missingness
- fairness gap stress
- regional shock
- thin-history tail behavior

Use when:

- testing robustness without real partner data
- stress-testing the evaluation harness and queue assumptions

Important limit:

- synthetic stress results are engineering evidence, not field-effectiveness
  evidence

## Recommended Usage Patterns

### For local maintainer development

Common sequence:

1. run unit/integration tests
2. run `run_model_backtest.py` against a known benchmark bundle after model
   changes
3. run `run_synthetic_stress_suite.py` when changing queue or fairness logic

### For partner onboarding

Common sequence:

1. run `validate_partner_bundle.py`
2. run `run_partner_readiness_suite.py`
3. run `run_cross_segment_validation.py`
4. review fairness, calibration, and precision-at-capacity results before any
   shadow deployment

### For release validation

Common sequence:

1. run tests and frontend build
2. run `compose_smoke.py`
3. run `smoke_check.py`
4. run at least one benchmark/evaluation script to catch regression in model or
   validation behavior

## Maintainer Notes

- These scripts are part of the product's trust story. Do not let them drift out
  of sync with the backend API or evaluation service.
- Public datasets are useful for regression and benchmarking, not for claiming
  real-world impact.
- Partner readiness scripts matter more than public benchmark scores when making
  deployment decisions.

## Related Documents

- [Research and Validation](research-evidence-and-validation.md)
- [Codebase Reference](codebase-reference.md)
- [Workflow Reference](workflow-reference.md)
