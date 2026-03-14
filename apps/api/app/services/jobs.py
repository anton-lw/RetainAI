"""Background-job orchestration primitives.

RetainAI uses queued execution for connector syncs, model retraining, and due
automation. This module is the core job abstraction shared by the lightweight
database-backed worker path and the optional Celery-based execution path.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
import logging
from time import perf_counter
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app import schemas
from app.celery_app import celery_app
from app.core.config import get_settings
from app.core.observability import observe_job_execution
from app.core.time import utc_now
from app.models import DataConnector, JobRecord, User
from app.services.connectors import run_connector_sync, run_due_automation
from app.services.modeling import build_model_status, train_and_deploy_model

JOB_TYPE_CONNECTOR_SYNC = "connector_sync"
JOB_TYPE_MODEL_TRAIN = "model_train"
JOB_TYPE_AUTOMATION_RUN_DUE = "automation_run_due"
JOB_STATUS_QUEUED = "queued"
JOB_STATUS_RUNNING = "running"
JOB_STATUS_SUCCEEDED = "succeeded"
JOB_STATUS_FAILED = "failed"
JOB_STATUS_DEAD_LETTER = "dead_letter"
settings = get_settings()
logger = logging.getLogger("retainai.jobs")


@dataclass
class EnqueueResult:
    job: JobRecord
    created: bool


def _hydrate_job(db: Session, job_id: str) -> JobRecord:
    statement = (
        select(JobRecord)
        .options(selectinload(JobRecord.created_by))
        .where(JobRecord.id == job_id)
    )
    job = db.scalar(statement)
    if job is None:
        raise ValueError("Job not found after persistence.")
    return job


def _serialize_job(job: JobRecord) -> schemas.JobRead:
    return schemas.JobRead(
        id=job.id,
        job_type=job.job_type,  # type: ignore[arg-type]
        status=job.status,  # type: ignore[arg-type]
        payload=job.payload or {},
        result=job.result,
        error_message=job.error_message,
        attempts=job.attempts,
        max_attempts=job.max_attempts,
        retry_backoff_seconds=job.retry_backoff_seconds,
        available_at=job.available_at,
        started_at=job.started_at,
        completed_at=job.completed_at,
        last_error_at=job.last_error_at,
        dead_lettered_at=job.dead_lettered_at,
        created_at=job.created_at,
        created_by_email=job.created_by.email if job.created_by is not None else None,
    )


def serialize_job(job: JobRecord) -> schemas.JobRead:
    return _serialize_job(job)


def list_jobs(db: Session, limit: int = 25) -> list[schemas.JobRead]:
    statement = (
        select(JobRecord)
        .options(selectinload(JobRecord.created_by))
        .order_by(JobRecord.created_at.desc())
        .limit(limit)
    )
    return [_serialize_job(job) for job in db.scalars(statement).all()]


def requeue_job(db: Session, job_id: str) -> JobRecord:
    job = db.scalar(
        select(JobRecord)
        .options(selectinload(JobRecord.created_by))
        .where(JobRecord.id == job_id)
    )
    if job is None:
        raise ValueError("Job not found.")
    if job.status not in {JOB_STATUS_FAILED, JOB_STATUS_DEAD_LETTER}:
        raise ValueError("Only failed or dead-lettered jobs can be re-queued.")

    previous_status = job.status
    job.status = JOB_STATUS_QUEUED
    job.available_at = utc_now()
    job.started_at = None
    job.completed_at = None
    job.last_error_at = None
    job.dead_lettered_at = None
    job.error_message = None
    job.result = None
    job.attempts = 0
    db.add(job)
    db.commit()

    logger.info(
        "job_requeued",
        extra={
            "event": "job.requeue",
            "job_type": job.job_type,
            "job_id": job.id,
            "status": previous_status,
        },
    )
    if settings.job_backend == "celery":
        celery_app.send_task("retainai.execute_job", args=[job.id])
    return _hydrate_job(db, job.id)


def _matching_open_job(
    db: Session,
    *,
    job_type: str,
    payload: dict[str, str | int | float | bool | None],
) -> JobRecord | None:
    statement = (
        select(JobRecord)
        .options(selectinload(JobRecord.created_by))
        .where(JobRecord.job_type == job_type, JobRecord.status.in_([JOB_STATUS_QUEUED, JOB_STATUS_RUNNING]))
        .order_by(JobRecord.created_at.desc())
        .limit(20)
    )
    for existing in db.scalars(statement).all():
        if (existing.payload or {}) == payload:
            return existing
    return None


def enqueue_job(
    db: Session,
    *,
    job_type: str,
    payload: dict[str, str | int | float | bool | None] | None = None,
    created_by: User | None = None,
) -> EnqueueResult:
    normalized_payload = payload or {}
    existing = _matching_open_job(db, job_type=job_type, payload=normalized_payload)
    if existing is not None:
        return EnqueueResult(job=existing, created=False)

    job = JobRecord(
        job_type=job_type,
        status=JOB_STATUS_QUEUED,
        created_by_user_id=created_by.id if created_by is not None else None,
        payload=normalized_payload,
        max_attempts=settings.job_max_attempts,
        retry_backoff_seconds=settings.job_retry_backoff_seconds,
        available_at=utc_now(),
    )
    db.add(job)
    db.commit()
    logger.info(
        "job_enqueued",
        extra={
            "event": "job.enqueue",
            "job_type": job.job_type,
            "job_id": job.id,
            "attempts": job.attempts,
        },
    )
    if settings.job_backend == "celery":
        celery_app.send_task("retainai.execute_job", args=[job.id])
    return EnqueueResult(job=_hydrate_job(db, job.id), created=True)


def _claim_next_job(db: Session) -> JobRecord | None:
    statement = (
        select(JobRecord)
        .options(selectinload(JobRecord.created_by))
        .where(
            JobRecord.status == JOB_STATUS_QUEUED,
            JobRecord.available_at <= utc_now(),
        )
        .order_by(JobRecord.created_at.asc())
        .limit(1)
    )
    job = db.scalar(statement)
    if job is None:
        return None

    job.status = JOB_STATUS_RUNNING
    job.started_at = utc_now()
    job.completed_at = None
    job.error_message = None
    job.dead_lettered_at = None
    job.attempts += 1
    db.add(job)
    db.commit()
    return _hydrate_job(db, job.id)


def _retry_delay_seconds(job: JobRecord) -> int:
    attempts = max(job.attempts, 1)
    return max(job.retry_backoff_seconds, 1) * attempts


def _run_connector_sync_job(db: Session, job: JobRecord) -> dict[str, str | int | float | bool | None]:
    connector_id = job.payload.get("connector_id")
    if not isinstance(connector_id, str) or not connector_id:
        raise ValueError("Connector sync job is missing connector_id.")

    connector = db.scalar(
        select(DataConnector)
        .options(selectinload(DataConnector.program))
        .where(DataConnector.id == connector_id)
    )
    if connector is None:
        raise ValueError("Connector not found.")

    actor = db.get(User, job.created_by_user_id) if job.created_by_user_id else None
    outcome = run_connector_sync(
        db,
        connector,
        triggered_by=actor,
        trigger_mode=str(job.payload.get("trigger_mode") or "manual"),
        auto_retrain=bool(job.payload.get("auto_retrain", False)),
    )
    if outcome.run.status != "succeeded":
        raise ValueError(outcome.connector.last_error or outcome.run.log_excerpt or "Connector sync failed.")
    return {
        "connector_id": connector.id,
        "sync_run_id": outcome.run.id,
        "sync_status": outcome.run.status,
        "records_processed": outcome.run.records_processed,
        "records_failed": outcome.run.records_failed,
        "model_retrained": outcome.run.model_retrained,
    }


def _run_model_train_job(db: Session, job: JobRecord) -> dict[str, str | int | float | bool | None]:
    force = bool(job.payload.get("force", False))
    version = train_and_deploy_model(db, force=force)
    model_status = build_model_status(db, version)
    return {
        "model_version_id": version.id,
        "algorithm": version.algorithm,
        "training_rows": model_status.training_rows,
        "positive_rows": model_status.positive_rows,
        "fallback_active": model_status.fallback_active,
    }


def _run_automation_job(db: Session, _: JobRecord) -> dict[str, str | int | float | bool | None]:
    outcome = run_due_automation(db)
    return {
        "connectors_considered": len(outcome.connector_runs),
        "connector_runs_triggered": len(outcome.connector_runs),
        "connector_runs_failed": outcome.connector_failures,
        "model_retrained": outcome.model_retrained,
    }


def execute_job(db: Session, job: JobRecord) -> JobRecord:
    retry_countdown: int | None = None
    started = perf_counter()
    terminal_status = JOB_STATUS_SUCCEEDED
    try:
        if job.job_type == JOB_TYPE_CONNECTOR_SYNC:
            result = _run_connector_sync_job(db, job)
        elif job.job_type == JOB_TYPE_MODEL_TRAIN:
            result = _run_model_train_job(db, job)
        elif job.job_type == JOB_TYPE_AUTOMATION_RUN_DUE:
            result = _run_automation_job(db, job)
        else:
            raise ValueError(f"Unsupported job type: {job.job_type}")
    except Exception as exc:
        job.result = None
        job.error_message = str(exc)
        job.last_error_at = utc_now()
        if job.attempts < job.max_attempts:
            job.status = JOB_STATUS_QUEUED
            terminal_status = JOB_STATUS_FAILED
            retry_countdown = _retry_delay_seconds(job)
            job.available_at = utc_now() + timedelta(seconds=retry_countdown)
            job.started_at = None
            job.completed_at = None
        else:
            job.status = JOB_STATUS_DEAD_LETTER
            terminal_status = JOB_STATUS_DEAD_LETTER
            job.dead_lettered_at = utc_now()
            job.completed_at = utc_now()
    else:
        job.status = JOB_STATUS_SUCCEEDED
        terminal_status = JOB_STATUS_SUCCEEDED
        job.result = result
        job.error_message = None
        job.last_error_at = None
        job.completed_at = utc_now()
    db.add(job)
    db.commit()
    duration_ms = round((perf_counter() - started) * 1000, 2)
    observe_job_execution(
        job_type=job.job_type,
        status=terminal_status,
        duration_seconds=duration_ms / 1000,
    )
    logger.info(
        "job_executed",
        extra={
            "event": "job.execute",
            "job_type": job.job_type,
            "job_id": job.id,
            "status": job.status,
            "attempts": job.attempts,
            "duration_ms": duration_ms,
        },
    )
    if retry_countdown is not None and settings.job_backend == "celery":
        celery_app.send_task("retainai.execute_job", args=[job.id], countdown=retry_countdown)
    return _hydrate_job(db, job.id)


def run_pending_jobs(db: Session, max_jobs: int = 10) -> list[JobRecord]:
    completed: list[JobRecord] = []
    for _ in range(max_jobs):
        job = _claim_next_job(db)
        if job is None:
            break
        completed.append(execute_job(db, job))
    return completed
