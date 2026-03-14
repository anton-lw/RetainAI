# Getting Started

This guide is the fastest path to a useful first experience with RetainAI.

It is written for developers, implementers, and evaluators who want to get the
system running locally before diving into deeper deployment or validation work.

## What You Will Have At The End

After completing this guide, you should have:

- the backend running locally
- the frontend dashboard running locally
- a seeded demo environment with sample users
- enough context to explore the queue, analytics, connectors, and validation
  views

## 1. Prerequisites

Install:

- Python 3.11+
- Node.js 20+

Recommended:

- PostgreSQL if you want to mirror a more realistic local setup

Optional:

- Docker if you want to use Compose instead of running services directly

## 2. Backend Setup

From the repository root:

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r apps/api/requirements.txt
python -m alembic -c apps/api/alembic.ini upgrade head
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload --app-dir apps/api
```

In a second terminal, start the lightweight worker:

```bash
python apps/api/worker.py
```

If you want the optional Celery path instead:

```bash
python apps/api/celery_worker.py
```

## 3. Frontend Setup

In another terminal:

```bash
npm install --prefix apps/web
npm --prefix apps/web run dev
```

The frontend will point at the local backend by default in development mode.

## 4. Seeded Demo Access

When `AUTO_SEED=true`, the backend seeds local demo users. The default password
is `retainai-demo` unless overridden.

Available demo accounts:

- `admin@retainai.local`
- `me.officer@retainai.local`
- `field.coordinator@retainai.local`
- `country.director@retainai.local`

## 5. First Screens To Visit

Once logged in, a good first tour is:

1. dashboard summary
2. risk queue
3. operations settings
4. governance section
5. validation section
6. connector automation section

That sequence shows the main operational loop and the main governance controls.

## 6. First Things To Try

### Inspect the risk queue

- filter by program, region, cohort, or phase
- open a case
- review its explanation and recommended action

### Log a workflow action

- assign a case
- record an attempted contact
- update verification status
- close or escalate the case

### Review model validation

- inspect model status
- review historical evaluation reports
- create or inspect shadow-mode runs

### Review imports and connectors

- explore existing import history
- preview connector settings if seeded

## 7. Useful Validation Checks

Basic local sanity checks:

```bash
python -m pytest
npm --prefix apps/web run build
npx playwright install chromium
npm --prefix apps/web run test:e2e
```

## 8. Where To Go Next

If you want to understand the product:

- [Project Overview](project-overview.md)
- [Workflow Reference](workflow-reference.md)

If you want to understand the code:

- [Codebase Reference](codebase-reference.md)
- [Backend Code Reference](backend-code-reference.md)
- [Frontend Code Reference](frontend-code-reference.md)

If you want to prepare a real deployment:

- [Implementation Guide](implementation-guide.md)
- [Deployment and Operations](deployment-and-operations.md)
- [Partner Data Request](partner-data-request.md)

If you want to validate the model:

- [Data and ML](data-and-ml.md)
- [Research and Validation](research-evidence-and-validation.md)
- [Testing and Quality Reference](testing-and-quality-reference.md)
