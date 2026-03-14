"""Central UTC time helpers used throughout the application.

RetainAI stores and compares timestamps across API requests, jobs, connector
syncs, evaluation runs, and audit-sensitive workflows. This module exists to
keep time handling consistent and to avoid scattered timezone logic or
deprecated ``datetime.utcnow()`` usage across the codebase.
"""

from __future__ import annotations

from datetime import UTC, date, datetime


def utc_now() -> datetime:
    return datetime.now(UTC)


def utc_today() -> date:
    return utc_now().date()


def utc_isoformat(value: datetime | None = None) -> str:
    return (value or utc_now()).isoformat().replace("+00:00", "Z")


def utc_timestamp_slug(value: datetime | None = None) -> str:
    return (value or utc_now()).strftime("%Y%m%d%H%M%S")


def coerce_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
