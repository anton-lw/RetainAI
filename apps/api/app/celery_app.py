"""Celery application bootstrap for optional distributed job execution.

RetainAI supports two job-execution modes:

- a lightweight in-process / polling worker for simple self-hosted installs
- a Celery + Redis path for deployments that need stronger async isolation

This module contains only the Celery app wiring and queue configuration. The
actual task bodies live in ``app.services.job_tasks`` and the job-routing logic
stays in ``app.services.jobs`` so that both execution backends share the same
business behavior.
"""

from __future__ import annotations

from celery import Celery

from app.core.config import get_settings


settings = get_settings()

celery_app = Celery(
    "retainai",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=["app.services.job_tasks"],
)
celery_app.conf.task_always_eager = settings.celery_task_always_eager
celery_app.conf.task_serializer = "json"
celery_app.conf.result_serializer = "json"
celery_app.conf.accept_content = ["json"]
celery_app.conf.timezone = "UTC"
celery_app.conf.task_acks_late = True
celery_app.conf.worker_prefetch_multiplier = 1
celery_app.conf.broker_connection_retry_on_startup = True
