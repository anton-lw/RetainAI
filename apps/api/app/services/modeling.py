"""Model training, feature engineering, and scoring support.

This is the largest ML-focused service in the codebase. It builds feature
contexts from operational data, trains program-aware tabular models, tracks
artifacts and metrics, generates explainability outputs, and exposes helpers
used by both live scoring and formal evaluation workflows.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any
import warnings

import joblib
import numpy as np
from scipy.sparse import csr_matrix
from sklearn.ensemble import RandomForestClassifier
from sklearn.feature_extraction import DictVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import f1_score, precision_score, recall_score, roc_auc_score
from sklearn.model_selection import train_test_split
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app import schemas
from app.core.config import get_settings
from app.models import Beneficiary, FeatureSnapshot, ModelBiasAudit, ModelDriftReport, ModelVersion, Program
from app.services.federated import latest_federated_prior
from app.services.labeling import (
    build_operational_settings_profile,
    candidate_training_snapshots,
    eligible_for_predictive_modeling,
)
from app.services.modelops import log_training_run
from app.services.nlp import analyze_note_sentiment
from app.services.scoring import assess_beneficiary_risk

try:
    import xgboost as xgb
    from xgboost import XGBClassifier
except Exception:  # pragma: no cover - optional dependency fallback
    xgb = None
    XGBClassifier = None

try:
    from lightgbm import LGBMClassifier
except Exception:  # pragma: no cover - optional dependency fallback
    LGBMClassifier = None

try:
    import shap
except Exception:  # pragma: no cover - optional dependency fallback
    shap = None


settings = get_settings()

KEYWORD_FEATURES = {
    "displacement": "notes_kw_displacement",
    "relocation": "notes_kw_displacement",
    "migration": "notes_kw_migration",
    "harvest": "notes_kw_migration",
    "food": "notes_kw_food_insecurity",
    "fee": "notes_kw_fee_barrier",
    "transport": "notes_kw_transport",
    "illness": "notes_kw_illness",
    "flood": "notes_kw_shock_event",
}

BIAS_AUDIT_DIMENSIONS = ("gender", "region", "household_type")
BIAS_MIN_GROUP_SAMPLES = 5
BIAS_MIN_POSITIVE_SAMPLES = 3
BIAS_MIN_NEGATIVE_SAMPLES = 3
BIAS_FPR_GAP_ALERT = 0.15
BIAS_RECALL_GAP_ALERT = 0.2
PSI_ALERT_THRESHOLD = 0.2
DRIFT_FEATURE_LIMIT = 10
PROGRAM_SPECIFIC_MIN_ROWS = 120
PROGRAM_SPECIFIC_MIN_POSITIVES = 8
PROGRAM_SPECIFIC_MIN_NEGATIVES = 8


@dataclass
class FeatureContext:
    features: dict[str, float | str]
    last_contact_days: int
    attendance_rate_30d: int
    consecutive_missed_events: int
    response_rate: float
    feature_coverage_ratio: float


@dataclass
class TrainingSample:
    beneficiary_id: str
    program_id: str
    program_type: str
    features: dict[str, float | str]
    label: int
    audit_groups: dict[str, str]
    label_source: str = "hard"
    sample_weight: float = 1.0
    label_probability: float | None = None
    snapshot_date: date | None = None


@dataclass
class LoadedModel:
    version: ModelVersion
    vectorizer: DictVectorizer
    algorithm: str
    components: dict[str, Any]
    feature_names: list[str]
    training_profile: dict[str, Any]


@dataclass
class ModelPrediction:
    risk_score: int
    risk_level: str
    explanation: str
    flags: list[str]
    confidence: str
    uncertainty_score: float


def _phase_bucket(phase: str | None) -> str:
    if not phase:
        return "unknown"

    normalized = phase.lower()
    if any(token in normalized for token in ("onboarding", "month 1", "month 2", "month 3", "transition", "visit 2")):
        return "early_transition"
    if any(token in normalized for token in ("term break", "exam", "postnatal", "post-visit", "re_entry")):
        return "checkpoint"
    return "steady_state"


def _latest_contact_days(events: list[Any], today: date) -> int:
    for event in sorted(events, key=lambda item: item.event_date, reverse=True):
        if event.successful:
            return max(0, (today - event.event_date).days)
    return 999


def build_feature_context(
    beneficiary: Beneficiary,
    *,
    as_of_date: date | None = None,
    events: list[Any] | None = None,
    interventions: list[Any] | None = None,
) -> FeatureContext:
    """Derive the model feature context for one beneficiary at a point in time.

    The optional ``as_of_date`` and explicit ``events`` / ``interventions``
    parameters are important: they let the same feature builder support both
    live scoring and leakage-safe retrospective evaluation.
    """
    today = as_of_date or date.today()
    if events is None:
        events = [
            event
            for event in beneficiary.monitoring_events
            if event.event_date <= today
        ]
    if interventions is None:
        interventions = [
            intervention
            for intervention in beneficiary.interventions
            if intervention.logged_at.date() <= today
        ]
    events = sorted(list(events), key=lambda item: item.event_date, reverse=True)
    interventions = sorted(list(interventions), key=lambda item: item.logged_at, reverse=True)

    last_contact_days = _latest_contact_days(events, today)
    recent_30 = [event for event in events if (today - event.event_date).days <= 30]
    recent_60 = [event for event in events if (today - event.event_date).days <= 60]
    recent_90 = [event for event in events if (today - event.event_date).days <= 90]

    def attendance_rate(window_events: list[Any]) -> float:
        if not window_events:
            return 100.0
        relevant = [
            event
            for event in window_events
            if event.event_type in {"attendance", "checkin", "clinic_visit", "payment_collection", "session", "visit"}
        ] or window_events
        if not relevant:
            return 100.0
        return round((sum(1 for event in relevant if event.successful) / len(relevant)) * 100, 2)

    attendance_30 = attendance_rate(recent_30)
    attendance_60 = attendance_rate(recent_60)
    attendance_90 = attendance_rate(recent_90)

    consecutive_missed = 0
    for event in events:
        if event.successful:
            break
        consecutive_missed += 1

    outreach_events = [event for event in events if event.response_received is not None]
    if outreach_events:
        response_rate = round(
            sum(1 for event in outreach_events if event.response_received) / len(outreach_events),
            3,
        )
    else:
        response_rate = 1.0

    months_since_enrollment = max(0, (today - beneficiary.enrollment_date).days / 30)
    notes_blob = " ".join(
        [beneficiary.current_note or "", *(event.notes or "" for event in events[:5])]
    ).lower()
    notes_sentiment_score, notes_sentiment_label = analyze_note_sentiment(notes_blob)

    keyword_flags = {feature_name: 0.0 for feature_name in KEYWORD_FEATURES.values()}
    for keyword, feature_name in KEYWORD_FEATURES.items():
        if keyword in notes_blob:
            keyword_flags[feature_name] = 1.0

    recent_intervention_success = 0.0
    if interventions and interventions[0].successful is True:
        recent_intervention_success = 1.0

    outreach_count_30d = sum(1 for event in recent_30 if event.response_received is not None)
    month_of_year = float(today.month)
    enrollment_month = float(beneficiary.enrollment_date.month)
    no_recent_events = 1.0 if not recent_30 else 0.0
    missed_rate_90d = round(max(0.0, 100.0 - attendance_90), 2)

    features: dict[str, float | str] = {
        "program_type": beneficiary.program.program_type or "unknown",
        "region": beneficiary.region or "unknown",
        "assigned_site": beneficiary.assigned_site or beneficiary.region or "unknown",
        "assigned_case_worker": beneficiary.assigned_case_worker or "unknown",
        "cohort": beneficiary.cohort or "unknown",
        "phase_bucket": _phase_bucket(beneficiary.phase),
        "gender": beneficiary.gender or "unknown",
        "delivery_modality": beneficiary.delivery_modality or beneficiary.program.delivery_modality or "unknown",
        "household_type": beneficiary.household_type or "unknown",
        "days_since_last_contact": float(last_contact_days),
        "events_last_30": float(len(recent_30)),
        "events_last_60": float(len(recent_60)),
        "events_last_90": float(len(recent_90)),
        "attendance_rate_30d": float(attendance_30),
        "attendance_rate_60d": float(attendance_60),
        "attendance_rate_90d": float(attendance_90),
        "attendance_delta_30_90": float(attendance_30 - attendance_90),
        "missed_rate_90d": float(missed_rate_90d),
        "consecutive_missed_events": float(consecutive_missed),
        "response_rate": float(response_rate),
        "outreach_count_30d": float(outreach_count_30d),
        "months_since_enrollment": float(months_since_enrollment),
        "month_of_year": month_of_year,
        "enrollment_month": enrollment_month,
        "no_recent_events": no_recent_events,
        "household_size": float(beneficiary.household_size or 0),
        "pmt_score": float(beneficiary.pmt_score or 0),
        "food_insecurity_index": float(beneficiary.food_insecurity_index or 0),
        "distance_to_service_km": float(beneficiary.distance_to_service_km or 0),
        "household_stability_signal": float(beneficiary.household_stability_signal or 0),
        "economic_stress_signal": float(beneficiary.economic_stress_signal or 0),
        "family_support_signal": float(beneficiary.family_support_signal or 0),
        "health_change_signal": float(beneficiary.health_change_signal or 0),
        "motivation_signal": float(beneficiary.motivation_signal or 0),
        "pmt_score_missing": 1.0 if beneficiary.pmt_score is None else 0.0,
        "food_insecurity_missing": 1.0 if beneficiary.food_insecurity_index is None else 0.0,
        "distance_missing": 1.0 if beneficiary.distance_to_service_km is None else 0.0,
        "household_stability_missing": 1.0 if beneficiary.household_stability_signal is None else 0.0,
        "economic_stress_missing": 1.0 if beneficiary.economic_stress_signal is None else 0.0,
        "family_support_missing": 1.0 if beneficiary.family_support_signal is None else 0.0,
        "health_change_missing": 1.0 if beneficiary.health_change_signal is None else 0.0,
        "motivation_missing": 1.0 if beneficiary.motivation_signal is None else 0.0,
        "recent_intervention_success": recent_intervention_success,
        "notes_sentiment_score": float(notes_sentiment_score),
        "notes_sentiment_label": notes_sentiment_label,
    }
    features.update(keyword_flags)

    known_fields = [
        beneficiary.phase,
        beneficiary.cohort,
        beneficiary.gender,
        beneficiary.household_type,
        beneficiary.pmt_score,
        beneficiary.food_insecurity_index,
        beneficiary.distance_to_service_km,
        beneficiary.household_stability_signal,
        beneficiary.economic_stress_signal,
        beneficiary.family_support_signal,
        beneficiary.health_change_signal,
        beneficiary.motivation_signal,
        beneficiary.current_note,
    ]
    feature_coverage_ratio = round(sum(1 for value in known_fields if value not in (None, "")) / len(known_fields), 3)

    return FeatureContext(
        features=features,
        last_contact_days=last_contact_days,
        attendance_rate_30d=int(round(attendance_30)),
        consecutive_missed_events=consecutive_missed,
        response_rate=response_rate,
        feature_coverage_ratio=feature_coverage_ratio,
    )


def _audit_groups_for(beneficiary: Beneficiary) -> dict[str, str]:
    return {
        "gender": beneficiary.gender or "Unknown",
        "region": beneficiary.region or "Unknown",
        "household_type": beneficiary.household_type or "Unknown",
    }


def _rate(numerator: int, denominator: int) -> float | None:
    if denominator <= 0:
        return None
    return round(numerator / denominator, 4)


def _gap(values: list[float | None]) -> float | None:
    observed = [value for value in values if value is not None]
    if len(observed) < 2:
        return None
    return round(max(observed) - min(observed), 4)


def _dimension_label(dimension: str) -> str:
    labels = {
        "gender": "gender",
        "region": "geography",
        "household_type": "household type",
    }
    return labels.get(dimension, dimension.replace("_", " "))


def _dimension_note(dimension: str, status: str, fpr_gap: float | None, recall_gap: float | None) -> str:
    label = _dimension_label(dimension)
    if status == "attention":
        fpr_text = f"false-positive gap {fpr_gap:.2f}" if fpr_gap is not None else "false-positive gap unavailable"
        recall_text = f"recall gap {recall_gap:.2f}" if recall_gap is not None else "recall gap unavailable"
        return (
            f"{label.title()} shows a material disparity in the current validation sample "
            f"({fpr_text}; {recall_text}). Review thresholding and follow-up operations before relying on this model for prioritization."
        )
    if status == "ok":
        return f"No large disparity gaps were detected across {label} in the current validation sample."
    return f"There is not enough labeled validation data to assess {label} reliably yet."


def _group_guidance(dimension: str, group_name: str, severity: str) -> str | None:
    if severity != "attention":
        return None
    if dimension == "gender":
        return f"Check whether outreach coverage or prior follow-up is systematically different for {group_name.lower()} beneficiaries."
    if dimension == "region":
        return f"Check whether travel burden, staffing intensity, or collection logistics differ in {group_name}."
    if dimension == "household_type":
        return f"Check whether program conditions or follow-up workflows fit {group_name.lower()} households as well as other groups."
    return "Review operational context for this group before acting on the model alone."


def _group_severity(
    sample_size: int,
    positive_count: int,
    negative_count: int,
    *,
    dimension_status: str,
    false_positive_rate: float | None,
    recall_rate: float | None,
    max_false_positive_rate: float | None,
    min_recall_rate: float | None,
) -> str:
    if sample_size < BIAS_MIN_GROUP_SAMPLES or (
        positive_count < BIAS_MIN_POSITIVE_SAMPLES and negative_count < BIAS_MIN_NEGATIVE_SAMPLES
    ):
        return "insufficient_data"
    if dimension_status != "attention":
        return "ok"
    if (
        false_positive_rate is not None
        and max_false_positive_rate is not None
        and abs(false_positive_rate - max_false_positive_rate) < 1e-9
    ):
        return "attention"
    if (
        recall_rate is not None
        and min_recall_rate is not None
        and abs(recall_rate - min_recall_rate) < 1e-9
    ):
        return "attention"
    return "ok"


def _build_bias_audit_records(
    samples: list[TrainingSample],
    probabilities: np.ndarray,
) -> list[dict[str, str | int | float | None]]:
    predicted_positive = (probabilities >= 0.5).astype(int)
    audit_records: list[dict[str, str | int | float | None]] = []

    for dimension in BIAS_AUDIT_DIMENSIONS:
        grouped: dict[str, list[tuple[int, int]]] = defaultdict(list)
        for sample, prediction in zip(samples, predicted_positive, strict=False):
            grouped[sample.audit_groups[dimension]].append((sample.label, int(prediction)))

        dimension_rows: list[dict[str, str | int | float | None]] = []
        fpr_values: list[float | None] = []
        recall_values: list[float | None] = []

        for group_name, rows in grouped.items():
            sample_size = len(rows)
            positive_count = sum(label for label, _ in rows)
            negative_count = sample_size - positive_count
            predicted_positive_count = sum(prediction for _, prediction in rows)
            false_positives = sum(1 for label, prediction in rows if label == 0 and prediction == 1)
            true_positives = sum(1 for label, prediction in rows if label == 1 and prediction == 1)

            false_positive_rate = (
                _rate(false_positives, negative_count)
                if negative_count >= BIAS_MIN_NEGATIVE_SAMPLES
                else None
            )
            recall_rate = _rate(true_positives, positive_count) if positive_count >= BIAS_MIN_POSITIVE_SAMPLES else None
            flagged_rate = _rate(predicted_positive_count, sample_size)

            dimension_rows.append(
                {
                    "dimension": dimension,
                    "group_name": group_name,
                    "sample_size": sample_size,
                    "positive_count": positive_count,
                    "predicted_positive_count": predicted_positive_count,
                    "flagged_rate": flagged_rate,
                    "false_positive_rate": false_positive_rate,
                    "recall_rate": recall_rate,
                }
            )
            if sample_size >= BIAS_MIN_GROUP_SAMPLES:
                fpr_values.append(false_positive_rate)
                recall_values.append(recall_rate)

        fpr_gap = _gap(fpr_values)
        recall_gap = _gap(recall_values)
        if fpr_gap is None and recall_gap is None:
            dimension_status = "insufficient_data"
        elif (
            (fpr_gap is not None and fpr_gap >= BIAS_FPR_GAP_ALERT)
            or (recall_gap is not None and recall_gap >= BIAS_RECALL_GAP_ALERT)
        ):
            dimension_status = "attention"
        else:
            dimension_status = "ok"

        max_false_positive_rate = max((value for value in fpr_values if value is not None), default=None)
        min_recall_rate = min((value for value in recall_values if value is not None), default=None)

        for row in dimension_rows:
            negative_count = int(row["sample_size"]) - int(row["positive_count"])
            severity = _group_severity(
                int(row["sample_size"]),
                int(row["positive_count"]),
                negative_count,
                dimension_status=dimension_status,
                false_positive_rate=row["false_positive_rate"] if isinstance(row["false_positive_rate"], float) else None,
                recall_rate=row["recall_rate"] if isinstance(row["recall_rate"], float) else None,
                max_false_positive_rate=max_false_positive_rate,
                min_recall_rate=min_recall_rate,
            )
            row["severity"] = severity
            row["guidance"] = _group_guidance(dimension, str(row["group_name"]), severity)
            audit_records.append(row)

    return audit_records


def _build_bias_audit_summary(audits: list[ModelBiasAudit]) -> schemas.BiasAuditSummary:
    if not audits:
        return schemas.BiasAuditSummary(
            status="insufficient_data",
            note="Bias auditing has not been run yet because there is not enough labeled validation data.",
            dimensions=[],
        )

    grouped: dict[str, list[ModelBiasAudit]] = defaultdict(list)
    for audit in audits:
        grouped[audit.dimension].append(audit)

    dimensions: list[schemas.BiasAuditDimension] = []
    overall_status = "ok"

    for dimension in BIAS_AUDIT_DIMENSIONS:
        rows = grouped.get(dimension, [])
        if not rows:
            continue

        fpr_gap = _gap([row.false_positive_rate for row in rows])
        recall_gap = _gap([row.recall_rate for row in rows])
        if any(row.severity == "attention" for row in rows):
            status = "attention"
            overall_status = "attention"
        elif all(row.severity == "insufficient_data" for row in rows):
            status = "insufficient_data"
            if overall_status != "attention":
                overall_status = "insufficient_data"
        else:
            status = "ok"

        dimensions.append(
            schemas.BiasAuditDimension(
                dimension=dimension,
                status=status,  # type: ignore[arg-type]
                note=_dimension_note(dimension, status, fpr_gap, recall_gap),
                max_false_positive_gap=fpr_gap,
                max_recall_gap=recall_gap,
                groups=[
                    schemas.BiasAuditGroup(
                        group_name=row.group_name,
                        sample_size=row.sample_size,
                        positive_count=row.positive_count,
                        predicted_positive_count=row.predicted_positive_count,
                        flagged_rate=row.flagged_rate,
                        false_positive_rate=row.false_positive_rate,
                        recall_rate=row.recall_rate,
                        severity=row.severity,  # type: ignore[arg-type]
                        guidance=row.guidance,
                    )
                    for row in rows
                ],
            )
        )

    overall_note = "Bias audit did not detect large disparity gaps in the current validation sample."
    if overall_status == "attention":
        overall_note = "One or more monitored groups show a meaningful disparity gap. Review the detailed audit before relying on the model operationally."
    elif overall_status == "insufficient_data":
        overall_note = "Some monitored groups do not yet have enough labeled validation data for a reliable fairness audit."

    return schemas.BiasAuditSummary(
        status=overall_status,  # type: ignore[arg-type]
        note=overall_note,
        dimensions=dimensions,
    )


def _load_training_beneficiaries(db: Session) -> list[Beneficiary]:
    statement = (
        select(Beneficiary)
        .options(
            selectinload(Beneficiary.program).selectinload(Program.operational_setting),
            selectinload(Beneficiary.program).selectinload(Program.data_policy),
            selectinload(Beneficiary.monitoring_events),
            selectinload(Beneficiary.interventions),
        )
        .order_by(Beneficiary.created_at.desc())
    )
    return list(db.scalars(statement).unique().all())


def _share_to_threshold(probabilities: np.ndarray, share: float) -> float:
    bounded_share = min(1.0, max(0.01, share))
    ranked = np.sort(probabilities)[::-1]
    index = max(0, min(len(ranked) - 1, int(np.ceil(len(ranked) * bounded_share)) - 1))
    return float(ranked[index])


def _classification_metrics_at_threshold(
    y_true: np.ndarray,
    probabilities: np.ndarray,
    threshold: float,
) -> tuple[float, float, float]:
    thresholded = (probabilities >= threshold).astype(int)
    precision = round(float(precision_score(y_true, thresholded, zero_division=0)), 4)
    recall = round(float(recall_score(y_true, thresholded, zero_division=0)), 4)
    flagged_share = round(float(np.mean(thresholded)), 4) if len(thresholded) else 0.0
    return precision, recall, flagged_share


def _operational_threshold_metrics(y_true: np.ndarray, probabilities: np.ndarray) -> dict[str, float]:
    if len(probabilities) == 0:
        return {
            "high_risk_threshold_score": 75.0,
            "medium_risk_threshold_score": 50.0,
            "high_risk_queue_share": 0.15,
            "medium_risk_queue_share": 0.35,
            "high_risk_precision": 0.0,
            "high_risk_recall": 0.0,
            "medium_or_higher_precision": 0.0,
            "medium_or_higher_recall": 0.0,
        }

    positive_rate = float(np.mean(y_true)) if len(y_true) else 0.0
    high_risk_share = min(0.2, max(0.08, round(max(positive_rate * 0.6, 0.12), 2)))
    medium_risk_share = min(0.45, max(high_risk_share + 0.1, round(max(positive_rate * 1.4, 0.3), 2)))

    high_threshold = _share_to_threshold(probabilities, high_risk_share)
    medium_threshold = min(high_threshold, _share_to_threshold(probabilities, medium_risk_share))

    high_precision, high_recall, resolved_high_share = _classification_metrics_at_threshold(
        y_true,
        probabilities,
        high_threshold,
    )
    medium_precision, medium_recall, resolved_medium_share = _classification_metrics_at_threshold(
        y_true,
        probabilities,
        medium_threshold,
    )

    return {
        "high_risk_threshold_score": round(high_threshold * 100, 2),
        "medium_risk_threshold_score": round(medium_threshold * 100, 2),
        "high_risk_queue_share": resolved_high_share,
        "medium_risk_queue_share": resolved_medium_share,
        "high_risk_precision": high_precision,
        "high_risk_recall": high_recall,
        "medium_or_higher_precision": medium_precision,
        "medium_or_higher_recall": medium_recall,
    }


def _metric_summary(y_true: np.ndarray, probabilities: np.ndarray, labels: np.ndarray) -> dict[str, float]:
    thresholded = (probabilities >= 0.5).astype(int)
    metrics: dict[str, float] = {
        "precision": round(float(precision_score(y_true, thresholded, zero_division=0)), 4),
        "recall": round(float(recall_score(y_true, thresholded, zero_division=0)), 4),
        "f1": round(float(f1_score(y_true, thresholded, zero_division=0)), 4),
    }

    try:
        metrics["auc_roc"] = round(float(roc_auc_score(y_true, probabilities)), 4)
    except ValueError:
        metrics["auc_roc"] = 0.0

    positives = int(np.sum(y_true))
    if positives > 0:
        top_k = max(1, int(np.ceil(len(probabilities) * 0.2)))
        top_indices = np.argsort(probabilities)[::-1][:top_k]
        metrics["top_20pct_recall"] = round(float(np.sum(y_true[top_indices]) / positives), 4)
    else:
        metrics["top_20pct_recall"] = 0.0

    metrics.update(_operational_threshold_metrics(y_true, probabilities))
    metrics["samples_evaluated"] = float(len(labels))
    return metrics


def _human_driver_name(feature_name: str) -> str:
    explicit_labels = {
        "days_since_last_contact": "Days since last contact",
        "attendance_rate_30d": "30-day attendance rate",
        "attendance_rate_60d": "60-day attendance rate",
        "attendance_rate_90d": "90-day attendance rate",
        "attendance_delta_30_90": "Attendance trend",
        "missed_rate_90d": "90-day missed-event rate",
        "consecutive_missed_events": "Consecutive missed events",
        "response_rate": "Outreach response rate",
        "outreach_count_30d": "Outreach attempts in last 30 days",
        "months_since_enrollment": "Time since enrollment",
        "food_insecurity_index": "Food insecurity score",
        "distance_to_service_km": "Distance to service point",
        "pmt_score": "Proxy means or vulnerability score",
        "household_stability_signal": "Household stability signal",
        "economic_stress_signal": "Economic stress signal",
        "family_support_signal": "Family support signal",
        "health_change_signal": "Health change signal",
        "motivation_signal": "Motivation signal",
        "recent_intervention_success": "Recent intervention success",
        "notes_sentiment_score": "Field-note sentiment",
        "notes_sentiment_label=negative": "Negative field-note sentiment",
        "notes_sentiment_label=positive": "Positive field-note sentiment",
        "notes_kw_displacement": "Displacement or relocation note",
        "notes_kw_migration": "Migration or harvest note",
        "notes_kw_food_insecurity": "Food insecurity note",
        "notes_kw_fee_barrier": "Fee or cost barrier note",
        "notes_kw_transport": "Transport barrier note",
        "notes_kw_illness": "Illness note",
        "notes_kw_shock_event": "Shock event note",
        "month_of_year": "Month of year",
        "no_recent_events": "No recent events",
    }
    if feature_name in explicit_labels:
        return explicit_labels[feature_name]
    if "=" in feature_name:
        left, right = feature_name.split("=", 1)
        return f"{left.replace('_', ' ').title()}: {right.replace('_', ' ')}"
    return feature_name.replace("_", " ").title()


def _feature_explanation(feature_name: str, context: FeatureContext) -> tuple[str, str] | None:
    lookup = {
        "days_since_last_contact": (
            "Long gap since last contact",
            f"No successful contact has been recorded in {context.last_contact_days} days.",
        ),
        "attendance_rate_30d": (
            "Recent attendance decline",
            f"Only {context.attendance_rate_30d}% of recent attendance or contact events were completed successfully over the last 30 days.",
        ),
        "attendance_delta_30_90": (
            "Attendance trend decline",
            "Recent attendance is weaker than the longer-term pattern for this beneficiary.",
        ),
        "missed_rate_90d": (
            "High missed-event rate",
            "A high share of recent events over the last 90 days were unsuccessful.",
        ),
        "consecutive_missed_events": (
            "Multiple consecutive misses",
            f"{context.consecutive_missed_events} recent monitoring events were missed consecutively.",
        ),
        "response_rate": (
            "Low response to outreach",
            "Recent outreach attempts are receiving fewer responses than expected.",
        ),
        "food_insecurity_index": (
            "Food insecurity flagged",
            "Household food insecurity indicators are elevated.",
        ),
        "distance_to_service_km": (
            "High travel burden",
            "Distance to the service point remains high for this beneficiary.",
        ),
        "pmt_score": (
            "Economic vulnerability at enrollment",
            "Vulnerability scoring at enrollment indicates household stress.",
        ),
        "household_stability_signal": (
            "Household instability observed",
            "The assigned field worker recorded elevated household instability during recent follow-up.",
        ),
        "economic_stress_signal": (
            "Economic stress observed",
            "Field observations suggest the household is under unusual economic pressure.",
        ),
        "family_support_signal": (
            "Family support risk observed",
            "Recent field observations indicate weaker family or caregiver support than expected.",
        ),
        "health_change_signal": (
            "Health deterioration observed",
            "Field observations suggest a recent health change that may disrupt participation.",
        ),
        "motivation_signal": (
            "Motivation decline observed",
            "Field observations suggest the beneficiary's motivation or engagement has weakened.",
        ),
        "notes_kw_displacement": (
            "Displacement or relocation noted",
            "Recent notes mention displacement or relocation risk.",
        ),
        "notes_kw_migration": (
            "Seasonal mobility pressure",
            "Recent notes suggest migration or seasonal mobility pressure.",
        ),
        "notes_kw_food_insecurity": (
            "Food insecurity noted in field reports",
            "Recent notes explicitly reference food insecurity or food stress.",
        ),
        "notes_kw_fee_barrier": (
            "Cost barrier flagged",
            "Recent notes mention fee pressure or a direct cost barrier.",
        ),
        "notes_kw_transport": (
            "Transport barrier flagged",
            "Recent notes mention transport or travel constraints.",
        ),
        "notes_kw_illness": (
            "Health shock flagged",
            "Recent notes mention illness or treatment disruption.",
        ),
        "notes_kw_shock_event": (
            "Shock event flagged",
            "Recent notes mention flooding or another external disruption.",
        ),
        "notes_sentiment_score": (
            "Negative field-note sentiment",
            "Recent free-text notes carry a more negative tone than the program baseline, which often signals unresolved barriers.",
        ),
        "notes_sentiment_label=negative": (
            "Negative field-note sentiment",
            "Recent free-text notes were classified as negative, suggesting barriers that may require supportive follow-up.",
        ),
        "phase_bucket=early_transition": (
            "Early-program or transition phase",
            "The beneficiary is currently in an early-program or transition phase where dropout often spikes.",
        ),
        "phase_bucket=checkpoint": (
            "Known transition-point dropout risk",
            "The beneficiary is at a checkpoint where dropout often rises.",
        ),
        "no_recent_events": (
            "No recent monitoring activity",
            "No monitoring or engagement events were recorded in the last 30 days.",
        ),
    }
    return lookup.get(feature_name)


def _model_driver_payload(feature_names: list[str], coefficients: np.ndarray, limit: int = 8) -> list[dict[str, float | str]]:
    ordered_indices = np.argsort(np.abs(coefficients))[::-1][:limit]
    drivers: list[dict[str, float | str]] = []
    for index in ordered_indices:
        weight = float(coefficients[index])
        drivers.append(
            {
                "name": _human_driver_name(feature_names[index]),
                "weight": round(abs(weight), 4),
                "direction": "increases_risk" if weight > 0 else "reduces_risk",
            }
        )
    return drivers


def _normalize_importances(values: np.ndarray) -> np.ndarray:
    if values.size == 0:
        return values
    max_value = float(np.max(np.abs(values)))
    if max_value <= 0:
        return np.zeros_like(values)
    return np.abs(values) / max_value


def _serialize_feature_value(value: float | str) -> float | str:
    return round(value, 6) if isinstance(value, float) else value


def _persist_feature_snapshots(
    db: Session,
    samples: list[TrainingSample],
    model_version: ModelVersion,
    *,
    source_kind: str,
) -> None:
    for sample in samples:
        db.add(
            FeatureSnapshot(
                beneficiary_id=sample.beneficiary_id,
                model_version_id=model_version.id,
                source_kind=source_kind,
                snapshot_date=sample.snapshot_date or date.today(),
                label=sample.label,
                values={key: _serialize_feature_value(value) for key, value in sample.features.items()},
            )
        )


def persist_scoring_snapshot(
    db: Session,
    beneficiary: Beneficiary,
    *,
    model_version: ModelVersion | None,
    feature_values: dict[str, float | str],
    uncertainty_score: float,
) -> None:
    statement = select(FeatureSnapshot).where(
        FeatureSnapshot.beneficiary_id == beneficiary.id,
        FeatureSnapshot.source_kind == "scoring",
        FeatureSnapshot.snapshot_date == date.today(),
    )
    if model_version is None:
        statement = statement.where(FeatureSnapshot.model_version_id.is_(None))
    else:
        statement = statement.where(FeatureSnapshot.model_version_id == model_version.id)

    snapshot = db.scalar(statement.limit(1))
    serialized_values = {key: _serialize_feature_value(value) for key, value in feature_values.items()}
    if snapshot is None:
        db.add(
            FeatureSnapshot(
                beneficiary_id=beneficiary.id,
                model_version_id=model_version.id if model_version is not None else None,
                source_kind="scoring",
                snapshot_date=date.today(),
                label=None,
                uncertainty_score=uncertainty_score,
                values=serialized_values,
            )
        )
        return

    snapshot.values = serialized_values
    snapshot.uncertainty_score = uncertainty_score
    db.add(snapshot)


def _build_training_profile(feature_rows: list[dict[str, float | str]]) -> dict[str, Any]:
    profile: dict[str, Any] = {}
    if not feature_rows:
        return profile

    keys = sorted({key for row in feature_rows for key in row.keys()})
    for key in keys:
        values = [row[key] for row in feature_rows if key in row]
        if not values:
            continue
        if all(isinstance(value, (int, float)) for value in values):
            numeric_values = np.asarray([float(value) for value in values], dtype=float)
            if len(np.unique(numeric_values)) == 1:
                edges = [float(numeric_values[0]), float(numeric_values[0]) + 1.0]
            else:
                edges = np.quantile(numeric_values, [0.0, 0.2, 0.4, 0.6, 0.8, 1.0]).tolist()
                edges = [float(item) for item in np.unique(edges)]
                if len(edges) < 2:
                    edges = [float(numeric_values.min()), float(numeric_values.max()) + 1.0]
            counts, _ = np.histogram(numeric_values, bins=edges)
            proportions = (counts / max(1, len(numeric_values))).tolist()
            profile[key] = {"type": "numeric", "edges": edges, "proportions": proportions}
        else:
            counts = Counter(str(value) for value in values)
            total = max(1, sum(counts.values()))
            profile[key] = {
                "type": "categorical",
                "proportions": {name: round(count / total, 6) for name, count in counts.most_common(20)},
            }
    return profile


def _psi(expected: np.ndarray, observed: np.ndarray) -> float:
    epsilon = 1e-6
    expected_safe = np.clip(expected.astype(float), epsilon, None)
    observed_safe = np.clip(observed.astype(float), epsilon, None)
    return float(np.sum((observed_safe - expected_safe) * np.log(observed_safe / expected_safe)))


def _build_drift_report(
    current_rows: list[dict[str, float | str]],
    training_profile: dict[str, Any],
) -> tuple[str, float, list[dict[str, object]], str]:
    if not current_rows or not training_profile:
        return (
            "insufficient_data",
            0.0,
            [],
            "There is not enough current feature-store data to estimate concept drift yet.",
        )

    feature_reports: list[dict[str, object]] = []
    for feature_name, descriptor in training_profile.items():
        current_values = [row.get(feature_name) for row in current_rows if feature_name in row]
        if not current_values:
            continue

        if descriptor.get("type") == "numeric":
            numeric_values = np.asarray([float(value) for value in current_values if isinstance(value, (int, float))], dtype=float)
            edges = descriptor.get("edges", [])
            if len(edges) < 2 or numeric_values.size == 0:
                continue
            counts, _ = np.histogram(numeric_values, bins=edges)
            observed = counts / max(1, len(numeric_values))
            expected = np.asarray(descriptor.get("proportions", []), dtype=float)
        else:
            counts = Counter(str(value) for value in current_values)
            categories = list(descriptor.get("proportions", {}).keys())
            expected = np.asarray([float(descriptor["proportions"].get(category, 0.0)) for category in categories], dtype=float)
            observed = np.asarray([counts.get(category, 0) / max(1, len(current_values)) for category in categories], dtype=float)

        if expected.size == 0 or observed.size == 0 or expected.size != observed.size:
            continue

        psi_score = round(_psi(expected, observed), 4)
        feature_reports.append(
            {
                "feature_name": feature_name,
                "psi": psi_score,
                "status": "attention" if psi_score >= PSI_ALERT_THRESHOLD else "ok",
                "note": (
                    "Feature distribution has shifted materially from training data."
                    if psi_score >= PSI_ALERT_THRESHOLD
                    else "Feature distribution remains close to training data."
                ),
            }
        )

    feature_reports.sort(key=lambda item: float(item["psi"]), reverse=True)
    feature_reports = feature_reports[:DRIFT_FEATURE_LIMIT]
    if not feature_reports:
        return (
            "insufficient_data",
            0.0,
            [],
            "There is not enough comparable feature coverage to estimate concept drift yet.",
        )

    overall_psi = round(float(sum(float(item["psi"]) for item in feature_reports) / len(feature_reports)), 4)
    status = "attention" if any(item["status"] == "attention" for item in feature_reports) else "ok"
    note = (
        "One or more monitored features have drifted materially away from the training data distribution."
        if status == "attention"
        else "Current feature distributions remain broadly aligned with the training profile."
    )
    return status, overall_psi, feature_reports, note


def build_feature_store_summary(db: Session) -> schemas.FeatureStoreSummary:
    total_snapshots = db.scalar(select(func.count(FeatureSnapshot.id))) or 0
    training_snapshots = db.scalar(select(func.count(FeatureSnapshot.id)).where(FeatureSnapshot.source_kind == "training")) or 0
    scoring_snapshots = db.scalar(select(func.count(FeatureSnapshot.id)).where(FeatureSnapshot.source_kind == "scoring")) or 0
    latest_snapshot = db.scalar(select(FeatureSnapshot).order_by(FeatureSnapshot.created_at.desc()).limit(1))
    return schemas.FeatureStoreSummary(
        total_snapshots=total_snapshots,
        training_snapshots=training_snapshots,
        scoring_snapshots=scoring_snapshots,
        latest_snapshot_at=latest_snapshot.created_at if latest_snapshot is not None else None,
        latest_model_version_id=latest_snapshot.model_version_id if latest_snapshot is not None else None,
    )


def refresh_model_drift_report(db: Session, version: ModelVersion | None = None) -> schemas.ModelDriftReportRead:
    current = version or db.scalar(
        select(ModelVersion)
        .where(ModelVersion.status == "deployed")
        .order_by(ModelVersion.trained_at.desc())
        .limit(1)
    )
    if current is None or not current.training_profile:
        return schemas.ModelDriftReportRead(
            status="insufficient_data",
            overall_psi=0.0,
            note="A deployed model and training profile are required before drift can be estimated.",
            monitored_at=None,
            feature_reports=[],
        )

    latest_scoring_date = db.scalar(
        select(func.max(FeatureSnapshot.snapshot_date)).where(
            FeatureSnapshot.model_version_id == current.id,
            FeatureSnapshot.source_kind == "scoring",
        )
    )
    if latest_scoring_date is not None:
        snapshots = list(
            db.scalars(
                select(FeatureSnapshot).where(
                    FeatureSnapshot.model_version_id == current.id,
                    FeatureSnapshot.source_kind == "scoring",
                    FeatureSnapshot.snapshot_date == latest_scoring_date,
                )
            ).all()
        )
        current_rows = [
            {
                key: value
                for key, value in snapshot.values.items()
                if isinstance(value, (int, float, str))
            }
            for snapshot in snapshots
        ]
    else:
        beneficiaries = _load_training_beneficiaries(db)
        current_rows = [
            build_feature_context(beneficiary).features
            for beneficiary in beneficiaries
            if beneficiary.status in {"active", "at_risk", "enrolled"}
        ]
    status, overall_psi, feature_reports, note = _build_drift_report(current_rows, current.training_profile)

    report = ModelDriftReport(
        model_version_id=current.id,
        status=status,
        overall_psi=overall_psi,
        feature_reports=feature_reports,
        note=note,
    )
    db.add(report)
    db.commit()
    db.refresh(report)
    return schemas.ModelDriftReportRead(
        id=report.id,
        status=report.status,  # type: ignore[arg-type]
        overall_psi=report.overall_psi,
        note=report.note or "",
        monitored_at=report.monitored_at.isoformat() + "Z",
        feature_reports=[schemas.DriftFeatureReport(**item) for item in report.feature_reports],
    )


def _positive_class_weight(y_train: list[int]) -> float:
    positives = max(1, sum(y_train))
    negatives = max(1, len(y_train) - positives)
    return round(negatives / positives, 4)


def _fit_logistic(
    x_train_sparse: Any,
    y_train: list[int],
    sample_weight: np.ndarray | None = None,
) -> LogisticRegression:
    logistic = LogisticRegression(
        class_weight="balanced",
        solver="saga",
        penalty="elasticnet",
        l1_ratio=0.25,
        max_iter=2500,
        random_state=42,
    )
    logistic.fit(x_train_sparse, y_train, sample_weight=sample_weight)
    return logistic


def _fit_xgboost(
    x_train_dense: np.ndarray,
    y_train: list[int],
    sample_weight: np.ndarray | None = None,
) -> Any | None:
    if XGBClassifier is None:
        return None
    model = XGBClassifier(
        n_estimators=220,
        max_depth=4,
        learning_rate=0.05,
        subsample=0.85,
        colsample_bytree=0.85,
        reg_lambda=1.2,
        min_child_weight=2.0,
        objective="binary:logistic",
        eval_metric="logloss",
        random_state=42,
        n_jobs=1,
        scale_pos_weight=_positive_class_weight(y_train),
    )
    model.fit(x_train_dense, y_train, sample_weight=sample_weight)
    return model


def _fit_lightgbm(
    x_train_dense: np.ndarray,
    y_train: list[int],
    sample_weight: np.ndarray | None = None,
) -> Any | None:
    if LGBMClassifier is None:
        return None
    model = LGBMClassifier(
        n_estimators=260,
        learning_rate=0.05,
        num_leaves=31,
        subsample=0.85,
        colsample_bytree=0.85,
        min_child_samples=12,
        reg_lambda=1.2,
        class_weight="balanced",
        random_state=42,
        n_jobs=1,
        verbosity=-1,
    )
    model.fit(x_train_dense, y_train, sample_weight=sample_weight)
    return model


def _fit_pipeline(
    x_train_sparse: Any,
    x_train_dense: np.ndarray,
    y_train: list[int],
    training_rows: int,
    sample_weight: np.ndarray | None = None,
) -> tuple[str, dict[str, Any], np.ndarray]:
    logistic = _fit_logistic(x_train_sparse, y_train, sample_weight=sample_weight)
    component_importances: list[np.ndarray] = [_normalize_importances(logistic.coef_[0])]

    if training_rows < 500:
        return "LogisticRegression", {"logistic": logistic}, np.abs(logistic.coef_[0])

    xgboost_model = _fit_xgboost(x_train_dense, y_train, sample_weight=sample_weight)
    lightgbm_model = _fit_lightgbm(x_train_dense, y_train, sample_weight=sample_weight)

    if xgboost_model is not None:
        component_importances.append(_normalize_importances(np.asarray(xgboost_model.feature_importances_)))
    if lightgbm_model is not None:
        component_importances.append(_normalize_importances(np.asarray(lightgbm_model.feature_importances_)))

    if training_rows < 2000:
        if xgboost_model is not None:
            return "XGBoost", {"xgboost": xgboost_model, "logistic": logistic}, np.asarray(xgboost_model.feature_importances_)
        if lightgbm_model is not None:
            return "LightGBM", {"lightgbm": lightgbm_model, "logistic": logistic}, np.asarray(lightgbm_model.feature_importances_)

        random_forest = RandomForestClassifier(
            n_estimators=250,
            min_samples_leaf=2,
            class_weight="balanced_subsample",
            random_state=42,
            n_jobs=1,
        )
        random_forest.fit(x_train_dense, y_train, sample_weight=sample_weight)
        return "RandomForest", {"random_forest": random_forest, "logistic": logistic}, random_forest.feature_importances_

    ensemble_components: dict[str, Any] = {"logistic": logistic}
    if xgboost_model is not None:
        ensemble_components["xgboost"] = xgboost_model
    if lightgbm_model is not None:
        ensemble_components["lightgbm"] = lightgbm_model

    if len(ensemble_components) == 1:
        return "LogisticRegression", {"logistic": logistic}, np.abs(logistic.coef_[0])

    return (
        "StackedEnsemble",
        ensemble_components,
        np.mean(component_importances, axis=0),
    )


def _component_probability(component_name: str, model: Any, sparse_matrix: Any, dense_matrix: np.ndarray) -> np.ndarray:
    if component_name == "logistic":
        positive_index = list(model.classes_).index(1)
        return model.predict_proba(sparse_matrix)[:, positive_index]
    if component_name in {"xgboost", "lightgbm", "random_forest"}:
        positive_index = list(model.classes_).index(1)
        with warnings.catch_warnings():
            warnings.filterwarnings(
                "ignore",
                message="X does not have valid feature names, but .* was fitted with feature names",
            )
            return model.predict_proba(dense_matrix)[:, positive_index]
    raise ValueError(f"Unsupported model component for probability scoring: {component_name}")


def _predict_from_bundle(
    bundle: dict[str, Any],
    sparse_matrix: Any,
    dense_matrix: np.ndarray,
) -> np.ndarray:
    algorithm = str(bundle["algorithm"])
    components = bundle["components"]
    if algorithm == "LogisticRegression":
        return _component_probability("logistic", components["logistic"], sparse_matrix, dense_matrix)
    if algorithm == "RandomForest":
        return _component_probability("random_forest", components["random_forest"], sparse_matrix, dense_matrix)
    if algorithm == "XGBoost":
        return _component_probability("xgboost", components["xgboost"], sparse_matrix, dense_matrix)
    if algorithm == "LightGBM":
        return _component_probability("lightgbm", components["lightgbm"], sparse_matrix, dense_matrix)

    probability_sets = [
        _component_probability(name, model, sparse_matrix, dense_matrix)
        for name, model in components.items()
        if name in {"logistic", "xgboost", "lightgbm", "random_forest"}
    ]
    if not probability_sets:
        raise ValueError("Model bundle has no scoreable components.")
    return np.mean(np.vstack(probability_sets), axis=0)


def _predict_probabilities(
    vectorizer: DictVectorizer,
    algorithm: str,
    components: dict[str, Any],
    feature_rows: list[dict[str, float | str]],
) -> np.ndarray:
    sparse_matrix = vectorizer.transform(feature_rows)
    dense_matrix = sparse_matrix.toarray()
    return _predict_from_bundle({"algorithm": algorithm, "components": components}, sparse_matrix, dense_matrix)


def _slice_sparse_matrix(matrix: Any, indices: list[int]) -> Any:
    if isinstance(matrix, csr_matrix):
        return matrix[indices]
    return matrix[indices]


def _fit_program_models(
    x_train_sparse: Any,
    x_train_dense: np.ndarray,
    train_samples: list[TrainingSample],
    feature_names: list[str],
    sample_weights: np.ndarray | None = None,
) -> tuple[dict[str, dict[str, Any]], list[str]]:
    grouped_indices: dict[str, list[int]] = defaultdict(list)
    grouped_labels: dict[str, list[int]] = defaultdict(list)
    for index, sample in enumerate(train_samples):
        grouped_indices[sample.program_id].append(index)
        grouped_labels[sample.program_id].append(sample.label)

    program_models: dict[str, dict[str, Any]] = {}
    thin_history_programs: list[str] = []
    for program_id, indices in grouped_indices.items():
        labels = grouped_labels[program_id]
        positives = sum(labels)
        negatives = len(labels) - positives
        if (
            len(labels) < PROGRAM_SPECIFIC_MIN_ROWS
            or positives < PROGRAM_SPECIFIC_MIN_POSITIVES
            or negatives < PROGRAM_SPECIFIC_MIN_NEGATIVES
        ):
            thin_history_programs.append(program_id)
            continue

        algorithm, components, importances = _fit_pipeline(
            _slice_sparse_matrix(x_train_sparse, indices),
            x_train_dense[indices],
            labels,
            len(labels),
            sample_weights[indices] if sample_weights is not None else None,
        )
        program_models[program_id] = {
            "algorithm": algorithm,
            "components": components,
            "training_rows": len(labels),
            "positive_rows": positives,
            "top_drivers": _model_driver_payload(feature_names, np.asarray(importances), limit=5),
        }

    return program_models, thin_history_programs


def _fit_program_type_models(
    x_train_sparse: Any,
    x_train_dense: np.ndarray,
    train_samples: list[TrainingSample],
    feature_names: list[str],
    sample_weights: np.ndarray | None = None,
) -> dict[str, dict[str, Any]]:
    grouped_indices: dict[str, list[int]] = defaultdict(list)
    grouped_labels: dict[str, list[int]] = defaultdict(list)
    for index, sample in enumerate(train_samples):
        grouped_indices[sample.program_type].append(index)
        grouped_labels[sample.program_type].append(sample.label)

    program_type_models: dict[str, dict[str, Any]] = {}
    for program_type, indices in grouped_indices.items():
        labels = grouped_labels[program_type]
        positives = sum(labels)
        negatives = len(labels) - positives
        if len(labels) < 80 or positives < 6 or negatives < 6:
            continue
        algorithm, components, importances = _fit_pipeline(
            _slice_sparse_matrix(x_train_sparse, indices),
            x_train_dense[indices],
            labels,
            len(labels),
            sample_weights[indices] if sample_weights is not None else None,
        )
        program_type_models[program_type] = {
            "algorithm": algorithm,
            "components": components,
            "training_rows": len(labels),
            "positive_rows": positives,
            "top_drivers": _model_driver_payload(feature_names, np.asarray(importances), limit=5),
        }

    return program_type_models


def _compute_sample_weights(train_samples: list[TrainingSample], beneficiaries_by_id: dict[str, Beneficiary]) -> np.ndarray:
    group_counts: Counter[tuple[str, str]] = Counter()
    for sample in train_samples:
        setting = beneficiaries_by_id[sample.beneficiary_id].program.operational_setting
        if setting is None or not setting.fairness_reweighting_enabled:
            continue
        for dimension in setting.fairness_target_dimensions or []:
            group_counts[(dimension, sample.audit_groups.get(dimension, "Unknown"))] += 1

    weights: list[float] = []
    for sample in train_samples:
        setting = beneficiaries_by_id[sample.beneficiary_id].program.operational_setting
        base_weight = max(0.01, float(sample.sample_weight))
        if setting is None or not setting.fairness_reweighting_enabled:
            weights.append(base_weight)
            continue
        baseline = float(max(1, setting.fairness_min_group_size))
        weight = base_weight
        for dimension in setting.fairness_target_dimensions or []:
            count = group_counts.get((dimension, sample.audit_groups.get(dimension, "Unknown")), 1)
            if count < baseline:
                weight *= baseline / float(max(1, count))
        weights.append(min(weight, 6.0))
    return np.asarray(weights, dtype=float)


def _select_prediction_bundle(loaded_model: LoadedModel, beneficiary: Beneficiary) -> tuple[dict[str, Any], dict[str, Any], float, float]:
    base_bundle = loaded_model.components["base_model"]
    program_models = loaded_model.components.get("program_models", {})
    program_type_models = loaded_model.components.get("program_type_models", {})
    program_bundle = program_models.get(beneficiary.program_id)
    if program_bundle is not None:
        return program_bundle, base_bundle, 0.7, 0.3
    type_bundle = program_type_models.get(beneficiary.program.program_type)
    if type_bundle is not None:
        return type_bundle, base_bundle, 0.7, 0.3
    return loaded_model.components["global_model"], base_bundle, 0.75, 0.25


def train_and_deploy_model(db: Session, force: bool = False) -> ModelVersion:
    """Train a new model version and mark it as the deployed artifact.

    The training path performs more than fitting an estimator. It also prepares
    training samples, selects or blends model families, computes fairness and
    drift-adjacent metadata, persists artifacts, and updates version status in
    a way the rest of the platform can consume.
    """
    beneficiaries = _load_training_beneficiaries(db)
    beneficiaries_by_id = {beneficiary.id: beneficiary for beneficiary in beneficiaries}
    federated_prior = latest_federated_prior(db)
    training_samples: list[TrainingSample] = []
    label_source_counts: Counter[str] = Counter()
    excluded_label_counts: Counter[str] = Counter()

    for beneficiary in beneficiaries:
        if not eligible_for_predictive_modeling(beneficiary):
            continue
        profile = build_operational_settings_profile(
            beneficiary.program.program_type,
            beneficiary.program.operational_setting,
        )
        snapshots = candidate_training_snapshots(beneficiary, profile=profile)
        for snapshot in snapshots:
            label_result = snapshot.label
            if label_result.excluded or label_result.label is None:
                excluded_label_counts[label_result.source] += 1
                continue
            snapshot_events = [
                event
                for event in beneficiary.monitoring_events
                if event.event_date <= snapshot.snapshot_date
            ]
            snapshot_interventions = [
                intervention
                for intervention in beneficiary.interventions
                if intervention.logged_at.date() <= snapshot.snapshot_date
            ]
            context = build_feature_context(
                beneficiary,
                as_of_date=snapshot.snapshot_date,
                events=snapshot_events,
                interventions=snapshot_interventions,
            )
            training_samples.append(
                TrainingSample(
                    beneficiary_id=beneficiary.id,
                    program_id=beneficiary.program_id,
                    program_type=beneficiary.program.program_type,
                    features=context.features,
                    label=label_result.label,
                    audit_groups=_audit_groups_for(beneficiary),
                    label_source=label_result.source,
                    sample_weight=label_result.sample_weight,
                    label_probability=label_result.label_probability,
                    snapshot_date=snapshot.snapshot_date,
                )
            )
            label_source_counts[label_result.source] += 1

    labels = [sample.label for sample in training_samples]

    positive_rows = sum(labels)
    negative_rows = len(labels) - positive_rows

    if len(labels) < 20 or positive_rows < 5 or negative_rows < 5:
        raise ValueError("Not enough labeled beneficiaries to train a model yet.")

    existing = db.scalar(select(ModelVersion).where(ModelVersion.status == "deployed").limit(1))
    if (
        existing is not None
        and not force
        and existing.artifact_path is not None
        and Path(existing.artifact_path).exists()
    ):
        return existing

    if len(labels) >= 24 and min(positive_rows, negative_rows) >= 2:
        train_samples, test_samples = train_test_split(
            training_samples,
            test_size=0.25,
            random_state=42,
            stratify=labels,
        )
        validation_note = "Metrics are reported on a held-out validation split."
    else:
        train_samples = training_samples
        test_samples = training_samples
        validation_note = "Metrics are reported on the training set because there were not enough records for a validation split."

    train_rows = [sample.features for sample in train_samples]
    y_train = [sample.label for sample in train_samples]
    test_rows = [sample.features for sample in test_samples]
    y_test = [sample.label for sample in test_samples]

    vectorizer = DictVectorizer(sparse=True)
    x_train_sparse = vectorizer.fit_transform(train_rows)
    x_train_dense = x_train_sparse.toarray()
    feature_names = list(vectorizer.get_feature_names_out())
    fairness_weights = _compute_sample_weights(train_samples, beneficiaries_by_id)
    base_logistic = _fit_logistic(x_train_sparse, y_train, sample_weight=fairness_weights)
    algorithm, global_components, importances = _fit_pipeline(
        x_train_sparse,
        x_train_dense,
        y_train,
        len(labels),
        fairness_weights,
    )
    base_bundle = {
        "algorithm": "LogisticRegression",
        "components": {"logistic": base_logistic},
        "training_rows": len(y_train),
        "positive_rows": sum(y_train),
    }
    global_bundle = {
        "algorithm": algorithm,
        "components": global_components,
        "training_rows": len(y_train),
        "positive_rows": sum(y_train),
    }
    program_models, thin_history_programs = _fit_program_models(
        x_train_sparse,
        x_train_dense,
        train_samples,
        feature_names,
        fairness_weights,
    )
    program_type_models = _fit_program_type_models(
        x_train_sparse,
        x_train_dense,
        train_samples,
        feature_names,
        fairness_weights,
    )

    x_test_sparse = vectorizer.transform(test_rows)
    x_test_dense = x_test_sparse.toarray()
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
    probabilities_array = np.asarray(probabilities, dtype=float)
    y_test_array = np.array(y_test)
    metrics = _metric_summary(y_test_array, probabilities_array, y_test_array)
    metrics.update(
        {
            "base_model_algorithm": "ElasticNetLogisticRegression",
            "program_models_trained": len(program_models),
            "program_type_models_trained": len(program_type_models),
            "programs_using_global_base_only": len(thin_history_programs),
            "explainability_mode": "shap" if shap is not None else "native_local_contributions",
            "sentiment_backend": "huggingface_or_lexicon",
            "fairness_reweighting_active": bool(np.max(fairness_weights) > 1.0),
            "hard_label_rows": int(sum(1 for sample in training_samples if sample.label_source.startswith("hard_"))),
            "soft_label_rows": int(sum(1 for sample in training_samples if sample.label_source.startswith("soft_"))),
            "excluded_label_rows": int(sum(excluded_label_counts.values())),
        }
    )
    for label_source, count in sorted(label_source_counts.items()):
        metrics[f"label_source_{label_source}"] = int(count)
    for label_source, count in sorted(excluded_label_counts.items()):
        metrics[f"excluded_label_source_{label_source}"] = int(count)
    if federated_prior:
        metrics["federated_participant_updates"] = int(federated_prior.get("participant_updates", 0))
    validation_note = (
        f"{validation_note} "
        f"{len(program_models)} program-specific model(s) were trained; "
        f"{len(program_type_models)} program-type base model(s) were trained; "
        f"{len(thin_history_programs)} program(s) are currently using the shared base model path. "
        f"Training labels were built from operational inactivity windows with "
        f"{sum(1 for sample in training_samples if sample.label_source.startswith('soft_'))} soft-labeled snapshot(s) "
        f"and {sum(excluded_label_counts.values())} excluded noisy snapshot(s)."
    )
    if federated_prior:
        validation_note += " Federated aggregated priors were available and surfaced in the model registry metadata."
    top_drivers = _model_driver_payload(feature_names, np.asarray(importances))
    bias_audit_records = _build_bias_audit_records(test_samples, probabilities_array)
    training_profile = _build_training_profile(train_rows)

    for version in db.scalars(select(ModelVersion).where(ModelVersion.status == "deployed")).all():
        version.status = "archived"

    model_version = ModelVersion(
        name="dropout-risk-model",
        algorithm=algorithm,
        status="training",
        training_rows=len(labels),
        positive_rows=positive_rows,
        features=feature_names,
        metrics=metrics,
        top_drivers=top_drivers,
        training_profile=training_profile,
        notes=validation_note,
    )
    db.add(model_version)
    db.flush()

    artifact_dir = Path(settings.model_artifact_dir)
    artifact_dir.mkdir(parents=True, exist_ok=True)
    artifact_path = artifact_dir / f"{model_version.id}.joblib"
    joblib.dump(
        {
            "vectorizer": vectorizer,
            "algorithm": algorithm,
            "components": {
                "base_model": base_bundle,
                "global_model": global_bundle,
                "program_models": program_models,
                "program_type_models": program_type_models,
            },
            "feature_names": feature_names,
            "training_profile": training_profile,
            "federated_prior": federated_prior,
        },
        artifact_path,
    )

    mlflow_run_id = log_training_run(
        algorithm=algorithm,
        metrics=metrics,
        params={
            "training_rows": len(labels),
            "positive_rows": positive_rows,
            "program_models_trained": len(program_models),
            "thin_history_programs": len(thin_history_programs),
            "federated_prior_available": bool(federated_prior),
        },
        artifact_path=str(artifact_path),
    )
    model_version.artifact_path = str(artifact_path)
    model_version.mlflow_run_id = mlflow_run_id
    model_version.status = "deployed"
    for row in bias_audit_records:
        db.add(
            ModelBiasAudit(
                model_version_id=model_version.id,
                dimension=str(row["dimension"]),
                group_name=str(row["group_name"]),
                sample_size=int(row["sample_size"]),
                positive_count=int(row["positive_count"]),
                predicted_positive_count=int(row["predicted_positive_count"]),
                flagged_rate=row["flagged_rate"] if isinstance(row["flagged_rate"], float) else None,
                false_positive_rate=row["false_positive_rate"] if isinstance(row["false_positive_rate"], float) else None,
                recall_rate=row["recall_rate"] if isinstance(row["recall_rate"], float) else None,
                severity=str(row["severity"]),
                guidance=str(row["guidance"]) if row["guidance"] is not None else None,
            )
        )
    _persist_feature_snapshots(db, train_samples, model_version, source_kind="training")
    _persist_feature_snapshots(db, test_samples, model_version, source_kind="validation")
    db.commit()
    db.refresh(model_version)
    refresh_model_drift_report(db, model_version)
    return model_version


def load_deployed_model(db: Session) -> LoadedModel | None:
    """Load the currently deployed model artifact bundle from persistence.

    The loader is defensive by design. It tolerates missing artifacts and older
    incompatible bundles so the application can fall back gracefully instead of
    crashing on startup.
    """
    version = db.scalar(
        select(ModelVersion)
        .where(ModelVersion.status == "deployed")
        .order_by(ModelVersion.trained_at.desc())
        .limit(1)
    )
    if version is None or not version.artifact_path:
        return None

    artifact_path = Path(version.artifact_path)
    if not artifact_path.exists():
        return None

    try:
        payload = joblib.load(artifact_path)
    except Exception:
        return None

    components = payload.get("components")
    if components is None:
        return None
    if "global_model" not in components:
        components = {
            "base_model": {
                "algorithm": payload["algorithm"],
                "components": payload["components"],
                "training_rows": version.training_rows,
                "positive_rows": version.positive_rows,
            },
            "global_model": {
                "algorithm": payload["algorithm"],
                "components": payload["components"],
                "training_rows": version.training_rows,
                "positive_rows": version.positive_rows,
            },
            "program_models": {},
            "program_type_models": {},
        }
    return LoadedModel(
        version=version,
        vectorizer=payload["vectorizer"],
        algorithm=payload["algorithm"],
        components=components,
        feature_names=list(payload["feature_names"]),
        training_profile=payload.get("training_profile", {}) or {},
    )


def ensure_model_ready(db: Session) -> schemas.ModelStatus:
    """Return model status, training a deployable model if needed.

    This helper is used during startup or health-like workflows where the app
    wants a best-effort model state without forcing callers to know whether a
    deployable artifact already exists.
    """
    loaded = load_deployed_model(db)
    if loaded is not None:
        return build_model_status(db, loaded.version)

    try:
        version = train_and_deploy_model(db, force=True)
        return build_model_status(db, version)
    except ValueError:
        return build_model_status(db, None)


def build_model_status(db: Session, version: ModelVersion | None = None) -> schemas.ModelStatus:
    """Build the canonical model-status payload consumed by the UI and API.

    The status object is intentionally richer than a bare training-metrics
    record. It packages readiness, fairness, threshold behavior, base-model
    usage, and other deployment-relevant context into one response.
    """
    current = version
    if current is None:
        current = db.scalar(select(ModelVersion).order_by(ModelVersion.trained_at.desc()).limit(1))

    if current is None:
        return schemas.ModelStatus(
            model_mode="Heuristic fallback",
            algorithm="None",
            status="untrained",
            mlflow_run_id=None,
            trained_at=None,
            training_rows=0,
            positive_rows=0,
            feature_count=0,
            metrics={},
            top_drivers=[],
            notes="A trained model is not available yet, so the platform is using heuristic scoring.",
            fallback_active=True,
            bias_audit=schemas.BiasAuditSummary(
                status="insufficient_data",
                note="A fairness audit will appear once a trained model and enough labeled validation data are available.",
                dimensions=[],
            ),
            drift_report=schemas.ModelDriftReportRead(
                status="insufficient_data",
                overall_psi=0.0,
                note="A deployed model is required before concept drift can be estimated.",
                monitored_at=None,
                feature_reports=[],
            ),
        )

    bias_audits = list(
        db.scalars(
            select(ModelBiasAudit)
            .where(ModelBiasAudit.model_version_id == current.id)
            .order_by(ModelBiasAudit.dimension.asc(), ModelBiasAudit.group_name.asc())
        ).all()
    )
    drift_report = db.scalar(
        select(ModelDriftReport)
        .where(ModelDriftReport.model_version_id == current.id)
        .order_by(ModelDriftReport.monitored_at.desc())
        .limit(1)
    )

    return schemas.ModelStatus(
        id=current.id,
        model_mode="Program-trained model" if current.status == "deployed" else "Heuristic fallback",
        algorithm=current.algorithm,
        status=current.status,
        mlflow_run_id=current.mlflow_run_id,
        trained_at=current.trained_at.isoformat() + "Z",
        training_rows=current.training_rows,
        positive_rows=current.positive_rows,
        feature_count=len(current.features or []),
        metrics=current.metrics or {},
        top_drivers=[schemas.ModelDriver(**driver) for driver in current.top_drivers or []],
        notes=current.notes,
        fallback_active=current.status != "deployed",
        bias_audit=_build_bias_audit_summary(bias_audits),
        drift_report=(
            schemas.ModelDriftReportRead(
                id=drift_report.id,
                status=drift_report.status,  # type: ignore[arg-type]
                overall_psi=drift_report.overall_psi,
                note=drift_report.note or "",
                monitored_at=drift_report.monitored_at.isoformat() + "Z",
                feature_reports=[schemas.DriftFeatureReport(**item) for item in drift_report.feature_reports],
            )
            if drift_report is not None
            else None
        ),
    )


def _uncertainty_score(probability: float, context: FeatureContext, training_rows: int) -> float:
    margin_component = 1.0 - min(1.0, abs(probability - 0.5) * 2)
    coverage_component = 1.0 - context.feature_coverage_ratio
    sample_component = 0.4 if training_rows < 100 else 0.0
    return round(min(1.0, max(0.0, (margin_component * 0.6) + (coverage_component * 0.3) + sample_component)), 3)


def _risk_level_from_model_version(version: ModelVersion, risk_score: int) -> str:
    metrics = version.metrics or {}
    high_threshold = int(round(float(metrics.get("high_risk_threshold_score", 75))))
    medium_threshold = int(round(float(metrics.get("medium_risk_threshold_score", 50))))
    if risk_score >= high_threshold:
        return "High"
    if risk_score >= medium_threshold:
        return "Medium"
    return "Low"


def _component_contributions(
    component_name: str,
    model: Any,
    row_sparse: Any,
    row_dense: np.ndarray,
    feature_names: list[str],
) -> np.ndarray | None:
    if component_name == "logistic":
        return np.asarray(model.coef_[0]) * np.asarray(row_sparse.toarray()[0], dtype=float)
    if component_name == "xgboost" and xgb is not None:
        booster = model.get_booster()
        dmatrix = xgb.DMatrix(row_dense, feature_names=feature_names)
        contributions = booster.predict(dmatrix, pred_contribs=True)
        return np.asarray(contributions[0][:-1], dtype=float)
    if component_name == "lightgbm":
        contributions = model.predict(row_dense, pred_contrib=True)
        return np.asarray(contributions[0][:-1], dtype=float)
    if component_name == "random_forest":
        importances = np.asarray(model.feature_importances_, dtype=float)
        values = np.asarray(row_dense[0], dtype=float)
        return importances * values
    return None


def _bundle_contributions(
    bundle: dict[str, Any],
    row_sparse: Any,
    row_dense: np.ndarray,
    feature_names: list[str],
) -> np.ndarray | None:
    algorithm = str(bundle["algorithm"])
    components = bundle["components"]

    if algorithm == "LogisticRegression":
        return _component_contributions("logistic", components["logistic"], row_sparse, row_dense, feature_names)
    if algorithm == "RandomForest":
        return _component_contributions("random_forest", components["random_forest"], row_sparse, row_dense, feature_names)
    if algorithm == "XGBoost":
        return _component_contributions("xgboost", components["xgboost"], row_sparse, row_dense, feature_names)
    if algorithm == "LightGBM":
        return _component_contributions("lightgbm", components["lightgbm"], row_sparse, row_dense, feature_names)

    contribution_sets = [
        contribution
        for name, model in components.items()
        if (contribution := _component_contributions(name, model, row_sparse, row_dense, feature_names)) is not None
    ]
    if not contribution_sets:
        return None
    return np.mean(np.vstack(contribution_sets), axis=0)


def _bundle_shap_values(
    bundle: dict[str, Any],
    row_dense: np.ndarray,
    feature_names: list[str],
) -> np.ndarray | None:
    if shap is None:
        return None

    algorithm = str(bundle["algorithm"])
    components = bundle["components"]
    try:  # pragma: no cover - depends on SHAP runtime behavior
        if algorithm == "LogisticRegression":
            explainer = shap.LinearExplainer(components["logistic"], row_dense)
            values = explainer.shap_values(row_dense)
            return np.asarray(values[0], dtype=float)
        if algorithm == "XGBoost":
            explainer = shap.TreeExplainer(components["xgboost"])
            values = explainer.shap_values(row_dense)
            return np.asarray(values[0], dtype=float)
        if algorithm == "LightGBM":
            explainer = shap.TreeExplainer(components["lightgbm"])
            values = explainer.shap_values(row_dense)
            return np.asarray(values[0], dtype=float)
        if algorithm == "RandomForest":
            explainer = shap.TreeExplainer(components["random_forest"])
            values = explainer.shap_values(row_dense)
            if isinstance(values, list):
                return np.asarray(values[-1][0], dtype=float)
            return np.asarray(values[0], dtype=float)

        shap_sets: list[np.ndarray] = []
        for name in ("logistic", "xgboost", "lightgbm", "random_forest"):
            model = components.get(name)
            if model is None:
                continue
            single_bundle = {"algorithm": {"logistic": "LogisticRegression", "xgboost": "XGBoost", "lightgbm": "LightGBM", "random_forest": "RandomForest"}[name], "components": {name: model}}
            if name == "logistic":
                single_bundle["components"] = {"logistic": model}
            elif name == "xgboost":
                single_bundle["components"] = {"xgboost": model}
            elif name == "lightgbm":
                single_bundle["components"] = {"lightgbm": model}
            else:
                single_bundle["components"] = {"random_forest": model}
            values = _bundle_shap_values(single_bundle, row_dense, feature_names)
            if values is not None:
                shap_sets.append(values)
        if shap_sets:
            return np.mean(np.vstack(shap_sets), axis=0)
    except Exception:
        return None
    return None


def score_with_model(loaded_model: LoadedModel, beneficiary: Beneficiary) -> ModelPrediction:
    heuristic = assess_beneficiary_risk(
        beneficiary,
        list(beneficiary.monitoring_events),
        list(beneficiary.interventions),
    )
    context = build_feature_context(beneficiary)
    row = loaded_model.vectorizer.transform([context.features])
    dense_row = row.toarray()
    selected_bundle, base_bundle, selected_weight, base_weight = _select_prediction_bundle(loaded_model, beneficiary)
    selected_probability = float(_predict_from_bundle(selected_bundle, row, dense_row)[0])
    base_probability = float(_predict_from_bundle(base_bundle, row, dense_row)[0])
    probability = (selected_probability * selected_weight) + (base_probability * base_weight)
    risk_score = int(round(probability * 100))
    risk_level = _risk_level_from_model_version(loaded_model.version, risk_score)

    explanation_sentences: list[str] = []
    flags: list[str] = []
    selected_contributions = _bundle_contributions(selected_bundle, row, dense_row, loaded_model.feature_names)
    base_contributions = _bundle_contributions(base_bundle, row, dense_row, loaded_model.feature_names)
    selected_shap_values = _bundle_shap_values(selected_bundle, dense_row, loaded_model.feature_names)
    base_shap_values = _bundle_shap_values(base_bundle, dense_row, loaded_model.feature_names)
    if selected_shap_values is not None and base_shap_values is not None:
        explanation_weights = (selected_shap_values * selected_weight) + (base_shap_values * base_weight)
    else:
        explanation_weights = None
    if selected_contributions is not None and base_contributions is not None:
        contributions = (selected_contributions * selected_weight) + (base_contributions * base_weight)
    else:
        contributions = selected_contributions if selected_contributions is not None else base_contributions

    if explanation_weights is not None:
        candidate_features = [
            loaded_model.feature_names[index]
            for index in np.argsort(explanation_weights)[::-1]
            if float(explanation_weights[index]) > 0
        ]
    elif contributions is not None:
        candidate_features = [
            loaded_model.feature_names[index]
            for index in np.argsort(contributions)[::-1]
            if float(contributions[index]) > 0
        ]
    else:
        candidate_features = []
        for driver in loaded_model.version.top_drivers or []:
            for feature_name in loaded_model.feature_names:
                if _human_driver_name(feature_name) == driver["name"]:
                    candidate_features.append(feature_name)
                    break

    for feature_name in candidate_features:
        payload = _feature_explanation(feature_name, context)
        if payload is None:
            continue
        flags.append(payload[0])
        explanation_sentences.append(payload[1])
        if len(explanation_sentences) == 3:
            break

    if explanation_sentences:
        explanation = " ".join(explanation_sentences)
    else:
        explanation = heuristic.explanation
        flags = heuristic.flags

    uncertainty_score = _uncertainty_score(probability, context, loaded_model.version.training_rows)
    confidence = "High confidence" if uncertainty_score < 0.35 and loaded_model.version.training_rows >= 40 else "Limited data"

    return ModelPrediction(
        risk_score=risk_score,
        risk_level=risk_level,
        explanation=explanation,
        flags=flags,
        confidence=confidence,
        uncertainty_score=uncertainty_score,
    )


def score_beneficiary(beneficiary: Beneficiary, loaded_model: LoadedModel | None = None) -> tuple[ModelPrediction, Any]:
    """Score a beneficiary with the deployed model and heuristic fallback.

    The return contract deliberately includes both the final prediction and the
    heuristic assessment. That makes it possible to explain or recover from
    cases where predictive modeling is not allowed, not available, or not
    trustworthy enough on its own.
    """
    heuristic = assess_beneficiary_risk(
        beneficiary,
        list(beneficiary.monitoring_events),
        list(beneficiary.interventions),
    )

    if not eligible_for_predictive_modeling(beneficiary):
        return (
            ModelPrediction(
                risk_score=heuristic.risk_score,
                risk_level=heuristic.risk_level,
                explanation="Predictive modeling is disabled for this beneficiary until consent is granted or restored. RetainAI is using heuristic signals only.",
                flags=heuristic.flags,
                confidence="Consent required",
                uncertainty_score=0.5,
            ),
            heuristic,
        )

    if loaded_model is None:
        return (
            ModelPrediction(
                risk_score=heuristic.risk_score,
                risk_level=heuristic.risk_level,
                explanation=heuristic.explanation,
                flags=heuristic.flags,
                confidence=heuristic.confidence,
                uncertainty_score=0.5,
            ),
            heuristic,
        )

    model_prediction = score_with_model(loaded_model, beneficiary)
    return model_prediction, heuristic
