from __future__ import annotations

import logging
import time

from app.core.config import get_settings
from app.core.observability import configure_observability
from app.db import SessionLocal, init_db
from app.services.auth import ensure_bootstrap_admin
from app.seed import seed_database
from app.services.automation import ensure_model_schedule
from app.services.jobs import run_pending_jobs
from app.services.modeling import ensure_model_ready


def main() -> None:
    configure_observability()
    settings = get_settings()
    logger = logging.getLogger("retainai.worker")
    if settings.job_backend == "celery":
        logger.info("JOB_BACKEND=celery is enabled. Start the Celery worker with `celery -A app.celery_app.celery_app worker -l info`.")
        return

    init_db()

    with SessionLocal() as session:
        ensure_bootstrap_admin(session)
        if settings.auto_seed:
            seed_database(session)
        ensure_model_schedule(session)
        ensure_model_ready(session)

    logger.info(
        "worker_started",
        extra={
            "event": "worker.start",
            "duration_ms": 0,
        },
    )
    while True:
        with SessionLocal() as session:
            completed = run_pending_jobs(session, max_jobs=25)
        if completed:
            logger.info(
                "worker_processed_jobs",
                extra={
                    "event": "worker.loop",
                    "status": "processed",
                    "attempts": len(completed),
                },
            )
        time.sleep(settings.worker_poll_interval_seconds)


if __name__ == "__main__":
    main()
