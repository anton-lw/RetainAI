"""Governance and misuse-prevention helpers.

This service centralizes beneficiary-governance views, export shaping, and
misuse-oriented alert logic. It exists because governance in RetainAI is a
first-class feature, not an afterthought layered on top of the queue.
"""

from __future__ import annotations

import csv
import io
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app import schemas
from app.core.time import utc_now
from app.models import Beneficiary, Program
from app.services.privacy import ensure_beneficiary_token
from app.services.modeling import load_deployed_model, score_beneficiary
from app.services.scoring import assess_beneficiary_risk


def _load_beneficiaries(db: Session) -> list[Beneficiary]:
    statement = (
        select(Beneficiary)
        .options(
            selectinload(Beneficiary.program).selectinload(Program.data_policy),
            selectinload(Beneficiary.monitoring_events),
            selectinload(Beneficiary.interventions),
        )
        .order_by(Beneficiary.updated_at.desc())
    )
    return list(db.scalars(statement).unique().all())


def mask_external_id(value: str) -> str:
    if len(value) <= 4:
        return "*" * len(value)
    return f"{value[:3]}***{value[-2:]}"


def pseudonymize_name(value: str, beneficiary_id: str) -> str:
    suffix = beneficiary_id.split("-")[0][:8]
    return f"Beneficiary {suffix}"


def list_governance_beneficiaries(db: Session, limit: int = 25) -> list[schemas.BeneficiaryGovernanceRecord]:
    beneficiaries = _load_beneficiaries(db)
    loaded_model = load_deployed_model(db)
    records: list[schemas.BeneficiaryGovernanceRecord] = []

    for beneficiary in beneficiaries[:limit]:
        prediction, heuristic = score_beneficiary(beneficiary, None if beneficiary.opted_out else loaded_model)
        last_intervention = next(iter(beneficiary.interventions), None)
        records.append(
            schemas.BeneficiaryGovernanceRecord(
                id=beneficiary.id,
                full_name=beneficiary.full_name,
                external_id_masked=mask_external_id(beneficiary.external_id),
                pii_token=ensure_beneficiary_token(db, beneficiary).pii_token,
                program_name=beneficiary.program.name,
                region=beneficiary.region,
                status=beneficiary.status,
                opted_out=beneficiary.opted_out,
                modeling_consent_status=beneficiary.modeling_consent_status,  # type: ignore[arg-type]
                consent_captured_at=beneficiary.consent_captured_at,
                consent_explained_at=beneficiary.consent_explained_at,
                consent_method=beneficiary.consent_method,
                consent_note=beneficiary.consent_note,
                risk_level=prediction.risk_level,  # type: ignore[arg-type]
                risk_score=prediction.risk_score,
                last_contact_days=heuristic.last_contact_days,
                last_intervention_at=last_intervention.logged_at if last_intervention is not None else None,
            )
        )

    return records


def build_misuse_alerts(db: Session, limit: int = 10) -> list[schemas.GovernanceAlert]:
    beneficiaries = _load_beneficiaries(db)
    alerts: list[schemas.GovernanceAlert] = []

    for beneficiary in beneficiaries:
        if beneficiary.dropout_date is None or beneficiary.status != "dropped":
            continue
        if beneficiary.opted_out:
            continue

        prior_events = [
            event for event in beneficiary.monitoring_events if event.event_date <= beneficiary.dropout_date
        ]
        prior_interventions = [
            intervention
            for intervention in beneficiary.interventions
            if intervention.logged_at.date() <= beneficiary.dropout_date
        ]
        recent_interventions = [
            intervention
            for intervention in prior_interventions
            if intervention.logged_at.date() >= beneficiary.dropout_date - timedelta(days=30)
        ]
        assessment = assess_beneficiary_risk(beneficiary, prior_events, prior_interventions)

        if assessment.risk_level == "Low" or recent_interventions:
            continue

        level = "attention" if assessment.risk_level == "High" else "warning"
        alerts.append(
            schemas.GovernanceAlert(
                beneficiary_id=beneficiary.id,
                beneficiary_name=beneficiary.full_name,
                program_name=beneficiary.program.name,
                region=beneficiary.region,
                alert_level=level,  # type: ignore[arg-type]
                dropout_date=beneficiary.dropout_date.isoformat(),
                risk_level=assessment.risk_level,  # type: ignore[arg-type]
                note=(
                    f"{beneficiary.full_name} dropped out on {beneficiary.dropout_date.isoformat()} with "
                    f"{assessment.risk_level.lower()} disengagement signals but no supportive intervention logged in the prior 30 days."
                ),
            )
        )

    alerts.sort(key=lambda item: (0 if item.alert_level == "attention" else 1, item.dropout_date), reverse=False)
    return alerts[:limit]


