# Testing And Quality Reference

This document explains how RetainAI is verified today and how future stewards
should think about adding or maintaining quality checks.

## Quality Philosophy

RetainAI needs more than ordinary web-app correctness because it makes
prioritization recommendations about vulnerable beneficiaries. That means the
quality bar spans four layers:

1. application correctness
2. workflow correctness
3. evaluation correctness
4. operational safety

The codebase does not yet satisfy every possible production-assurance standard,
but it already includes multiple complementary verification layers.

## Current Verification Layers

## Backend Tests

Primary backend tests live in:

- `apps/api/tests/conftest.py`
- `apps/api/tests/test_api_flows.py`

These tests primarily cover:

- authentication and session behavior
- connector CRUD, sync, and dispatch paths
- queue and intervention workflows
- program settings and validation settings
- model training endpoints and status
- evaluation and shadow-mode persistence
- governance and export controls
- runtime and observability endpoints

Use backend tests for:

- route regressions
- workflow state changes
- policy enforcement changes
- persisted contract behavior

## Frontend Verification

Primary frontend verification includes:

- `npm --prefix apps/web run build`
- Playwright tests in `apps/web/e2e/`

Current browser coverage focuses on high-value flows such as:

- login
- queue filtering
- mobile-lite explanation flow
- validation section behavior

Use Playwright when:

- a change affects visible workflows
- state wiring in `App.tsx` changes
- role-aware UI behavior changes

## Lightweight Source Verification

Useful fast checks include:

- `python -m py_compile` for touched Python modules
- frontend TypeScript build for touched web modules

These are not substitutes for the broader test suite, but they are useful for
catching syntax or import problems quickly during documentation or refactor
passes.

## Evaluation Harnesses

RetainAI's quality story includes formal model evaluation scripts, not just
unit tests.

Important scripts:

- `scripts/run_model_backtest.py`
- `scripts/run_cross_segment_validation.py`
- `scripts/run_partner_readiness_suite.py`
- `scripts/run_public_benchmark_suite.py`
- `scripts/run_synthetic_stress_suite.py`

These should be treated as product-quality checks, not optional research tools.

They help answer:

- did ranking quality regress?
- did fairness behavior worsen?
- does segment stability still hold?
- is a partner bundle ready for shadow mode?

## Deployment Validation

Deployment-related verification includes:

- `scripts/compose_smoke.py`
- `scripts/smoke_check.py`
- CI checks in `.github/workflows/ci.yml`
- runbooks in `infra/ops/`

These cover packaging and operational readiness more than business logic.

## What To Test When Changing Specific Areas

### If you change queue ranking or model scoring

Run:

- backend tests
- at least one backtest or benchmark script
- ideally cross-segment validation

### If you change connectors or write-back behavior

Run:

- backend tests touching connectors
- browser flows if the admin UI changed
- manual or scripted smoke checks where possible

### If you change governance, exports, or privacy rules

Run:

- backend tests
- check audit logging behavior
- verify export shape and masking assumptions

### If you change frontend orchestration

Run:

- frontend build
- Playwright tests

### If you change schema models

Run:

- Alembic upgrade path
- backend tests
- frontend build if the API contract changed

## Gaps Future Stewards Should Address

Current quality coverage is strong but incomplete. The most obvious next
improvements are:

- broader Playwright coverage
- more direct tests around fairness and calibration behavior
- explicit migration downgrade coverage
- container-runtime validation in CI
- dependency-vulnerability remediation in the frontend toolchain

## Recommended Release Gate

For a serious release candidate, a maintainer should aim to pass:

1. backend tests
2. frontend build
3. Playwright tests
4. at least one benchmark or evaluation regression run
5. migration upgrade
6. deployment smoke checks where infrastructure is available

## Related Documents

- [Tooling and Scripts Reference](tooling-and-scripts-reference.md)
- [Workflow Reference](workflow-reference.md)
- [Deployment and Operations](deployment-and-operations.md)
