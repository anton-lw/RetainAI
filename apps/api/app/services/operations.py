"""Runtime-status and operator-health helpers.

This module powers the administrative view of whether the deployment is in a
safe, policy-compliant state. It checks runtime assumptions such as data
residency alignment, queue health, and worker freshness, and returns a compact
status structure suitable for dashboards and operational runbooks.
"""

from __future__ import annotations

from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.celery_app import celery_app
from app.core.config import get_settings
from app.core.time import utc_now
from app.models import JobRecord, Program


settings = get_settings()


def build_runtime_status(db: Session) -> dict[str, object]:
    programs = db.scalars(
        select(Program)
        .options(selectinload(Program.data_policy))
        .order_by(Program.name.asc())
    ).all()
    violations: list[dict[str, str]] = []
    warnings: list[str] = []
    for program in programs:
        policy = program.data_policy
        if policy is None:
            warnings.append(f"{program.name} is missing an explicit program data policy.")
            continue
        if (
            policy.storage_mode != "self_hosted"
            and policy.data_residency_region != settings.deployment_region
            and not policy.cross_border_transfers_allowed
        ):
            violations.append(
                {
                    "program_id": program.id,
                    "program_name": program.name,
                    "issue": (
                        f"Program requires {policy.data_residency_region} residency but deployment is "
                        f"running in {settings.deployment_region}."
                    ),
                }
            )
        if settings.sso_enabled and settings.sso_mode == "oidc" and not settings.sso_oidc_issuer_url:
            warnings.append("OIDC mode is enabled but the issuer URL is not configured.")
    return {
        "status": "ok" if not violations else "attention",
        "deployment_region": settings.deployment_region,
        "job_backend": settings.job_backend,
        "enforce_runtime_policy": settings.enforce_runtime_policy,
        "violations": violations,
        "warnings": warnings,
    }


def enforce_runtime_status(db: Session) -> None:
    runtime_status = build_runtime_status(db)
    if settings.enforce_runtime_policy and runtime_status["violations"]:
        messages = "; ".join(item["issue"] for item in runtime_status["violations"])  # type: ignore[index]
        raise RuntimeError(f"Runtime policy enforcement blocked application startup: {messages}")


def _celery_worker_state() -> tuple[str, list[str]]:
    if settings.job_backend != "celery":
        return "n/a", []
    try:
        inspector = celery_app.control.inspect(timeout=1.0)
        active = inspector.ping() or {}
        worker_names = sorted(active.keys())
        return ("healthy" if worker_names else "attention"), worker_names
    except Exception:
        return "attention", []


def build_worker_health(db: Session) -> dict[str, object]:
    now = utc_now()
    queued = db.scalar(select(func.count(JobRecord.id)).where(JobRecord.status == "queued")) or 0
    running = db.scalar(select(func.count(JobRecord.id)).where(JobRecord.status == "running")) or 0
    failed = db.scalar(select(func.count(JobRecord.id)).where(JobRecord.status == "failed")) or 0
    dead_letter = db.scalar(select(func.count(JobRecord.id)).where(JobRecord.status == "dead_letter")) or 0
    next_ready_at = db.scalar(
        select(JobRecord.available_at)
        .where(JobRecord.status == "queued")
        .order_by(JobRecord.available_at.asc())
        .limit(1)
    )
    oldest_queued = db.scalar(
        select(JobRecord.created_at)
        .where(JobRecord.status == "queued")
        .order_by(JobRecord.created_at.asc())
        .limit(1)
    )
    worker_status, worker_names = _celery_worker_state()
    oldest_queue_age_seconds = None
    if oldest_queued is not None:
        oldest_queue_age_seconds = int((now - oldest_queued).total_seconds())
    return {
        "backend": settings.job_backend,
        "status": "healthy" if dead_letter == 0 and failed == 0 else "attention",
        "queued": queued,
        "running": running,
        "failed": failed,
        "dead_letter": dead_letter,
        "worker_status": worker_status,
        "workers": worker_names,
        "next_ready_at": next_ready_at,
        "oldest_queue_age_seconds": oldest_queue_age_seconds,
        "retry_backoff_seconds": settings.job_retry_backoff_seconds,
        "max_attempts": settings.job_max_attempts,
        "stalled_threshold_seconds": int(timedelta(minutes=10).total_seconds()),
    }
