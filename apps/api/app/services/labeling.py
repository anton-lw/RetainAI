"""Operational label construction and tracing-protocol helpers.

This service centralizes two product-critical ideas:

1. what RetainAI is actually trying to predict operationally
2. how a flagged case should move through the tracing cascade

Historically the codebase exposed configurable horizons and workflow fields, but
live model training still leaned too heavily on beneficiary status flags and
connector dispatch escalated channels with fairly generic rules. This module
turns both concerns into first-class shared logic so training, evaluation,
queue-building, and embedded write-back flows all speak the same language.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any

from app.core.time import coerce_utc, utc_now
from app.models import Beneficiary, Intervention, MonitoringEvent, ProgramOperationalSetting


LABEL_PRESET_DEFAULTS: dict[str, tuple[int, int]] = {
    "health_28d": (28, 14),
    "education_10d": (10, 30),
    "cct_missed_cycle": (30, 42),
    "custom": (30, 30),
}

PROGRAM_TYPE_DEFAULT_PRESETS: dict[str, str] = {
    "health": "health_28d",
    "education": "education_10d",
    "cash transfer": "cct_missed_cycle",
}

POSITIVE_VERIFICATION_STATUSES = {"still_enrolled", "re_engaged", "completed_elsewhere"}
CONFIRMED_SILENT_TRANSFER_STATUSES = {"silent_transfer", "completed_elsewhere"}
CONTACT_EVENT_TYPES = {
    "attendance",
    "checkin",
    "clinic_visit",
    "payment_collection",
    "session",
    "visit",
    "follow_up",
    "followup",
    "home_visit",
    "phone_call",
    "call",
    "sms",
    "outreach",
}
TRANSFER_KEYWORDS = {
    "silent transfer",
    "transfer",
    "transferred",
    "completed elsewhere",
    "another facility",
    "another clinic",
    "another site",
    "another school",
    "moved school",
    "moved clinic",
    "relocated",
    "relocation",
    "referred out",
    "referred to",
}
TRACING_PROTOCOL_STEPS = ("sms", "call", "visit")
CONSENT_ELIGIBLE_STATUSES = {"granted", "waived"}
MAX_TRAINING_SNAPSHOTS_PER_BENEFICIARY = 3
MIN_HISTORY_DAYS = 30


@dataclass(frozen=True)
class OperationalSettingsProfile:
    label_definition_preset: str
    dropout_inactivity_days: int
    prediction_window_days: int
    label_noise_strategy: str
    soft_label_weight: float
    silent_transfer_detection_enabled: bool
    low_risk_channel: str
    medium_risk_channel: str
    high_risk_channel: str
    tracing_sms_delay_days: int
    tracing_call_delay_days: int
    tracing_visit_delay_days: int
    escalation_max_attempts: int


@dataclass(frozen=True)
class SilentTransferAssessment:
    status: str
    confidence: float
    evidence: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class OperationalLabel:
    snapshot_date: date
    horizon_end: date
    label: int | None
    label_probability: float | None
    sample_weight: float
    source: str
    hard_label: bool
    excluded: bool
    suspected_silent_transfer: bool
    silent_transfer_assessment: SilentTransferAssessment
    evidence: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class TrainingSnapshot:
    snapshot_date: date
    label: OperationalLabel


@dataclass(frozen=True)
class TracingProtocolProjection:
    current_step: str
    current_channel: str
    current_due_at: datetime
    next_step: str | None
    next_due_at: datetime | None


def default_operational_profile(program_type: str | None) -> tuple[str, int, int]:
    normalized = (program_type or "").strip().lower()
    preset = PROGRAM_TYPE_DEFAULT_PRESETS.get(normalized, "custom")
    inactivity_days, prediction_window_days = LABEL_PRESET_DEFAULTS[preset]
    return preset, inactivity_days, prediction_window_days


def build_operational_settings_profile(
    program_type: str | None,
    setting: ProgramOperationalSetting | None,
) -> OperationalSettingsProfile:
    default_preset, default_inactivity, default_prediction = default_operational_profile(program_type)
    return OperationalSettingsProfile(
        label_definition_preset=(setting.label_definition_preset if setting is not None else default_preset) or default_preset,
        dropout_inactivity_days=max(1, (setting.dropout_inactivity_days if setting is not None else default_inactivity) or default_inactivity),
        prediction_window_days=max(1, (setting.prediction_window_days if setting is not None else default_prediction) or default_prediction),
        label_noise_strategy=(setting.label_noise_strategy if setting is not None else "operational_soft_labels") or "operational_soft_labels",
        soft_label_weight=float((setting.soft_label_weight if setting is not None else 0.35) or 0.35),
        silent_transfer_detection_enabled=bool(
            True if setting is None else setting.silent_transfer_detection_enabled
        ),
        low_risk_channel=(setting.low_risk_channel if setting is not None else "sms") or "sms",
        medium_risk_channel=(setting.medium_risk_channel if setting is not None else "call") or "call",
        high_risk_channel=(setting.high_risk_channel if setting is not None else "visit") or "visit",
        tracing_sms_delay_days=max(0, (setting.tracing_sms_delay_days if setting is not None else 3) or 3),
        tracing_call_delay_days=max(1, (setting.tracing_call_delay_days if setting is not None else 7) or 7),
        tracing_visit_delay_days=max(1, (setting.tracing_visit_delay_days if setting is not None else 14) or 14),
        escalation_max_attempts=max(1, (setting.escalation_max_attempts if setting is not None else 2) or 2),
    )


def eligible_for_predictive_modeling(beneficiary: Beneficiary) -> bool:
    if beneficiary.opted_out:
        return False
    policy = beneficiary.program.data_policy
    if policy is not None and not policy.consent_required:
        return True
    return beneficiary.modeling_consent_status in CONSENT_ELIGIBLE_STATUSES


def latest_observation_date(beneficiary: Beneficiary) -> date:
    dates: list[date] = [beneficiary.enrollment_date]
    if beneficiary.completion_date is not None:
        dates.append(beneficiary.completion_date)
    if beneficiary.dropout_date is not None:
        dates.append(beneficiary.dropout_date)
    dates.extend(event.event_date for event in beneficiary.monitoring_events)
    dates.extend(intervention.logged_at.date() for intervention in beneficiary.interventions)
    return max(dates)


def _is_recorded_interaction(event: MonitoringEvent) -> bool:
    if event.successful:
        return True
    if event.response_received is True:
        return True
    return (event.event_type or "").strip().lower() in CONTACT_EVENT_TYPES


def _interaction_dates(beneficiary: Beneficiary) -> list[date]:
    dates: list[date] = [beneficiary.enrollment_date]
    if beneficiary.completion_date is not None:
        dates.append(beneficiary.completion_date)
    for event in beneficiary.monitoring_events:
        if _is_recorded_interaction(event):
            dates.append(event.event_date)
    for intervention in beneficiary.interventions:
        if intervention.status in {"reached", "verified", "closed"}:
            dates.append(intervention.logged_at.date())
        elif intervention.successful is True:
            dates.append(intervention.logged_at.date())
        elif intervention.verification_status in POSITIVE_VERIFICATION_STATUSES:
            dates.append(intervention.logged_at.date())
    return sorted(set(dates))


def detect_silent_transfer(
    beneficiary: Beneficiary,
    *,
    snapshot_date: date | None = None,
    observation_end: date | None = None,
) -> SilentTransferAssessment:
    cutoff = observation_end or latest_observation_date(beneficiary)
    window_start = snapshot_date or beneficiary.enrollment_date
    evidence: list[str] = []

    interventions = [
        intervention
        for intervention in beneficiary.interventions
        if window_start <= intervention.logged_at.date() <= cutoff
    ]
    for intervention in interventions:
        if intervention.verification_status in CONFIRMED_SILENT_TRANSFER_STATUSES:
            evidence.append(
                f"Intervention on {intervention.logged_at.date().isoformat()} was verified as {intervention.verification_status.replace('_', ' ')}."
            )
            return SilentTransferAssessment(status="confirmed", confidence=0.98, evidence=evidence)

    notes_blob = " ".join(
        filter(
            None,
            [
                beneficiary.current_note or "",
                *(
                    event.notes or ""
                    for event in beneficiary.monitoring_events
                    if window_start <= event.event_date <= cutoff
                ),
                *(
                    intervention.verification_note or intervention.note or ""
                    for intervention in interventions
                ),
            ],
        )
    ).lower()
    keyword_hits = sorted(keyword for keyword in TRANSFER_KEYWORDS if keyword in notes_blob)
    if keyword_hits:
        evidence.append(f"Transfer-related notes mention {', '.join(keyword_hits[:3])}.")

    sources = [
        (event.source or "").strip().lower()
        for event in beneficiary.monitoring_events
        if window_start <= event.event_date <= cutoff and (event.source or "").strip()
    ]
    distinct_sources = [source for source in dict.fromkeys(sources) if source]
    if len(distinct_sources) >= 2:
        evidence.append(f"Activity was recorded from multiple sources ({', '.join(distinct_sources[:3])}).")

    if keyword_hits and len(distinct_sources) >= 2:
        return SilentTransferAssessment(status="suspected", confidence=0.82, evidence=evidence)
    if keyword_hits:
        return SilentTransferAssessment(status="suspected", confidence=0.68, evidence=evidence)
    if len(distinct_sources) >= 3:
        evidence.append("Source changes suggest the beneficiary may have continued elsewhere.")
        return SilentTransferAssessment(status="suspected", confidence=0.55, evidence=evidence)
    return SilentTransferAssessment(status="none", confidence=0.0, evidence=[])


def _last_contact_before(interaction_dates: list[date], snapshot_date: date, enrollment_date: date) -> date:
    eligible = [item for item in interaction_dates if item <= snapshot_date]
    return max(eligible) if eligible else enrollment_date


def _next_contact_after(interaction_dates: list[date], snapshot_date: date) -> date | None:
    future = [item for item in interaction_dates if item > snapshot_date]
    return min(future) if future else None


def _consecutive_missed_events(events: list[MonitoringEvent]) -> int:
    ordered = sorted(events, key=lambda item: item.event_date, reverse=True)
    consecutive = 0
    for event in ordered:
        if _is_recorded_interaction(event):
            break
        consecutive += 1
    return consecutive


def _response_rate(events: list[MonitoringEvent]) -> float:
    outreach = [event for event in events if event.response_received is not None]
    if not outreach:
        return 1.0
    return sum(1 for event in outreach if event.response_received) / len(outreach)


def _sequence_label_probability(
    beneficiary: Beneficiary,
    *,
    snapshot_date: date,
    inactivity_days: int,
) -> tuple[float, list[str]]:
    observed_events = [event for event in beneficiary.monitoring_events if event.event_date <= snapshot_date]
    interaction_dates = _interaction_dates(beneficiary)
    last_contact = _last_contact_before(interaction_dates, snapshot_date, beneficiary.enrollment_date)
    days_since_last_contact = max(0, (snapshot_date - last_contact).days)
    recent_30 = [event for event in observed_events if (snapshot_date - event.event_date).days <= 30]
    recent_success_rate = 1.0
    if recent_30:
        recent_success_rate = sum(1 for event in recent_30 if _is_recorded_interaction(event)) / len(recent_30)
    months_since_enrollment = max(0.0, (snapshot_date - beneficiary.enrollment_date).days / 30.0)
    consecutive_missed = _consecutive_missed_events(observed_events)
    response_rate = _response_rate(observed_events)
    soft_signal_values = [
        value
        for value in (
            beneficiary.household_stability_signal,
            beneficiary.economic_stress_signal,
            beneficiary.family_support_signal,
            beneficiary.health_change_signal,
            beneficiary.motivation_signal,
        )
        if value is not None
    ]
    soft_signal_pressure = 0.0
    if soft_signal_values:
        soft_signal_pressure = sum(max(0.0, float(value) - 1.0) / 4.0 for value in soft_signal_values) / len(soft_signal_values)

    score = 0.0
    score += min(1.0, days_since_last_contact / float(max(1, inactivity_days))) * 0.4
    score += min(1.0, consecutive_missed / 3.0) * 0.18
    score += (1.0 - recent_success_rate) * 0.18
    score += (1.0 - response_rate) * 0.12
    if months_since_enrollment <= 12:
        score += 0.06
    score += soft_signal_pressure * 0.12
    score = max(0.0, min(1.0, score))

    evidence: list[str] = []
    if days_since_last_contact >= inactivity_days:
        evidence.append(f"Current inactivity gap is already {days_since_last_contact} days.")
    elif days_since_last_contact >= max(7, inactivity_days // 2):
        evidence.append(f"Inactivity gap is already {days_since_last_contact} days and trending upward.")
    if consecutive_missed >= 2:
        evidence.append(f"{consecutive_missed} recent monitoring events were missed or unsuccessful.")
    if recent_success_rate <= 0.5 and recent_30:
        evidence.append("Recent contact success has fallen below 50%.")
    if response_rate < 0.5:
        evidence.append("Recent outreach attempts rarely received a response.")
    if soft_signal_pressure >= 0.5:
        evidence.append("Field observations indicate compounding household or motivation pressures.")
    return score, evidence


def _terminal_status_prior(
    beneficiary: Beneficiary,
    *,
    snapshot_date: date,
    horizon_end: date,
) -> tuple[float | None, list[str], str | None]:
    evidence: list[str] = []
    horizon_days = max(1, (horizon_end - snapshot_date).days)

    if beneficiary.dropout_date is not None and beneficiary.dropout_date >= snapshot_date:
        days_to_dropout = (beneficiary.dropout_date - snapshot_date).days
        probability = 0.72
        if days_to_dropout <= horizon_days:
            probability = 0.9
        elif days_to_dropout <= max(horizon_days * 2, 21):
            probability = 0.82
        evidence.append(
            f"The beneficiary was later marked dropped on {beneficiary.dropout_date.isoformat()}, which is treated as a noisy disengagement signal."
        )
        return probability, evidence, "soft_positive_terminal_status_prior"

    if beneficiary.status == "dropped":
        evidence.append("The beneficiary is currently marked dropped, but no precise dropout date is available.")
        return 0.75, evidence, "soft_positive_terminal_status_prior"

    if beneficiary.completion_date is not None and beneficiary.completion_date <= horizon_end:
        evidence.append(
            f"The beneficiary completed on {beneficiary.completion_date.isoformat()}, which weakly suggests continued engagement through the window."
        )
        return 0.12, evidence, "soft_negative_completion_status_prior"

    if beneficiary.status == "completed":
        evidence.append("The beneficiary is currently marked completed, which is treated as a weak stable-engagement prior.")
        return 0.18, evidence, "soft_negative_completion_status_prior"

    return None, [], None


def _soft_label_from_priors(
    beneficiary: Beneficiary,
    *,
    snapshot_date: date,
    horizon_end: date,
    inactivity_days: int,
    profile: OperationalSettingsProfile,
    evidence: list[str],
    suffix_note: str,
) -> OperationalLabel | None:
    sequence_probability, sequence_evidence = _sequence_label_probability(
        beneficiary,
        snapshot_date=snapshot_date,
        inactivity_days=inactivity_days,
    )
    terminal_probability, terminal_evidence, terminal_source = _terminal_status_prior(
        beneficiary,
        snapshot_date=snapshot_date,
        horizon_end=horizon_end,
    )
    merged_evidence = list(evidence) + sequence_evidence + terminal_evidence

    combined_probability = sequence_probability
    source = "soft_sequence_prior"
    if terminal_probability is not None:
        combined_probability = round((sequence_probability * 0.2) + (terminal_probability * 0.8), 3)
        source = terminal_source or "soft_terminal_status_prior"

    if combined_probability >= 0.65:
        return OperationalLabel(
            snapshot_date=snapshot_date,
            horizon_end=horizon_end,
            label=1,
            label_probability=combined_probability,
            sample_weight=profile.soft_label_weight,
            source=source,
            hard_label=False,
            excluded=False,
            suspected_silent_transfer=False,
            silent_transfer_assessment=SilentTransferAssessment(status="none", confidence=0.0, evidence=[]),
            evidence=merged_evidence + [suffix_note],
        )
    if combined_probability <= 0.35:
        negative_source = source if source.startswith("soft_negative") else "soft_negative_sequence_stable_engagement"
        return OperationalLabel(
            snapshot_date=snapshot_date,
            horizon_end=horizon_end,
            label=0,
            label_probability=combined_probability,
            sample_weight=profile.soft_label_weight,
            source=negative_source,
            hard_label=False,
            excluded=False,
            suspected_silent_transfer=False,
            silent_transfer_assessment=SilentTransferAssessment(status="none", confidence=0.0, evidence=[]),
            evidence=merged_evidence + [suffix_note],
        )
    return None


def construct_operational_label(
    beneficiary: Beneficiary,
    *,
    snapshot_date: date,
    profile: OperationalSettingsProfile,
    observation_end: date | None = None,
    min_history_days: int = MIN_HISTORY_DAYS,
    prediction_window_days: int | None = None,
) -> OperationalLabel:
    observation_end = observation_end or latest_observation_date(beneficiary)
    resolved_prediction_window_days = prediction_window_days or profile.prediction_window_days
    horizon_end = snapshot_date + timedelta(days=resolved_prediction_window_days)
    if snapshot_date <= beneficiary.enrollment_date:
        return OperationalLabel(
            snapshot_date=snapshot_date,
            horizon_end=horizon_end,
            label=None,
            label_probability=None,
            sample_weight=0.0,
            source="excluded_before_enrollment",
            hard_label=False,
            excluded=True,
            suspected_silent_transfer=False,
            silent_transfer_assessment=SilentTransferAssessment(status="none", confidence=0.0, evidence=[]),
            evidence=["Snapshot falls before or on enrollment date."],
        )
    if (snapshot_date - beneficiary.enrollment_date).days < min_history_days:
        return OperationalLabel(
            snapshot_date=snapshot_date,
            horizon_end=horizon_end,
            label=None,
            label_probability=None,
            sample_weight=0.0,
            source="excluded_insufficient_history",
            hard_label=False,
            excluded=True,
            suspected_silent_transfer=False,
            silent_transfer_assessment=SilentTransferAssessment(status="none", confidence=0.0, evidence=[]),
            evidence=["Not enough pre-snapshot history to construct an operational label."],
        )

    silent_transfer = detect_silent_transfer(
        beneficiary,
        snapshot_date=snapshot_date,
        observation_end=observation_end,
    )
    if profile.silent_transfer_detection_enabled and silent_transfer.status in {"confirmed", "suspected"}:
        return OperationalLabel(
            snapshot_date=snapshot_date,
            horizon_end=horizon_end,
            label=None,
            label_probability=None,
            sample_weight=0.0,
            source=f"excluded_{silent_transfer.status}_silent_transfer",
            hard_label=False,
            excluded=True,
            suspected_silent_transfer=True,
            silent_transfer_assessment=silent_transfer,
            evidence=list(silent_transfer.evidence),
        )

    interaction_dates = _interaction_dates(beneficiary)
    last_contact = _last_contact_before(interaction_dates, snapshot_date, beneficiary.enrollment_date)
    next_contact = _next_contact_after(interaction_dates, snapshot_date)
    inactivity_threshold_date = last_contact + timedelta(days=profile.dropout_inactivity_days)
    evidence: list[str] = [
        f"Last recorded interaction before snapshot was on {last_contact.isoformat()}.",
        f"Operational inactivity threshold would be crossed on {inactivity_threshold_date.isoformat()}.",
    ]

    enough_future_observation = observation_end >= horizon_end
    if next_contact is not None and next_contact <= horizon_end:
        evidence.append(f"A recorded interaction occurred on {next_contact.isoformat()} within the prediction window.")
        return OperationalLabel(
            snapshot_date=snapshot_date,
            horizon_end=horizon_end,
            label=0,
            label_probability=0.0,
            sample_weight=1.0,
            source="hard_negative_future_contact",
            hard_label=True,
            excluded=False,
            suspected_silent_transfer=False,
            silent_transfer_assessment=silent_transfer,
            evidence=evidence,
        )

    if inactivity_threshold_date <= horizon_end and observation_end >= inactivity_threshold_date:
        evidence.append("No recorded interaction occurred before the configured inactivity threshold was crossed.")
        return OperationalLabel(
            snapshot_date=snapshot_date,
            horizon_end=horizon_end,
            label=1,
            label_probability=1.0,
            sample_weight=1.0,
            source="hard_positive_inactivity_threshold_crossed",
            hard_label=True,
            excluded=False,
            suspected_silent_transfer=False,
            silent_transfer_assessment=silent_transfer,
            evidence=evidence,
        )

    if enough_future_observation and next_contact is None and inactivity_threshold_date > horizon_end:
        if profile.label_noise_strategy == "operational_soft_labels":
            soft_label = _soft_label_from_priors(
                beneficiary,
                snapshot_date=snapshot_date,
                horizon_end=horizon_end,
                inactivity_days=profile.dropout_inactivity_days,
                profile=profile,
                evidence=evidence,
                suffix_note="No recorded interaction occurred in the window, but the configured inactivity threshold was not crossed yet.",
            )
            if soft_label is not None:
                return soft_label

        return OperationalLabel(
            snapshot_date=snapshot_date,
            horizon_end=horizon_end,
            label=None,
            label_probability=None,
            sample_weight=0.0,
            source="excluded_ambiguous_future_window",
            hard_label=False,
            excluded=True,
            suspected_silent_transfer=False,
            silent_transfer_assessment=silent_transfer,
            evidence=evidence + ["No recorded interaction occurred in the window, but the configured inactivity threshold was not crossed yet."],
        )

    if not enough_future_observation and profile.label_noise_strategy == "operational_soft_labels":
        soft_label = _soft_label_from_priors(
            beneficiary,
            snapshot_date=snapshot_date,
            horizon_end=horizon_end,
            inactivity_days=profile.dropout_inactivity_days,
            profile=profile,
            evidence=evidence,
            suffix_note="Future observation is incomplete, so the label is derived from sequence structure and terminal-status priors and is down-weighted.",
        )
        if soft_label is not None:
            if not soft_label.source.startswith("soft_negative") and not soft_label.source.startswith("soft_positive"):
                return OperationalLabel(
                    snapshot_date=soft_label.snapshot_date,
                    horizon_end=soft_label.horizon_end,
                    label=soft_label.label,
                    label_probability=soft_label.label_probability,
                    sample_weight=soft_label.sample_weight,
                    source="soft_label_incomplete_future_window",
                    hard_label=False,
                    excluded=False,
                    suspected_silent_transfer=False,
                    silent_transfer_assessment=silent_transfer,
                    evidence=soft_label.evidence,
                )
            return OperationalLabel(
                snapshot_date=soft_label.snapshot_date,
                horizon_end=soft_label.horizon_end,
                label=soft_label.label,
                label_probability=soft_label.label_probability,
                sample_weight=soft_label.sample_weight,
                source=soft_label.source,
                hard_label=False,
                excluded=False,
                suspected_silent_transfer=False,
                silent_transfer_assessment=silent_transfer,
                evidence=soft_label.evidence,
            )

    return OperationalLabel(
        snapshot_date=snapshot_date,
        horizon_end=horizon_end,
        label=None,
        label_probability=None,
        sample_weight=0.0,
        source="excluded_noisy_unresolved_window",
        hard_label=False,
        excluded=True,
        suspected_silent_transfer=False,
        silent_transfer_assessment=silent_transfer,
        evidence=evidence + ["The future window is too ambiguous to label reliably."],
    )


def candidate_training_snapshots(
    beneficiary: Beneficiary,
    *,
    profile: OperationalSettingsProfile,
    max_snapshots: int = MAX_TRAINING_SNAPSHOTS_PER_BENEFICIARY,
    min_history_days: int = MIN_HISTORY_DAYS,
) -> list[TrainingSnapshot]:
    observation_end = latest_observation_date(beneficiary)
    snapshots: list[TrainingSnapshot] = []

    prioritized_candidates: list[date] = []
    prioritized_candidates.append(observation_end - timedelta(days=1))
    prioritized_candidates.append(observation_end - timedelta(days=min(7, max(1, profile.prediction_window_days // 2))))
    prioritized_candidates.append(observation_end - timedelta(days=profile.prediction_window_days))
    for index in range(1, max_snapshots + 2):
        prioritized_candidates.append(observation_end - timedelta(days=profile.prediction_window_days * index))

    seen: set[date] = set()
    ordered_candidates: list[date] = []
    for snapshot_date in prioritized_candidates:
        if snapshot_date <= beneficiary.enrollment_date:
            continue
        if snapshot_date in seen:
            continue
        seen.add(snapshot_date)
        ordered_candidates.append(snapshot_date)
        if len(ordered_candidates) >= max_snapshots:
            break

    for snapshot_date in ordered_candidates:
        label = construct_operational_label(
            beneficiary,
            snapshot_date=snapshot_date,
            profile=profile,
            observation_end=observation_end,
            min_history_days=min_history_days,
            prediction_window_days=profile.prediction_window_days,
        )
        if label.excluded and label.source == "excluded_insufficient_history":
            break
        snapshots.append(TrainingSnapshot(snapshot_date=snapshot_date, label=label))
    return snapshots


def canonical_protocol_step(channel: str | None) -> str:
    normalized = (channel or "").strip().lower()
    if normalized in {"sms", "whatsapp"}:
        return "sms"
    if normalized in {"call", "manual"}:
        return "call"
    return "visit"


def _entry_channel_for_risk_level(profile: OperationalSettingsProfile, risk_level: str) -> str:
    if risk_level == "High":
        return profile.high_risk_channel
    if risk_level == "Medium":
        return profile.medium_risk_channel
    return profile.low_risk_channel


def _channel_for_step(step: str, configured_channel: str) -> str:
    normalized = configured_channel.lower()
    if step == "sms":
        return "whatsapp" if normalized == "whatsapp" else "sms"
    if step == "call":
        return "manual" if normalized == "manual" else "call"
    return "visit"


def _step_delay_days(profile: OperationalSettingsProfile, step: str) -> int:
    if step == "sms":
        return profile.tracing_sms_delay_days
    if step == "call":
        return profile.tracing_call_delay_days
    return profile.tracing_visit_delay_days


def _next_protocol_step(step: str) -> str | None:
    try:
        index = TRACING_PROTOCOL_STEPS.index(step)
    except ValueError:
        return None
    if index >= len(TRACING_PROTOCOL_STEPS) - 1:
        return None
    return TRACING_PROTOCOL_STEPS[index + 1]


def project_tracing_protocol(
    *,
    risk_level: str,
    profile: OperationalSettingsProfile,
    workflow: Any | None = None,
    reference_time: datetime | None = None,
) -> TracingProtocolProjection:
    now = reference_time or utc_now()
    entry_channel = _entry_channel_for_risk_level(profile, risk_level)
    entry_step = canonical_protocol_step(entry_channel)
    current_step = canonical_protocol_step(getattr(workflow, "protocol_step", None) or getattr(workflow, "support_channel", None) or entry_channel)
    current_channel = _channel_for_step(current_step, getattr(workflow, "support_channel", None) or entry_channel)
    current_due_at = getattr(workflow, "due_at", None)

    if current_due_at is None:
        current_due_at = now + timedelta(days=_step_delay_days(profile, current_step))
    current_due_at = coerce_utc(current_due_at)

    status = (getattr(workflow, "status", None) or "queued").lower()
    attempts = int(getattr(workflow, "attempt_count", 0) or 0)
    overdue = current_due_at <= now

    if status in {"attempted", "reached", "escalated"} and (attempts >= profile.escalation_max_attempts or overdue):
        advanced_step = _next_protocol_step(current_step)
        if advanced_step is not None:
            current_step = advanced_step
            current_channel = _channel_for_step(advanced_step, _entry_channel_for_risk_level(profile, risk_level))
            current_due_at = now + timedelta(days=_step_delay_days(profile, advanced_step))

    next_step = _next_protocol_step(current_step)
    next_due_at = None
    if next_step is not None:
        next_due_at = now + timedelta(days=_step_delay_days(profile, next_step))

    return TracingProtocolProjection(
        current_step=current_step,
        current_channel=current_channel,
        current_due_at=current_due_at,
        next_step=next_step,
        next_due_at=next_due_at,
    )


def tracing_recommended_action(program_type: str | None, projection: TracingProtocolProjection) -> str:
    step = projection.current_step
    if step == "sms":
        return "Send a supportive SMS or WhatsApp reminder and watch for a response before escalating."
    if step == "call":
        if (program_type or "").strip().lower() == "health":
            return "Call the beneficiary or caregiver to verify appointment barriers and current care status."
        return "Call the beneficiary or caregiver to verify the current barrier and confirm next steps."
    return "Schedule an in-person visit in the next field round and verify the beneficiary's current status before closing the case."
