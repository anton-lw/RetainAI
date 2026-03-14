"""Scheduling helpers for model retraining and automation cadence.

This service keeps the retraining cadence logic intentionally small and
deterministic. It calculates when model runs should happen, ensures a schedule
record exists, and updates run markers after automation or connector-triggered
events. The actual queued execution happens elsewhere.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.time import utc_now
from app.models import ModelSchedule


def compute_next_model_run(cadence: str, reference: datetime | None = None) -> datetime | None:
    now = reference or utc_now()
    normalized = cadence.lower()
    if normalized == "weekly":
        return now + timedelta(days=7)
    if normalized == "monthly":
        return now + timedelta(days=30)
    return None


def ensure_model_schedule(db: Session) -> ModelSchedule:
    schedule = db.scalar(select(ModelSchedule).limit(1))
    if schedule is not None:
        return schedule

    schedule = ModelSchedule(
        enabled=False,
        cadence="manual",
        auto_retrain_after_sync=False,
        next_run_at=None,
    )
    db.add(schedule)
    db.commit()
    db.refresh(schedule)
    return schedule


def update_model_schedule(
    db: Session,
    schedule: ModelSchedule,
    *,
    cadence: str,
    enabled: bool,
    auto_retrain_after_sync: bool,
) -> ModelSchedule:
    schedule.cadence = cadence
    schedule.enabled = enabled and cadence.lower() in {"weekly", "monthly"}
    schedule.auto_retrain_after_sync = auto_retrain_after_sync
    schedule.next_run_at = compute_next_model_run(cadence) if schedule.enabled else None
    db.add(schedule)
    db.commit()
    db.refresh(schedule)
    return schedule


def mark_model_schedule_run(db: Session, schedule: ModelSchedule, when: datetime | None = None) -> ModelSchedule:
    ran_at = when or utc_now()
    schedule.last_run_at = ran_at
    schedule.next_run_at = compute_next_model_run(schedule.cadence, ran_at) if schedule.enabled else None
    db.add(schedule)
    db.commit()
    db.refresh(schedule)
    return schedule
