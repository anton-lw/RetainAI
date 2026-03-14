"""Celery task wrappers around the shared job execution service.

The point of this module is narrow: expose queue-executable task functions that
delegate into the same ``execute_job`` logic used by the lightweight worker.
Keeping the task body minimal reduces divergence between deployment modes.
"""

from __future__ import annotations

from app.celery_app import celery_app
from app.db import SessionLocal
from app.models import JobRecord
from app.services.jobs import execute_job


@celery_app.task(name="retainai.execute_job")
def execute_job_task(job_id: str) -> dict[str, str]:
    with SessionLocal() as session:
        job = session.get(JobRecord, job_id)
        if job is None:
            raise ValueError(f"Job {job_id} not found.")
        execute_job(session, job)
    return {"job_id": job_id, "status": "completed"}
