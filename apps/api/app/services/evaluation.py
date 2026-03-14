"""Formal evaluation and shadow-mode logic.

This service is where RetainAI stops being "just a scoring system" and becomes
an evidence-oriented platform. It implements temporal backtesting, cross-window
fold evaluation, persisted evaluation reports, and shadow runs that later
measure observed precision/recall against real outcomes.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from types import SimpleNamespace
from typing import Callable, Sequence
import warnings

import numpy as np
from sklearn.feature_extraction import DictVectorizer
from sklearn.metrics import average_precision_score, brier_score_loss, f1_score, precision_score, recall_score, roc_auc_score
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app import schemas
from app.core.time import utc_now, utc_today
from app.models import Beneficiary, EvaluationReport, Program, ProgramValidationSetting, ShadowRun, ShadowRunCase, User
from app.services.labeling import (
    build_operational_settings_profile,
    construct_operational_label,
    eligible_for_predictive_modeling,
    latest_observation_date,
)
from app.services.modeling import (
    TrainingSample,
    _audit_groups_for,
    _build_bias_audit_records,
    _build_bias_audit_summary,
    _compute_sample_weights,
    _fit_logistic,
    _fit_pipeline,
    _fit_program_models,
    _fit_program_type_models,
    _load_training_beneficiaries,
    _predict_from_bundle,
    build_feature_context,
)


@dataclass
class SnapshotSample:
    sample: TrainingSample
    snapshot_date: date


@dataclass
class EvaluationFold:
    train_snapshots: list[SnapshotSample]
    test_snapshots: list[SnapshotSample]
    balanced: bool


@dataclass
class FoldResult:
    algorithm: str
    train_samples: list[TrainingSample]
    test_samples: list[TrainingSample]
    probabilities: np.ndarray
    y_true: np.ndarray
    top_k_count: int
    metrics: dict[str, float]


def _build_snapshot_sample(
    beneficiary: Beneficiary,
    *,
    horizon_days: int,
    min_history_days: int,
) -> SnapshotSample | None:
    if not eligible_for_predictive_modeling(beneficiary):
        return None

    observation_end = latest_observation_date(beneficiary)
    anchor_date = beneficiary.dropout_date or beneficiary.completion_date or observation_end
    snapshot_date = anchor_date - timedelta(days=horizon_days)
    if snapshot_date <= beneficiary.enrollment_date:
        return None
    if (snapshot_date - beneficiary.enrollment_date).days < min_history_days:
        return None
    if observation_end < snapshot_date + timedelta(days=horizon_days):
        return None

    profile = build_operational_settings_profile(
        beneficiary.program.program_type,
        beneficiary.program.operational_setting,
    )
    label_result = construct_operational_label(
        beneficiary,
        snapshot_date=snapshot_date,
        profile=profile,
        observation_end=observation_end,
        min_history_days=min_history_days,
        prediction_window_days=horizon_days,
    )
    if label_result.excluded or label_result.label is None:
        return None
    snapshot_events = [event for event in beneficiary.monitoring_events if event.event_date <= snapshot_date]
    snapshot_interventions = [
        intervention for intervention in beneficiary.interventions if intervention.logged_at.date() <= snapshot_date
    ]
    context = build_feature_context(
        beneficiary,
        as_of_date=snapshot_date,
        events=snapshot_events,
        interventions=snapshot_interventions,
    )
    return SnapshotSample(
        sample=TrainingSample(
            beneficiary_id=beneficiary.id,
            program_id=beneficiary.program_id,
            program_type=beneficiary.program.program_type,
            features=context.features,
            label=label_result.label,
            audit_groups=_audit_groups_for(beneficiary),
            label_source=label_result.source,
            sample_weight=label_result.sample_weight,
            label_probability=label_result.label_probability,
            snapshot_date=snapshot_date,
        ),
        snapshot_date=snapshot_date,
    )


def _collect_snapshot_samples(
    db: Session,
    *,
    horizon_days: int,
    min_history_days: int,
) -> tuple[list[SnapshotSample], dict[str, Beneficiary]]:
    beneficiaries = _load_training_beneficiaries(db)
    beneficiaries_by_id = {beneficiary.id: beneficiary for beneficiary in beneficiaries}
    snapshots = [
        snapshot
        for beneficiary in beneficiaries
        if (snapshot := _build_snapshot_sample(beneficiary, horizon_days=horizon_days, min_history_days=min_history_days)) is not None
    ]
    snapshots.sort(key=lambda item: item.snapshot_date)
    return snapshots, beneficiaries_by_id


def _filter_snapshots(
    snapshots: list[SnapshotSample],
    *,
    program_ids: Sequence[str] | None = None,
    cohorts: Sequence[str] | None = None,
) -> list[SnapshotSample]:
    allowed_programs = {value for value in (program_ids or []) if value}
    allowed_cohorts = {value for value in (cohorts or []) if value}
    filtered = snapshots
    if allowed_programs:
        filtered = [snapshot for snapshot in filtered if snapshot.sample.program_id in allowed_programs]
    if allowed_cohorts:
        filtered = [
            snapshot
            for snapshot in filtered
            if str(snapshot.sample.features.get("cohort", "unknown")) in allowed_cohorts
        ]
    return filtered


def _fold_is_balanced(train: list[SnapshotSample], test: list[SnapshotSample]) -> bool:
    train_labels = {item.sample.label for item in train}
    test_labels = {item.sample.label for item in test}
    return len(train_labels) >= 2 and len(test_labels) >= 2


def _fold_has_train_class_variation(fold: EvaluationFold) -> bool:
    return len({item.sample.label for item in fold.train_snapshots}) >= 2


def _holdout_folds(samples: list[SnapshotSample], holdout_share: float) -> list[EvaluationFold]:
    if len(samples) < 30:
        raise ValueError("At least 30 retrospective snapshot cases are required for temporal backtesting.")

    min_test = max(10, int(np.ceil(len(samples) * holdout_share)))
    min_train = max(20, len(samples) - int(np.floor(len(samples) * 0.5)))
    for split_index in range(len(samples) - min_test, min_train - 1, -1):
        train = samples[:split_index]
        test = samples[split_index:]
        if _fold_is_balanced(train, test):
            return [EvaluationFold(train_snapshots=train, test_snapshots=test, balanced=True)]

    split_index = len(samples) - min_test
    if split_index <= 0:
        raise ValueError("Could not construct a usable temporal holdout split.")
    train = samples[:split_index]
    test = samples[split_index:]
    return [EvaluationFold(train_snapshots=train, test_snapshots=test, balanced=False)]


def _rolling_folds(samples: list[SnapshotSample], holdout_share: float, requested_folds: int) -> list[EvaluationFold]:
    if len(samples) < 60:
        raise ValueError("At least 60 retrospective snapshot cases are required for rolling temporal backtesting.")

    test_size = max(10, int(np.ceil(len(samples) * holdout_share)))
    max_folds = max(1, (len(samples) - 20) // test_size)
    fold_count = max(1, min(requested_folds, max_folds))
    while fold_count > 1 and len(samples) - (fold_count * test_size) < 20:
        fold_count -= 1

    initial_train_size = len(samples) - (fold_count * test_size)
    if initial_train_size < 20:
        raise ValueError("Could not construct rolling temporal folds with enough training history.")

    folds: list[EvaluationFold] = []
    for fold_index in range(fold_count):
        train_end = initial_train_size + (fold_index * test_size)
        test_end = min(len(samples), train_end + test_size)
        train = samples[:train_end]
        test = samples[train_end:test_end]
        if not train or not test:
            continue
        folds.append(
            EvaluationFold(
                train_snapshots=train,
                test_snapshots=test,
                balanced=_fold_is_balanced(train, test),
            )
        )
    if not folds:
        raise ValueError("Could not construct rolling temporal folds.")
    return folds


def _predict_snapshot_probabilities(
    train_samples: list[TrainingSample],
    test_samples: list[TrainingSample],
    beneficiaries_by_id: dict[str, Beneficiary],
) -> tuple[str, np.ndarray]:
    train_rows = [sample.features for sample in train_samples]
    y_train = [sample.label for sample in train_samples]
    test_rows = [sample.features for sample in test_samples]

    vectorizer = DictVectorizer(sparse=True)
    x_train_sparse = vectorizer.fit_transform(train_rows)
    x_train_dense = x_train_sparse.toarray()
    x_test_sparse = vectorizer.transform(test_rows)
    x_test_dense = x_test_sparse.toarray()
    feature_names = list(vectorizer.get_feature_names_out())
    sample_weights = _compute_sample_weights(train_samples, beneficiaries_by_id)

    base_logistic = _fit_logistic(x_train_sparse, y_train, sample_weight=sample_weights)
    algorithm, global_components, _ = _fit_pipeline(
        x_train_sparse,
        x_train_dense,
        y_train,
        len(train_samples),
        sample_weights,
    )
    base_bundle = {
        "algorithm": "LogisticRegression",
        "components": {"logistic": base_logistic},
    }
    global_bundle = {
        "algorithm": algorithm,
        "components": global_components,
    }
    program_models, _ = _fit_program_models(
        x_train_sparse,
        x_train_dense,
        train_samples,
        feature_names,
        sample_weights,
    )
    program_type_models = _fit_program_type_models(
        x_train_sparse,
        x_train_dense,
        train_samples,
        feature_names,
        sample_weights,
    )

    base_probabilities = _predict_from_bundle(base_bundle, x_test_sparse, x_test_dense)
    probabilities: list[float] = []
    for index, sample in enumerate(test_samples):
        program_bundle = program_models.get(sample.program_id)
        if program_bundle is not None:
            specific_probability = float(
                _predict_from_bundle(program_bundle, x_test_sparse[index : index + 1], x_test_dense[index : index + 1])[0]
            )
            probability = (specific_probability * 0.7) + (float(base_probabilities[index]) * 0.3)
        else:
            type_bundle = program_type_models.get(sample.program_type)
            selected_bundle = type_bundle if type_bundle is not None else global_bundle
            selected_weight = 0.7 if type_bundle is not None else 0.75
            global_probability = float(
                _predict_from_bundle(selected_bundle, x_test_sparse[index : index + 1], x_test_dense[index : index + 1])[0]
            )
            probability = (global_probability * selected_weight) + (float(base_probabilities[index]) * (1 - selected_weight))
        probabilities.append(probability)

    return algorithm, np.asarray(probabilities, dtype=float)


def _top_k_stats(y_true: np.ndarray, probabilities: np.ndarray, *, top_k_count: int) -> tuple[float, float]:
    if len(probabilities) == 0:
        return 0.0, 0.0
    bounded_k = max(1, min(top_k_count, len(probabilities)))
    ranked = np.argsort(probabilities)[::-1][:bounded_k]
    hits = float(np.sum(y_true[ranked]))
    precision = round(hits / bounded_k, 4)
    positives = int(np.sum(y_true))
    recall = round(hits / positives, 4) if positives else 0.0
    return precision, recall


def _expected_calibration_error(y_true: np.ndarray, probabilities: np.ndarray, *, bins: int) -> float:
    if len(probabilities) == 0:
        return 0.0
    ranked_indices = np.argsort(probabilities)
    splits = np.array_split(ranked_indices, bins)
    total = float(len(probabilities))
    error = 0.0
    for split in splits:
        if len(split) == 0:
            continue
        bucket_probabilities = probabilities[split]
        bucket_labels = y_true[split]
        error += (len(split) / total) * abs(float(np.mean(bucket_probabilities)) - float(np.mean(bucket_labels)))
    return round(float(error), 4)


def _safe_metric(metric_fn, y_true: np.ndarray, probabilities: np.ndarray) -> float:
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            value = float(metric_fn(y_true, probabilities))
    except ValueError:
        return 0.0
    if not np.isfinite(value):
        return 0.0
    return round(value, 4)


def _metric_bundle(
    y_true: np.ndarray,
    probabilities: np.ndarray,
    *,
    top_k_count: int,
    calibration_bins: int,
) -> dict[str, float]:
    thresholded = (probabilities >= 0.5).astype(int)
    top_k_precision, top_k_recall = _top_k_stats(y_true, probabilities, top_k_count=top_k_count)
    base_positive_rate = float(np.mean(y_true)) if len(y_true) else 0.0
    return {
        "auc_roc": _safe_metric(roc_auc_score, y_true, probabilities),
        "pr_auc": _safe_metric(average_precision_score, y_true, probabilities),
        "precision": round(float(precision_score(y_true, thresholded, zero_division=0)), 4),
        "recall": round(float(recall_score(y_true, thresholded, zero_division=0)), 4),
        "f1": round(float(f1_score(y_true, thresholded, zero_division=0)), 4),
        "brier_score": _safe_metric(brier_score_loss, y_true, probabilities),
        "top_k_precision": top_k_precision,
        "top_k_recall": top_k_recall,
        "top_k_lift": round(top_k_precision / base_positive_rate, 4) if base_positive_rate > 0 else 0.0,
        "expected_calibration_error": _expected_calibration_error(y_true, probabilities, bins=calibration_bins),
    }


def _aggregate_fold_metrics(fold_results: list[FoldResult]) -> dict[str, float]:
    metric_names = tuple(fold_results[0].metrics.keys())
    weights = np.asarray([len(result.test_samples) for result in fold_results], dtype=float)
    weight_sum = float(np.sum(weights)) or 1.0
    aggregated: dict[str, float] = {}
    for metric_name in metric_names:
        weighted_value = sum(result.metrics[metric_name] * weights[index] for index, result in enumerate(fold_results)) / weight_sum
        aggregated[metric_name] = round(float(weighted_value), 4)
    return aggregated


def _zero_metric_intervals() -> schemas.EvaluationMetrics:
    zero = schemas.EvaluationMetricInterval(value=0.0, lower_ci=None, upper_ci=None)
    return schemas.EvaluationMetrics(
        auc_roc=zero,
        pr_auc=zero,
        precision=zero,
        recall=zero,
        f1=zero,
        brier_score=zero,
        top_k_precision=zero,
        top_k_recall=zero,
        top_k_lift=zero,
        expected_calibration_error=zero,
    )


def _empty_evaluation_report(
    *,
    request: schemas.EvaluationRequest,
    snapshots: list[SnapshotSample],
    folds: list[EvaluationFold],
    strategy_label: str,
    note: str,
    aggregation_note: str | None = None,
) -> schemas.ModelEvaluationReport:
    positive_cases = int(sum(sample.sample.label for sample in snapshots))
    if folds:
        reference_train = folds[0].train_snapshots or folds[0].test_snapshots
        reference_test = folds[-1].test_snapshots or folds[-1].train_snapshots
        train_start = reference_train[0].snapshot_date.isoformat()
        train_end = reference_train[-1].snapshot_date.isoformat()
        test_start = reference_test[0].snapshot_date.isoformat()
        test_end = reference_test[-1].snapshot_date.isoformat()
        train_cases = int(round(float(np.mean([len(fold.train_snapshots) for fold in folds]))))
        test_cases = int(round(float(np.mean([len(fold.test_snapshots) for fold in folds]))))
        train_positive_rate = round(
            float(np.mean([np.mean([item.sample.label for item in fold.train_snapshots]) for fold in folds if fold.train_snapshots] or [0.0])),
            4,
        )
        test_positive_rate = round(
            float(np.mean([np.mean([item.sample.label for item in fold.test_snapshots]) for fold in folds if fold.test_snapshots] or [0.0])),
            4,
        )
    else:
        earliest = snapshots[0].snapshot_date.isoformat()
        latest = snapshots[-1].snapshot_date.isoformat()
        train_start = earliest
        train_end = latest
        test_start = earliest
        test_end = latest
        train_cases = len(snapshots)
        test_cases = len(snapshots)
        train_positive_rate = round(float(np.mean([sample.sample.label for sample in snapshots])) if snapshots else 0.0, 4)
        test_positive_rate = train_positive_rate

    return schemas.ModelEvaluationReport(
        status="needs_more_data",
        note=note,
        algorithm="Insufficient class variation",
        horizon_days=request.horizon_days,
        min_history_days=request.min_history_days,
        top_k_share=request.top_k_share,
        top_k_count=request.top_k_capacity or max(1, int(np.ceil(max(1, len(snapshots)) * request.top_k_share))),
        samples_evaluated=len(snapshots),
        positive_cases=positive_cases,
        split=schemas.EvaluationSplitSummary(
            temporal_strategy=strategy_label,
            train_cases=train_cases,
            test_cases=test_cases,
            train_positive_rate=train_positive_rate,
            test_positive_rate=test_positive_rate,
            train_start=train_start,
            train_end=train_end,
            test_start=test_start,
            test_end=test_end,
            folds_considered=len(folds),
            folds_used=0,
            balanced_folds=sum(1 for fold in folds if fold.balanced),
            aggregation_note=aggregation_note
            or "Backtesting could not train on any fold with both positive and negative labels.",
        ),
        metrics=_zero_metric_intervals(),
        calibration=[],
        fairness_audit=None,
    )


def _bootstrap_interval_from_folds(
    fold_results: list[FoldResult],
    *,
    metric_name: str,
    iterations: int,
) -> tuple[float | None, float | None]:
    if len(fold_results) < 2:
        return None, None

    rng = np.random.default_rng(seed=42)
    values: list[float] = []
    fold_indices = np.arange(len(fold_results))
    for _ in range(iterations):
        sampled_indices = rng.choice(fold_indices, size=len(fold_indices), replace=True)
        sampled_results = [fold_results[index] for index in sampled_indices]
        metric_value = _aggregate_fold_metrics(sampled_results)[metric_name]
        if np.isfinite(metric_value):
            values.append(metric_value)

    if not values:
        return None, None
    return round(float(np.percentile(values, 2.5)), 4), round(float(np.percentile(values, 97.5)), 4)


def _calibration_bins(y_true: np.ndarray, probabilities: np.ndarray, *, bins: int) -> list[schemas.CalibrationBin]:
    if len(probabilities) == 0:
        return []

    ranked_indices = np.argsort(probabilities)
    splits = np.array_split(ranked_indices, bins)
    calibration: list[schemas.CalibrationBin] = []
    for index, split in enumerate(splits):
        if len(split) == 0:
            continue
        bucket_probabilities = probabilities[split]
        bucket_labels = y_true[split]
        calibration.append(
            schemas.CalibrationBin(
                bin_index=index + 1,
                lower_bound=round(float(np.min(bucket_probabilities)), 4),
                upper_bound=round(float(np.max(bucket_probabilities)), 4),
                predicted_rate=round(float(np.mean(bucket_probabilities)), 4),
                observed_rate=round(float(np.mean(bucket_labels)), 4),
                count=int(len(split)),
            )
        )
    return calibration


def _build_fairness_summary(test_samples: list[TrainingSample], probabilities: np.ndarray) -> schemas.BiasAuditSummary | None:
    audit_rows = _build_bias_audit_records(test_samples, probabilities)
    if not audit_rows:
        return None
    audit_models = [SimpleNamespace(**row) for row in audit_rows]
    return _build_bias_audit_summary(audit_models)


def _readiness_status(
    *,
    total_samples: int,
    positive_cases: int,
    metrics: dict[str, float],
    strategy: str,
    folds_used: int,
    balanced_folds: int,
) -> tuple[str, str]:
    if strategy == "rolling":
        if folds_used < 2 or balanced_folds < 2:
            return (
                "needs_more_data",
                "Rolling temporal backtesting did not find enough balanced evaluation windows. More historical outcome coverage is required before trusting the result.",
            )
    else:
        if balanced_folds < 1:
            return (
                "needs_more_data",
                "Temporal backtesting completed, but the latest holdout window does not contain both dropout and non-dropout cases. More historical outcome coverage is required before trusting the result.",
            )
    if total_samples < 80 or positive_cases < 12:
        return (
            "needs_more_data",
            "Temporal backtesting ran successfully, but there are not yet enough labeled retrospective cases to trust the result operationally.",
        )
    if metrics["top_k_recall"] >= 0.6 and metrics["auc_roc"] >= 0.7 and metrics["pr_auc"] >= 0.3:
        return (
            "ready_for_shadow_mode",
            "Temporal backtesting meets the current shadow-mode bar. Use this model in read-only operational pilots before enabling live follow-up prioritization.",
        )
    return (
        "not_ready",
        "Temporal backtesting completed, but ranking quality is still below the current shadow-mode threshold. Improve data quality, volume, or labeling before live use.",
    )


def _run_fold(
    fold: EvaluationFold,
    *,
    beneficiaries_by_id: dict[str, Beneficiary],
    top_k_share: float,
    top_k_capacity: int | None,
    calibration_bins: int,
) -> FoldResult:
    train_samples = [item.sample for item in fold.train_snapshots]
    test_samples = [item.sample for item in fold.test_snapshots]
    algorithm, probabilities = _predict_snapshot_probabilities(train_samples, test_samples, beneficiaries_by_id)
    y_true = np.asarray([sample.label for sample in test_samples], dtype=int)
    top_k_count = top_k_capacity or max(1, int(np.ceil(len(test_samples) * top_k_share)))
    metrics = _metric_bundle(
        y_true,
        probabilities,
        top_k_count=top_k_count,
        calibration_bins=calibration_bins,
    )
    return FoldResult(
        algorithm=algorithm,
        train_samples=train_samples,
        test_samples=test_samples,
        probabilities=probabilities,
        y_true=y_true,
        top_k_count=min(top_k_count, len(test_samples)),
        metrics=metrics,
    )


def _algorithm_label(fold_results: list[FoldResult]) -> str:
    labels = [result.algorithm for result in fold_results]
    most_common = max(set(labels), key=labels.count)
    return most_common if len(set(labels)) == 1 else f"Mixed({most_common})"


def _aggregate_split_summary(strategy: str, folds: list[EvaluationFold], used_folds: list[EvaluationFold]) -> schemas.EvaluationSplitSummary:
    train_sizes = [len(fold.train_snapshots) for fold in used_folds]
    test_sizes = [len(fold.test_snapshots) for fold in used_folds]
    train_positive_rates = [float(np.mean([item.sample.label for item in fold.train_snapshots])) for fold in used_folds]
    test_positive_rates = [float(np.mean([item.sample.label for item in fold.test_snapshots])) for fold in used_folds]
    aggregation_note = None
    if strategy == "rolling":
        aggregation_note = "Counts and positive rates are averaged across the balanced rolling folds."

    return schemas.EvaluationSplitSummary(
        temporal_strategy=strategy,
        train_cases=int(round(float(np.mean(train_sizes)))),
        test_cases=int(round(float(np.mean(test_sizes)))),
        train_positive_rate=round(float(np.mean(train_positive_rates)), 4),
        test_positive_rate=round(float(np.mean(test_positive_rates)), 4),
        train_start=used_folds[0].train_snapshots[0].snapshot_date.isoformat(),
        train_end=used_folds[-1].train_snapshots[-1].snapshot_date.isoformat(),
        test_start=used_folds[0].test_snapshots[0].snapshot_date.isoformat(),
        test_end=used_folds[-1].test_snapshots[-1].snapshot_date.isoformat(),
        folds_considered=len(folds),
        folds_used=len(used_folds),
        balanced_folds=sum(1 for fold in folds if fold.balanced),
        aggregation_note=aggregation_note,
    )


def _segment_value(snapshot: SnapshotSample, *, dimension: str) -> str:
    if dimension == "program":
        return snapshot.sample.program_id
    if dimension == "cohort":
        return str(snapshot.sample.features.get("cohort", "unknown"))
    raise ValueError(f"Unsupported segment dimension: {dimension}")


def collect_snapshot_dataset(
    db: Session,
    payload: schemas.EvaluationRequest | None = None,
) -> tuple[schemas.EvaluationRequest, list[SnapshotSample], dict[str, Beneficiary]]:
    """Build the point-in-time dataset used for formal retrospective evaluation.

    This is the main boundary between live beneficiary records and the evaluation
    harness. It converts operational history into leakage-aware snapshot samples
    and applies any program or cohort scoping requested by the caller.
    """
    request = payload or schemas.EvaluationRequest()
    snapshots, beneficiaries_by_id = _collect_snapshot_samples(
        db,
        horizon_days=request.horizon_days,
        min_history_days=request.min_history_days,
    )
    snapshots = _filter_snapshots(
        snapshots,
        program_ids=request.program_ids,
        cohorts=request.cohorts,
    )
    if len(snapshots) < 30:
        raise ValueError("Not enough retrospective snapshot cases to run the formal evaluation harness yet.")
    return request, snapshots, beneficiaries_by_id


def evaluate_snapshot_folds(
    *,
    request: schemas.EvaluationRequest,
    snapshots: list[SnapshotSample],
    beneficiaries_by_id: dict[str, Beneficiary],
    folds: list[EvaluationFold],
    strategy_label: str,
    aggregation_note: str | None = None,
) -> schemas.ModelEvaluationReport:
    """Run model evaluation across a prepared set of temporal folds.

    This function is the core evaluator used by both the API and batch scripts.
    It is responsible for metric aggregation, fairness summaries, calibration
    outputs, readiness status, and the human-readable explanation of what split
    strategy produced the result.
    """
    if not folds:
        raise ValueError("At least one evaluation fold is required.")

    trainable_folds = [fold for fold in folds if _fold_has_train_class_variation(fold)]
    usable_folds = [fold for fold in trainable_folds if fold.balanced]
    if not usable_folds and trainable_folds:
        usable_folds = [trainable_folds[-1]]
    if not usable_folds:
        return _empty_evaluation_report(
            request=request,
            snapshots=snapshots,
            folds=folds,
            strategy_label=strategy_label,
            note="Temporal backtesting could not find a fold with both positive and negative training labels. More local history or a shorter horizon is required before the report is meaningful.",
            aggregation_note=aggregation_note,
        )

    fold_results = [
        _run_fold(
            fold,
            beneficiaries_by_id=beneficiaries_by_id,
            top_k_share=request.top_k_share,
            top_k_capacity=request.top_k_capacity,
            calibration_bins=request.calibration_bins,
        )
        for fold in usable_folds
    ]

    metrics = _aggregate_fold_metrics(fold_results)
    metric_intervals: dict[str, schemas.EvaluationMetricInterval] = {}
    for metric_name, value in metrics.items():
        lower_ci, upper_ci = _bootstrap_interval_from_folds(
            fold_results,
            metric_name=metric_name,
            iterations=request.bootstrap_iterations,
        )
        metric_intervals[metric_name] = schemas.EvaluationMetricInterval(
            value=value,
            lower_ci=lower_ci,
            upper_ci=upper_ci,
        )

    all_probabilities = np.concatenate([result.probabilities for result in fold_results])
    all_labels = np.concatenate([result.y_true for result in fold_results]).astype(int)
    all_test_samples = [sample for result in fold_results for sample in result.test_samples]
    top_k_count = int(round(float(np.mean([result.top_k_count for result in fold_results]))))
    resolved_top_k_share = round(float(np.mean([result.top_k_count / max(1, len(result.test_samples)) for result in fold_results])), 4)

    split_summary = _aggregate_split_summary(strategy_label, folds, usable_folds)
    if aggregation_note:
        split_summary.aggregation_note = aggregation_note
    status, note = _readiness_status(
        total_samples=len(snapshots),
        positive_cases=int(sum(sample.sample.label for sample in snapshots)),
        metrics=metrics,
        strategy=strategy_label,
        folds_used=len(usable_folds),
        balanced_folds=sum(1 for fold in folds if fold.balanced),
    )

    return schemas.ModelEvaluationReport(
        status=status,
        note=note,
        algorithm=_algorithm_label(fold_results),
        horizon_days=request.horizon_days,
        min_history_days=request.min_history_days,
        top_k_share=resolved_top_k_share,
        top_k_count=top_k_count,
        samples_evaluated=len(snapshots),
        positive_cases=int(sum(sample.sample.label for sample in snapshots)),
        split=split_summary,
        metrics=schemas.EvaluationMetrics(**metric_intervals),
        calibration=_calibration_bins(all_labels, all_probabilities, bins=request.calibration_bins),
        fairness_audit=_build_fairness_summary(all_test_samples, all_probabilities),
    )


def evaluate_segment_holdout_reports(
    *,
    request: schemas.EvaluationRequest,
    snapshots: list[SnapshotSample],
    beneficiaries_by_id: dict[str, Beneficiary],
    dimension: str,
    label_resolver: Callable[[str], str] | None = None,
) -> list[tuple[str, schemas.ModelEvaluationReport]]:
    """Evaluate out-of-segment generalization for one chosen dimension.

    Segment holdouts are an important realism check. A model can look strong in
    aggregate while failing badly on held-out cohorts, programs, or other
    operational slices. This helper makes that failure mode visible.
    """
    segment_values = sorted({_segment_value(snapshot, dimension=dimension) for snapshot in snapshots})
    reports: list[tuple[str, schemas.ModelEvaluationReport]] = []
    for raw_value in segment_values:
        held_out = [snapshot for snapshot in snapshots if _segment_value(snapshot, dimension=dimension) == raw_value]
        retained = [snapshot for snapshot in snapshots if _segment_value(snapshot, dimension=dimension) != raw_value]
        if len(held_out) < 20 or len(retained) < 30:
            continue
        fold = EvaluationFold(
            train_snapshots=retained,
            test_snapshots=held_out,
            balanced=_fold_is_balanced(retained, held_out),
        )
        label = label_resolver(raw_value) if label_resolver is not None else raw_value
        report = evaluate_snapshot_folds(
            request=request,
            snapshots=held_out,
            beneficiaries_by_id=beneficiaries_by_id,
            folds=[fold],
            strategy_label="segment_holdout",
            aggregation_note=f"Train on all data outside the held-out {dimension} segment; test only on {label}.",
        )
        reports.append((label, report))
    return reports


def evaluate_model_backtest(db: Session, payload: schemas.EvaluationRequest | None = None) -> schemas.ModelEvaluationReport:
    """Run the standard persisted backtest flow for a deployment.

    This is the default API-facing evaluation entrypoint. It prepares the
    dataset, chooses the requested temporal strategy, and delegates to the fold
    evaluator for actual metric production.
    """
    request, snapshots, beneficiaries_by_id = collect_snapshot_dataset(db, payload)

    if request.temporal_strategy == "rolling":
        folds = _rolling_folds(snapshots, request.holdout_share, request.rolling_folds)
    else:
        folds = _holdout_folds(snapshots, request.holdout_share)

    return evaluate_snapshot_folds(
        request=request,
        snapshots=snapshots,
        beneficiaries_by_id=beneficiaries_by_id,
        folds=folds,
        strategy_label=request.temporal_strategy,
    )


def ensure_program_validation_setting(db: Session, program: Program) -> ProgramValidationSetting:
    """Return the validation settings record for a program, creating defaults.

    Validation expectations are program-specific because acceptable shadow-mode
    thresholds and prediction windows depend on the operational context.
    """
    setting = db.scalar(
        select(ProgramValidationSetting).where(ProgramValidationSetting.program_id == program.id)
    )
    if setting is not None:
        return setting

    prediction_window_days = 30
    if program.operational_setting is not None:
        prediction_window_days = program.operational_setting.prediction_window_days
    setting = ProgramValidationSetting(
        program_id=program.id,
        shadow_prediction_window_days=prediction_window_days,
    )
    db.add(setting)
    db.commit()
    db.refresh(setting)
    return setting


def _serialize_program_validation_setting(setting: ProgramValidationSetting) -> schemas.ProgramValidationSettingRead:
    return schemas.ProgramValidationSettingRead(
        id=setting.id,
        program_id=setting.program_id,
        shadow_mode_enabled=setting.shadow_mode_enabled,
        shadow_prediction_window_days=setting.shadow_prediction_window_days,
        minimum_precision_at_capacity=setting.minimum_precision_at_capacity,
        minimum_recall_at_capacity=setting.minimum_recall_at_capacity,
        require_fairness_review=setting.require_fairness_review,
        last_evaluation_status=setting.last_evaluation_status,
        last_shadow_run_at=setting.last_shadow_run_at,
        updated_at=setting.updated_at,
    )


def list_program_validation_settings(db: Session) -> list[schemas.ProgramValidationSettingRead]:
    programs = db.scalars(
        select(Program)
        .options(selectinload(Program.operational_setting))
        .order_by(Program.name.asc())
    ).all()
    return [_serialize_program_validation_setting(ensure_program_validation_setting(db, program)) for program in programs]


def update_program_validation_setting(
    db: Session,
    program_id: str,
    payload: schemas.ProgramValidationSettingUpdate,
) -> schemas.ProgramValidationSettingRead:
    program = db.scalar(
        select(Program)
        .options(selectinload(Program.operational_setting))
        .where(Program.id == program_id)
    )
    if program is None:
        raise ValueError("Program not found")
    setting = ensure_program_validation_setting(db, program)
    setting.shadow_mode_enabled = payload.shadow_mode_enabled
    setting.shadow_prediction_window_days = payload.shadow_prediction_window_days
    setting.minimum_precision_at_capacity = payload.minimum_precision_at_capacity
    setting.minimum_recall_at_capacity = payload.minimum_recall_at_capacity
    setting.require_fairness_review = payload.require_fairness_review
    db.add(setting)
    db.commit()
    db.refresh(setting)
    return _serialize_program_validation_setting(setting)


def _serialize_evaluation_report(record: EvaluationReport) -> schemas.ModelEvaluationRecordRead:
    return schemas.ModelEvaluationRecordRead(
        id=record.id,
        created_by_email=record.created_by.email if record.created_by is not None else None,
        program_ids=list(record.program_scope or []),
        cohorts=list(record.cohort_scope or []),
        temporal_strategy=record.temporal_strategy,  # type: ignore[arg-type]
        status=record.status,  # type: ignore[arg-type]
        algorithm=record.algorithm,
        horizon_days=record.horizon_days,
        samples_evaluated=record.samples_evaluated,
        positive_cases=record.positive_cases,
        created_at=record.created_at,
        report=schemas.ModelEvaluationReport(**record.report_payload),
    )


def persist_evaluation_report(
    db: Session,
    *,
    payload: schemas.EvaluationRequest,
    report: schemas.ModelEvaluationReport,
    created_by: User | None = None,
) -> schemas.ModelEvaluationRecordRead:
    """Store a completed evaluation report for later review in the product.

    Persisting evaluation output is important for governance and handoff because
    it creates a durable record of what was tested, how it was tested, and what
    readiness conclusion was reached at that point in time.
    """
    record = EvaluationReport(
        created_by_user_id=created_by.id if created_by is not None else None,
        program_scope=list(payload.program_ids),
        cohort_scope=list(payload.cohorts),
        temporal_strategy=payload.temporal_strategy,
        status=report.status,
        algorithm=report.algorithm,
        horizon_days=report.horizon_days,
        samples_evaluated=report.samples_evaluated,
        positive_cases=report.positive_cases,
        request_payload=payload.model_dump(mode="json"),
        report_payload=report.model_dump(mode="json"),
    )
    db.add(record)

    if payload.program_ids:
        programs = db.scalars(
            select(Program)
            .options(selectinload(Program.operational_setting))
            .where(Program.id.in_(payload.program_ids))
        ).all()
        for program in programs:
            setting = ensure_program_validation_setting(db, program)
            setting.last_evaluation_status = report.status
            db.add(setting)

    db.commit()
    hydrated = db.scalar(
        select(EvaluationReport)
        .options(selectinload(EvaluationReport.created_by))
        .where(EvaluationReport.id == record.id)
    )
    assert hydrated is not None
    return _serialize_evaluation_report(hydrated)


def list_evaluation_reports(
    db: Session,
    *,
    limit: int = 12,
    program_id: str | None = None,
) -> list[schemas.ModelEvaluationRecordRead]:
    records = list(
        db.scalars(
            select(EvaluationReport)
            .options(selectinload(EvaluationReport.created_by))
            .order_by(EvaluationReport.created_at.desc())
            .limit(max(limit * 4, limit))
        ).all()
    )
    if program_id:
        records = [record for record in records if program_id in (record.program_scope or [])]
    return [_serialize_evaluation_report(record) for record in records[:limit]]


def _serialize_shadow_run(run: ShadowRun) -> schemas.ShadowRunRead:
    return schemas.ShadowRunRead(
        id=run.id,
        program_id=run.program_id,
        program_name=run.program.name,
        status=run.status,  # type: ignore[arg-type]
        snapshot_date=run.snapshot_date.isoformat(),
        horizon_days=run.horizon_days,
        top_k_count=run.top_k_count,
        cases_captured=run.cases_captured,
        high_risk_cases=run.high_risk_cases,
        due_now_cases=run.due_now_cases,
        matured_cases=run.matured_cases,
        observed_positive_cases=run.observed_positive_cases,
        actioned_cases=run.actioned_cases,
        top_k_precision=run.top_k_precision,
        top_k_recall=run.top_k_recall,
        note=run.note,
        created_by_email=run.created_by.email if run.created_by is not None else None,
        created_at=run.created_at,
        completed_at=run.completed_at,
    )


def _beneficiary_action_logged(
    beneficiary: Beneficiary,
    *,
    snapshot_date: date,
    horizon_days: int,
) -> bool:
    horizon_end = snapshot_date + timedelta(days=horizon_days)
    for intervention in beneficiary.interventions:
        logged_date = intervention.logged_at.date()
        if snapshot_date < logged_date <= horizon_end:
            return True
    return False


def refresh_shadow_run(db: Session, run: ShadowRun) -> ShadowRun:
    """Update a shadow run with newly observed outcomes and workflow actions.

    Shadow runs mature over time. This helper checks whether originally flagged
    cases later disengaged, re-engaged, or received follow-up actions so the
    system can compare predicted and observed behavior after the fact.
    """
    if not run.cases:
        return run

    beneficiary_ids = [case.beneficiary_id for case in run.cases]
    beneficiaries = db.scalars(
        select(Beneficiary)
        .options(selectinload(Beneficiary.interventions))
        .where(Beneficiary.id.in_(beneficiary_ids))
    ).all()
    beneficiary_by_id = {beneficiary.id: beneficiary for beneficiary in beneficiaries}
    today = utc_today()

    matured_cases = 0
    observed_positive_cases = 0
    actioned_cases = 0
    matured_top_k = 0
    top_k_hits = 0

    for case in run.cases:
        beneficiary = beneficiary_by_id.get(case.beneficiary_id)
        if beneficiary is None:
            continue
        horizon_end = case.snapshot_date + timedelta(days=run.horizon_days)
        observed_cutoff = min(horizon_end, today)
        action_logged = _beneficiary_action_logged(
            beneficiary,
            snapshot_date=case.snapshot_date,
            horizon_days=run.horizon_days,
        )
        case.action_logged = action_logged
        if case.included_in_top_k and action_logged:
            actioned_cases += 1

        observed_outcome = "pending"
        observed_at: date | None = None
        if beneficiary.dropout_date is not None and case.snapshot_date < beneficiary.dropout_date <= observed_cutoff:
            observed_outcome = "disengaged"
            observed_at = beneficiary.dropout_date
        elif beneficiary.completion_date is not None and case.snapshot_date < beneficiary.completion_date <= observed_cutoff:
            observed_outcome = "completed"
            observed_at = beneficiary.completion_date
        elif today >= horizon_end:
            observed_outcome = "retained"
            observed_at = horizon_end

        case.observed_outcome = observed_outcome
        case.observed_at = observed_at
        db.add(case)

        if observed_outcome != "pending":
            matured_cases += 1
            if case.included_in_top_k:
                matured_top_k += 1
        if observed_outcome == "disengaged":
            observed_positive_cases += 1
            if case.included_in_top_k:
                top_k_hits += 1

    run.matured_cases = matured_cases
    run.observed_positive_cases = observed_positive_cases
    run.actioned_cases = actioned_cases
    run.top_k_precision = round(top_k_hits / matured_top_k, 4) if matured_top_k > 0 else None
    run.top_k_recall = round(top_k_hits / observed_positive_cases, 4) if observed_positive_cases > 0 else None
    if matured_cases == 0:
        run.status = "captured"
        run.completed_at = None
        run.note = "Shadow run captured. Waiting for enough time to observe outcomes."
    elif matured_cases < run.cases_captured:
        run.status = "partial_followup"
        run.completed_at = None
        run.note = f"{matured_cases} of {run.cases_captured} shadow cases have observed outcomes so far."
    else:
        run.status = "matured"
        run.completed_at = utc_now()
        run.note = (
            f"Observed {observed_positive_cases} disengagement outcomes across {matured_cases} matured shadow cases. "
            f"Precision at capacity is {run.top_k_precision if run.top_k_precision is not None else 'n/a'}."
        )
    db.add(run)
    db.commit()
    db.refresh(run)
    return run


def create_shadow_run(
    db: Session,
    *,
    program_id: str,
    payload: schemas.ShadowRunCreateRequest,
    created_by: User | None = None,
) -> schemas.ShadowRunRead:
    """Capture a shadow-mode snapshot for later observational validation.

    A shadow run freezes what the queue looked like at one moment in time for a
    given program and capacity setting. It is one of the main mechanisms for
    building prospective evidence before live reliance on the model.
    """
    program = db.scalar(
        select(Program)
        .options(selectinload(Program.operational_setting), selectinload(Program.validation_setting))
        .where(Program.id == program_id)
    )
    if program is None:
        raise ValueError("Program not found")
    setting = ensure_program_validation_setting(db, program)
    from app.services.analytics import build_risk_cases, ensure_program_operational_setting

    operational_setting = ensure_program_operational_setting(db, program)
    beneficiary_ids = {
        beneficiary_id
        for beneficiary_id, in db.execute(select(Beneficiary.id).where(Beneficiary.program_id == program.id)).all()
    }
    scoped_cases = [case for case in build_risk_cases(db) if case.id in beneficiary_ids]
    if not scoped_cases:
        raise ValueError("No active risk cases are available for this program.")

    top_k_count = payload.top_k_count or min(operational_setting.weekly_followup_capacity, len(scoped_cases))
    run = ShadowRun(
        program_id=program.id,
        created_by_user_id=created_by.id if created_by is not None else None,
        snapshot_date=utc_today(),
        horizon_days=setting.shadow_prediction_window_days,
        top_k_count=top_k_count,
        cases_captured=len(scoped_cases),
        high_risk_cases=sum(1 for case in scoped_cases if case.risk_level == "High"),
        due_now_cases=sum(1 for case in scoped_cases if case.queue_bucket == "Due now"),
        note=payload.note,
    )
    db.add(run)
    db.flush()

    for index, case in enumerate(scoped_cases):
        db.add(
            ShadowRunCase(
                shadow_run_id=run.id,
                beneficiary_id=case.id,
                snapshot_date=run.snapshot_date,
                rank_order=index + 1,
                included_in_top_k=index < top_k_count,
                risk_level=case.risk_level,
                risk_score=case.risk_score,
                queue_bucket=case.queue_bucket,
                queue_rank=case.queue_rank,
                assigned_worker=case.assigned_worker,
                assigned_site=case.assigned_site,
                recommended_action=case.recommended_action[:255],
            )
        )

    setting.last_shadow_run_at = utc_now()
    db.add(setting)
    db.commit()

    hydrated = db.scalar(
        select(ShadowRun)
        .options(
            selectinload(ShadowRun.program),
            selectinload(ShadowRun.created_by),
            selectinload(ShadowRun.cases),
        )
        .where(ShadowRun.id == run.id)
    )
    assert hydrated is not None
    hydrated = refresh_shadow_run(db, hydrated)
    hydrated = db.scalar(
        select(ShadowRun)
        .options(selectinload(ShadowRun.program), selectinload(ShadowRun.created_by))
        .where(ShadowRun.id == run.id)
    )
    assert hydrated is not None
    return _serialize_shadow_run(hydrated)


def list_shadow_runs(
    db: Session,
    *,
    limit: int = 12,
    program_id: str | None = None,
) -> list[schemas.ShadowRunRead]:
    statement = (
        select(ShadowRun)
        .options(
            selectinload(ShadowRun.program),
            selectinload(ShadowRun.created_by),
            selectinload(ShadowRun.cases),
        )
        .order_by(ShadowRun.created_at.desc())
        .limit(max(limit * 3, limit))
    )
    runs = list(db.scalars(statement).all())
    if program_id:
        runs = [run for run in runs if run.program_id == program_id]
    serialized: list[schemas.ShadowRunRead] = []
    for run in runs[:limit]:
        refreshed = refresh_shadow_run(db, run)
        hydrated = db.scalar(
            select(ShadowRun)
            .options(selectinload(ShadowRun.program), selectinload(ShadowRun.created_by))
            .where(ShadowRun.id == refreshed.id)
        )
        assert hydrated is not None
        serialized.append(_serialize_shadow_run(hydrated))
    return serialized