def update_beneficiary_opt_out(
    db: Session,
    beneficiary: Beneficiary,
    *,
    opted_out: bool,
    modeling_consent_status: str | None = None,
    consent_method: str | None = None,
    consent_note: str | None = None,
    explained_to_beneficiary: bool | None = None,
) -> Beneficiary:
    beneficiary.opted_out = opted_out
    if modeling_consent_status is not None:
        beneficiary.modeling_consent_status = modeling_consent_status
        if modeling_consent_status in {"granted", "waived"}:
            beneficiary.consent_captured_at = beneficiary.consent_captured_at or utc_now()
        elif modeling_consent_status in {"declined", "withdrawn"}:
            beneficiary.opted_out = True
    if consent_method is not None:
        beneficiary.consent_method = consent_method
    if consent_note is not None:
        beneficiary.consent_note = consent_note
    if explained_to_beneficiary:
        beneficiary.consent_explained_at = utc_now()
    db.add(beneficiary)
    db.commit()
    db.refresh(beneficiary)
    return beneficiary


def build_csv_export(
    *,
    dataset: str,
    risk_cases: list[schemas.RiskCase] | None = None,
    interventions: list[schemas.InterventionRecord] | None = None,
    include_pii: bool = False,
) -> str:
    output = io.StringIO()

    if dataset == "risk_cases":
        assert risk_cases is not None
        fieldnames = [
            "beneficiary",
            "beneficiary_token",
            "program",
            "program_type",
            "region",
            "risk_level",
            "risk_score",
            "recommended_action",
            "last_contact_days",
            "attendance_rate_30d",
            "confidence",
            "opted_out",
        ]
        writer = csv.DictWriter(output, fieldnames=fieldnames)
        writer.writeheader()
        for item in risk_cases:
            writer.writerow(
                {
                    "beneficiary": item.name if include_pii else pseudonymize_name(item.name, item.id),
                    "beneficiary_token": getattr(item, "pii_token", None) or f"tok_{item.id.split('-')[0][:8]}",
                    "program": item.program,
                    "program_type": item.program_type,
                    "region": item.region,
                    "risk_level": item.risk_level,
                    "risk_score": item.risk_score,
                    "recommended_action": item.recommended_action,
                    "last_contact_days": item.last_contact_days,
                    "attendance_rate_30d": item.attendance_rate_30d,
                    "confidence": item.confidence,
                    "opted_out": "yes" if item.opted_out else "no",
                }
            )
        return output.getvalue()

    assert interventions is not None
    fieldnames = ["beneficiary", "beneficiary_token", "action_type", "note", "successful", "logged_at"]
    writer = csv.DictWriter(output, fieldnames=fieldnames)
    writer.writeheader()
    for item in interventions:
        writer.writerow(
            {
                "beneficiary": item.beneficiary_name if include_pii else pseudonymize_name(item.beneficiary_name, item.beneficiary_id),
                "beneficiary_token": f"tok_{item.beneficiary_id.split('-')[0][:8]}",
                "action_type": item.action_type,
                "note": item.note or "",
                "successful": item.successful if item.successful is not None else "",
                "logged_at": item.logged_at,
            }
        )
    return output.getvalue()
