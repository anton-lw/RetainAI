"""MLflow-oriented model operations helpers.

This module isolates experiment and training-run logging concerns from the core
training code. ``modeling.py`` remains responsible for feature engineering and
estimation, while this file handles the bookkeeping needed to persist run
metadata into MLflow-compatible tracking backends.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from app.core.config import get_settings


settings = get_settings()


def log_training_run(
    *,
    algorithm: str,
    metrics: dict[str, float | int | str],
    params: dict[str, Any],
    artifact_path: str | None,
) -> str | None:
    try:  # pragma: no cover - optional runtime dependency
        import mlflow
    except Exception:
        return None

    mlflow.set_tracking_uri(settings.mlflow_tracking_uri)
    mlflow.set_experiment(settings.mlflow_experiment_name)
    with mlflow.start_run(run_name=f"retainai-{algorithm.lower()}") as run:
        mlflow.log_param("algorithm", algorithm)
        for key, value in params.items():
            mlflow.log_param(key, value)
        for key, value in metrics.items():
            if isinstance(value, (int, float)):
                mlflow.log_metric(key, float(value))
            else:
                mlflow.log_param(f"metric_{key}", value)
        if artifact_path:
            artifact = Path(artifact_path)
            if artifact.exists():
                mlflow.log_artifact(str(artifact), artifact_path="model_artifacts")
        return run.info.run_id
