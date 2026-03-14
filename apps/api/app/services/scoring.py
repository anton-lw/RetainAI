"""Scoring helpers used by live queue generation.

The broader modeling service manages training and artifacts; this module holds
the narrower logic for turning persisted beneficiaries into risk-oriented output
that can be consumed by analytics and queue-building workflows.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from app.models import Beneficiary, Intervention, MonitoringEvent


@dataclass
class RiskAssessment:
    risk_score: int
    risk_level: str
    explanation: str
    recommended_action: str
    flags: list[str]
    driver_names: list[str]
    last_contact_days: int
    attendance_rate_30d: int
    confidence: str
    intervention_status: str
    dropout_probability: float


def recommended_action_for(program_type: str, risk_level: str) -> str:
    key = program_type.lower()
    if risk_level == "Low":
        return "Continue standard monitoring unless a new missed contact is recorded."

    actions = {
        "cash transfer": {
            "High": "Schedule a follow-up call within 48 hours and verify transfer collection barriers.",
            "Medium": "Confirm payment logistics and check for mobility or household stress before the next cycle.",
        },
        "education": {
            "High": "Assign a school transition follow-up this week and verify fee, transport, or caregiver barriers.",
            "Medium": "Contact the caregiver before the next attendance milestone to prevent re-entry loss.",
        },
        "health": {
            "High": "Route the case to the relevant health worker immediately for phone or home follow-up.",
            "Medium": "Bundle the beneficiary into the next outreach round and confirm access barriers early.",
        },
    }

    fallback = {
        "High": "Trigger a manual check-in within 48 hours and document the barrier before the next milestone.",
        "Medium": "Queue a structured follow-up before the next scheduled service point.",
    }

    return actions.get(key, fallback).get(risk_level, fallback[risk_level])


def risk_level_from_score(risk_score: int) -> str:
    if risk_score >= 75:
        return "High"
    if risk_score >= 50:
        return "Medium"
    return "Low"


def _phase_weight(phase: str | None) -> tuple[int, str] | None:
    if not phase:
        return None

    normalized = phase.lower()
    if any(token in normalized for token in ("onboarding", "month 1", "month 2", "month 3", "transition", "visit 2")):
        return 10, "Early-program or transition phase"
    if any(token in normalized for token in ("term break", "exam", "postnatal", "post-visit")):
        return 8, "Known transition-point dropout risk"
    return None


def _keyword_factors(notes: str) -> list[tuple[int, str, str]]:
    keyword_map = {
        "displacement": (14, "Displacement or relocation noted", "Recent notes mention displacement or relocation risk."),
        "relocation": (14, "Displacement or relocation noted", "Recent notes mention displacement or relocation risk."),
        "migration": (12, "Seasonal mobility pressure", "Recent notes suggest seasonal mobility or migration pressure."),
        "harvest": (10, "Seasonal mobility pressure", "Recent notes suggest seasonal mobility or migration pressure."),
        "food": (10, "Food insecurity flagged", "Household notes include food stress or insecurity signals."),
        "fee": (10, "Cost barrier flagged", "Recent notes suggest fee or cost pressure."),
        "transport": (8, "Transport barrier flagged", "Recent notes mention transport or travel constraints."),
        "illness": (12, "Health shock flagged", "Recent notes mention illness or treatment disruption."),
        "flood": (10, "Shock event flagged", "Recent notes mention flooding or another external disruption."),
    }

    results: list[tuple[int, str, str]] = []
    for keyword, payload in keyword_map.items():
        if keyword in notes:
            results.append(payload)
    return results


def assess_beneficiary_risk(
    beneficiary: Beneficiary,
    events: list[MonitoringEvent],
    interventions: list[Intervention],
) -> RiskAssessment:
    today = date.today()
    ordered_events = sorted(events, key=lambda item: item.event_date, reverse=True)
    score = 8
    reasons: list[tuple[int, str, str]] = []

    last_successful_contact = next((event.event_date for event in ordered_events if event.successful), beneficiary.enrollment_date)
    last_contact_days = max(0, (today - last_successful_contact).days)
    if last_contact_days >= 45:
        reasons.append((26, "Long gap since last successful contact", f"No successful contact has been recorded in {last_contact_days} days."))
    elif last_contact_days >= 30:
        reasons.append((18, "Long gap since last successful contact", f"No successful contact has been recorded in {last_contact_days} days."))

    recent_events = [event for event in ordered_events if (today - event.event_date).days <= 30]
    relevant_recent_events = [
        event
        for event in recent_events
        if event.event_type in {"attendance", "checkin", "clinic_visit", "payment_collection", "session", "visit"}
    ] or recent_events

    if relevant_recent_events:
        successful_recent = sum(1 for event in relevant_recent_events if event.successful)
        attendance_rate_30d = round((successful_recent / len(relevant_recent_events)) * 100)
    else:
        attendance_rate_30d = 100

    if len(relevant_recent_events) >= 2 and attendance_rate_30d <= 49:
        reasons.append(
            (
                24,
                "Attendance has fallen sharply",
                f"Only {attendance_rate_30d}% of recent attendance or contact events were successful over the last 30 days.",
            )
        )
    elif len(relevant_recent_events) >= 2 and attendance_rate_30d <= 69:
        reasons.append(
            (
                14,
                "Attendance is declining",
                f"Recent engagement is weakening, with only {attendance_rate_30d}% of recent events completed successfully.",
            )
        )

    consecutive_missed = 0
    for event in ordered_events:
        if event.successful:
            break
        consecutive_missed += 1

    if consecutive_missed >= 3:
        reasons.append((22, "Multiple consecutive misses", f"The latest {consecutive_missed} monitoring events were missed or unsuccessful."))
    elif consecutive_missed == 2:
        reasons.append((14, "Multiple consecutive misses", "The last two monitoring events were missed or unsuccessful."))

    outreach_events = [event for event in ordered_events if event.response_received is not None]
    if outreach_events:
        response_rate = sum(1 for event in outreach_events if event.response_received) / len(outreach_events)
        if len(outreach_events) >= 3 and response_rate < 0.4:
            reasons.append((12, "Low response to outreach", "Recent outreach attempts are going unanswered more often than expected."))

    if beneficiary.food_insecurity_index is not None and beneficiary.food_insecurity_index >= 6:
        reasons.append((10, "Food insecurity flagged", "The beneficiary household carries a high food insecurity signal."))
    elif beneficiary.food_insecurity_index is not None and beneficiary.food_insecurity_index >= 4:
        reasons.append((6, "Food insecurity flagged", "Food insecurity indicators are elevated for this household."))

    if beneficiary.distance_to_service_km is not None and beneficiary.distance_to_service_km >= 10:
        reasons.append((8, "Distance to service point is high", "Travel distance to the service point is above 10 km."))

    if beneficiary.pmt_score is not None and beneficiary.pmt_score <= 30:
        reasons.append((6, "Economic vulnerability at enrollment", "Proxy means or vulnerability scoring indicates elevated household stress."))

    soft_signal_weights = {
        "household_stability_signal": (
            beneficiary.household_stability_signal,
            8,
            "Household instability observed",
            "Recent field observations indicate household instability that may disrupt participation.",
        ),
        "economic_stress_signal": (
            beneficiary.economic_stress_signal,
            8,
            "Economic stress observed",
            "Recent field observations suggest meaningful economic stress in the household.",
        ),
        "family_support_signal": (
            beneficiary.family_support_signal,
            7,
            "Family support risk observed",
            "Recent field observations suggest lower family or caregiver support.",
        ),
        "health_change_signal": (
            beneficiary.health_change_signal,
            9,
            "Health deterioration observed",
            "Recent field observations suggest a health change affecting retention risk.",
        ),
        "motivation_signal": (
            beneficiary.motivation_signal,
            7,
            "Motivation decline observed",
            "Recent field observations suggest reduced motivation or engagement.",
        ),
    }
    for signal_value, max_weight, title, description in soft_signal_weights.values():
        if signal_value is None:
            continue
        if signal_value >= 4:
            reasons.append((max_weight, title, description))
        elif signal_value == 3:
            reasons.append((max(4, max_weight - 3), title, description))

    phase_factor = _phase_weight(beneficiary.phase)
    if phase_factor:
        reasons.append((phase_factor[0], phase_factor[1], "The beneficiary is in a phase where dropout typically spikes."))

    notes_blob = " ".join(
        [
            beneficiary.current_note or "",
            *(event.notes or "" for event in ordered_events[:4]),
        ]
    ).lower()
    reasons.extend(_keyword_factors(notes_blob))

    recent_intervention = next((intervention for intervention in sorted(interventions, key=lambda item: item.logged_at, reverse=True)), None)
    if recent_intervention is None:
        intervention_status = "Not contacted"
    elif recent_intervention.status == "queued":
        intervention_status = f"Queued for {recent_intervention.assigned_to or 'follow-up queue'}"
    elif recent_intervention.status == "attempted":
        intervention_status = f"Attempted ({recent_intervention.attempt_count} tries)"
    elif recent_intervention.status == "reached":
        intervention_status = "Reached - verify status"
    elif recent_intervention.status == "verified":
        intervention_status = (
            f"Verified: {recent_intervention.verification_status.replace('_', ' ')}"
            if recent_intervention.verification_status
            else "Verified"
        )
    elif recent_intervention.status == "dismissed":
        intervention_status = "Dismissed"
    elif recent_intervention.status == "closed":
        intervention_status = "Closed"
    elif recent_intervention.status == "escalated":
        intervention_status = "Escalated"
    else:
        intervention_status = recent_intervention.action_type
    if recent_intervention and recent_intervention.successful is True:
        reasons.append((-8, "Recent follow-up succeeded", "A recent intervention was logged as successful, which reduces immediate dropout risk."))

    score += sum(weight for weight, _, _ in reasons)
    risk_score = max(5, min(98, score))

    if risk_score >= 75:
        risk_level = "High"
    elif risk_score >= 50:
        risk_level = "Medium"
    else:
        risk_level = "Low"

    ranked_reasons = sorted(reasons, key=lambda item: item[0], reverse=True)
    positive_reasons = [item for item in ranked_reasons if item[0] > 0][:3]

    if positive_reasons:
        explanation = " ".join(reason_text for _, _, reason_text in positive_reasons)
        flags = [driver_name for _, driver_name, _ in positive_reasons]
        driver_names = flags.copy()
    else:
        explanation = "Recent contact, attendance, and follow-up signals remain stable for this beneficiary."
        flags = ["Stable engagement"]
        driver_names = flags.copy()

    known_fields = [
        beneficiary.food_insecurity_index,
        beneficiary.pmt_score,
        beneficiary.distance_to_service_km,
        beneficiary.household_stability_signal,
        beneficiary.economic_stress_signal,
        beneficiary.family_support_signal,
        beneficiary.health_change_signal,
        beneficiary.motivation_signal,
        beneficiary.phase,
        beneficiary.cohort,
    ]
    populated_fields = sum(1 for value in known_fields if value not in (None, ""))
    confidence = "High confidence" if len(events) >= 4 and populated_fields >= 2 else "Limited data"

    return RiskAssessment(
        risk_score=risk_score,
        risk_level=risk_level,
        explanation=explanation,
        recommended_action=recommended_action_for(beneficiary.program.program_type, risk_level),
        flags=flags,
        driver_names=driver_names,
        last_contact_days=last_contact_days,
        attendance_rate_30d=attendance_rate_30d,
        confidence=confidence,
        intervention_status=intervention_status,
        dropout_probability=risk_score / 100,
    )
