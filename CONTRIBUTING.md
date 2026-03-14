# Contributing

Thank you for contributing to RetainAI.

This project operates in a sensitive domain. Changes can affect how organizations prioritize outreach to vulnerable beneficiaries. That means documentation, tests, and safeguards matter as much as new features.

## Before You Start

Read these first:

- [README.md](README.md)
- [GOVERNANCE.md](GOVERNANCE.md)
- [SECURITY.md](SECURITY.md)
- [docs/privacy-and-safeguards.md](docs/privacy-and-safeguards.md)
- [docs/data-and-ml.md](docs/data-and-ml.md)

## Development Setup

### Backend

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r apps/api/requirements.txt
python -m alembic -c apps/api/alembic.ini upgrade head
```

### Frontend

```bash
npm install --prefix apps/web
```

### Start the stack

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload --app-dir apps/api
python apps/api/worker.py
npm --prefix apps/web run dev
```

## Contribution Expectations

Every substantive change should include:

- a clear problem statement
- tests or a justified explanation for why tests are not practical
- documentation updates where behavior, setup, or policy changes
- explicit note of privacy, fairness, or operational impacts when relevant

## Pull Request Checklist

Before opening a PR:

- run `python -m pytest`
- run `npm --prefix apps/web run build`
- run `npm --prefix apps/web run test:e2e` when frontend behavior changed
- run Alembic upgrade if schema changed
- update or add relevant docs

## High-Risk Change Areas

The following require especially careful review:

- risk score generation or threshold changes
- dropout-label definition changes
- fairness logic or evaluation methodology
- data export, tokenization, consent, or governance changes
- connector write-back behavior
- authentication, session, or authorization logic
- synthetic data generation that could leak structure from sensitive source data

## Data Handling Rules

Do not:

- commit real beneficiary data
- commit secrets, tokens, or connector credentials
- add tests that depend on live external systems without a mock or opt-in flag
- write code that silently exports PII by default

Use seeded, synthetic, or approved de-identified data for development and tests.

## Documentation Standards

RetainAI is intended for open-source handoff and public-good review. Documentation is part of the product.

Update documentation when you change:

- setup or deployment steps
- APIs or schemas
- governance, privacy, or safety behavior
- model evaluation or validation workflows
- external integration behavior

## Community Norms

All contributors are expected to follow [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md).

## Security Reporting

Do not open a public issue for a suspected security vulnerability that could expose beneficiary data or compromise deployments. Follow [SECURITY.md](SECURITY.md).
