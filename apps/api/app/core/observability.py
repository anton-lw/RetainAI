"""Observability primitives used by the API and workers.

This module holds the lightweight metrics and request-tracing helpers used
across the backend. It is deliberately framework-light so the rest of the code
can emit request IDs, counters, and timings without depending on a large
monitoring stack.
"""

from __future__ import annotations

import contextvars
import json
import logging
import sys
from typing import Any

from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, Histogram, generate_latest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.time import utc_isoformat
from app.models import JobRecord, Program


settings = get_settings()
_request_id_context: contextvars.ContextVar[str] = contextvars.ContextVar("retainai_request_id", default="-")
_configured = False


HTTP_REQUESTS_TOTAL = Counter(
    "retainai_http_requests_total",
    "HTTP requests processed by the RetainAI API.",
    labelnames=("method", "path", "status"),
)
HTTP_REQUEST_DURATION_SECONDS = Histogram(
    "retainai_http_request_duration_seconds",
    "HTTP request duration in seconds.",
    labelnames=("method", "path"),
    buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30),
)
HTTP_REQUESTS_IN_PROGRESS = Gauge(
    "retainai_http_requests_in_progress",
    "HTTP requests currently being processed.",
)
JOB_EXECUTIONS_TOTAL = Counter(
    "retainai_job_executions_total",
    "Job executions by type and terminal status.",
    labelnames=("job_type", "status"),
)
JOB_EXECUTION_DURATION_SECONDS = Histogram(
    "retainai_job_execution_duration_seconds",
    "Background job execution duration in seconds.",
    labelnames=("job_type", "status"),
    buckets=(0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30, 60, 120, 300),
)
APP_INFO = Gauge(
    "retainai_app_info",
    "Deployment metadata for the current RetainAI process.",
    labelnames=("environment", "deployment_label", "deployment_region"),
)
PROGRAM_COUNT = Gauge(
    "retainai_programs_total",
    "Programs configured in the current deployment.",
)
RUNTIME_POLICY_VIOLATIONS = Gauge(
    "retainai_runtime_policy_violations_total",
    "Runtime policy violations currently detected.",
)
RUNTIME_POLICY_WARNINGS = Gauge(
    "retainai_runtime_policy_warnings_total",
    "Runtime policy warnings currently detected.",
)
JOB_COUNT_BY_STATUS = Gauge(
    "retainai_jobs_by_status",
    "Queued background jobs grouped by status.",
    labelnames=("status",),
)
WORKER_COUNT = Gauge(
    "retainai_workers_detected_total",
    "Workers detected by the configured job backend.",
)
OLDEST_QUEUE_AGE_SECONDS = Gauge(
    "retainai_oldest_queue_age_seconds",
    "Age in seconds of the oldest queued background job.",
)


class RequestContextFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = get_request_id()
        return True


class JsonLogFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": utc_isoformat(),
            "level": record.levelname.lower(),
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": getattr(record, "request_id", get_request_id()),
        }
        for attribute in (
            "event",
            "method",
            "path",
            "status",
            "status_code",
            "duration_ms",
            "job_type",
            "job_id",
            "attempts",
        ):
            value = getattr(record, attribute, None)
            if value is not None:
                payload[attribute] = value
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=True)


def configure_observability() -> None:
    global _configured
    if _configured:
        return

    log_level = getattr(logging, settings.observability_log_level.upper(), logging.INFO)
    handler = logging.StreamHandler(sys.stdout)
    handler.addFilter(RequestContextFilter())
    if settings.observability_json_logs:
        handler.setFormatter(JsonLogFormatter())
    else:
        handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)s %(name)s [%(request_id)s] %(message)s")
        )

    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.setLevel(log_level)
    root_logger.addHandler(handler)

    APP_INFO.labels(
        environment=settings.environment,
        deployment_label=settings.deployment_label,
        deployment_region=settings.deployment_region,
    ).set(1)
    _configured = True


def set_request_id(value: str) -> None:
    _request_id_context.set(value)


def get_request_id() -> str:
    return _request_id_context.get()


def clear_request_id() -> None:
    _request_id_context.set("-")


def observe_http_request(*, method: str, path: str, status_code: int, duration_seconds: float) -> None:
    if not settings.observability_metrics_enabled:
        return
    HTTP_REQUESTS_TOTAL.labels(method=method, path=path, status=str(status_code)).inc()
    HTTP_REQUEST_DURATION_SECONDS.labels(method=method, path=path).observe(duration_seconds)


def observe_job_execution(*, job_type: str, status: str, duration_seconds: float) -> None:
    if not settings.observability_metrics_enabled:
        return
    JOB_EXECUTIONS_TOTAL.labels(job_type=job_type, status=status).inc()
    JOB_EXECUTION_DURATION_SECONDS.labels(job_type=job_type, status=status).observe(duration_seconds)


def _update_runtime_metrics(db: Session) -> None:
    from app.services.operations import build_runtime_status, build_worker_health

    runtime_status = build_runtime_status(db)
    worker_health = build_worker_health(db)

    PROGRAM_COUNT.set(float(db.scalar(select(func.count(Program.id))) or 0))
    RUNTIME_POLICY_VIOLATIONS.set(float(len(runtime_status["violations"])))
    RUNTIME_POLICY_WARNINGS.set(float(len(runtime_status["warnings"])))

    statuses = ("queued", "running", "succeeded", "failed", "dead_letter")
    for job_status in statuses:
        count = db.scalar(select(func.count(JobRecord.id)).where(JobRecord.status == job_status)) or 0
        JOB_COUNT_BY_STATUS.labels(status=job_status).set(float(count))

    WORKER_COUNT.set(float(len(worker_health["workers"])))
    OLDEST_QUEUE_AGE_SECONDS.set(float(worker_health["oldest_queue_age_seconds"] or 0))


def render_metrics(db: Session) -> bytes:
    if settings.observability_metrics_enabled:
        _update_runtime_metrics(db)
    return generate_latest()


__all__ = [
    "CONTENT_TYPE_LATEST",
    "HTTP_REQUESTS_IN_PROGRESS",
    "clear_request_id",
    "configure_observability",
    "get_request_id",
    "observe_http_request",
    "observe_job_execution",
    "render_metrics",
    "set_request_id",
]
