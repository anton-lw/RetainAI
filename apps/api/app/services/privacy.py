"""Privacy-policy enforcement helpers.

This module contains the deployment-facing privacy logic: program data-policy
serialization, export eligibility checks, tokenization support, and residency
aware policy behavior. It complements, but does not replace, local legal and
infrastructure review.
"""

from __future__ import annotations

import base64
import hashlib
import hmac

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import schemas
from app.core.config import get_settings
from app.core.time import utc_now
from app.models import Beneficiary, Program, ProgramDataPolicy


settings = get_settings()


def tokenize_value(namespace: str, raw_value: str) -> str:
    digest = hmac.new(
        settings.derived_privacy_token_key.encode("utf-8"),
        f"{namespace}:{raw_value}".encode("utf-8"),
        hashlib.sha256,
    ).digest()
    return base64.urlsafe_b64encode(digest).decode("utf-8").rstrip("=")[:20]


def ensure_beneficiary_token(db: Session, beneficiary: Beneficiary) -> Beneficiary:
    if not beneficiary.pii_token:
        beneficiary.pii_token = f"tok_{tokenize_value('beneficiary', f'{beneficiary.id}:{beneficiary.external_id}')}"
        beneficiary.pii_tokenized_at = utc_now()
        db.add(beneficiary)
        db.commit()
        db.refresh(beneficiary)
    return beneficiary


def ensure_program_data_policy(db: Session, program: Program) -> ProgramDataPolicy:
    policy = db.scalar(select(ProgramDataPolicy).where(ProgramDataPolicy.program_id == program.id))
    if policy is not None:
        return policy

    policy = ProgramDataPolicy(
        program_id=program.id,
        data_residency_region=settings.deployment_region,
        storage_mode="self_hosted",
        cross_border_transfers_allowed=False,
        pii_tokenization_enabled=True,
        consent_required=True,
        federated_learning_enabled=True,
    )
    db.add(policy)
    db.commit()
    db.refresh(policy)
    return policy


def serialize_program_data_policy(policy: ProgramDataPolicy) -> schemas.ProgramDataPolicyRead:
    return schemas.ProgramDataPolicyRead(
        id=policy.id,
        program_id=policy.program_id,
        storage_mode=policy.storage_mode,  # type: ignore[arg-type]
        data_residency_region=policy.data_residency_region,
        cross_border_transfers_allowed=policy.cross_border_transfers_allowed,
        pii_tokenization_enabled=policy.pii_tokenization_enabled,
        consent_required=policy.consent_required,
        federated_learning_enabled=policy.federated_learning_enabled,
        updated_at=policy.updated_at,
    )


def list_program_data_policies(db: Session) -> list[schemas.ProgramDataPolicyRead]:
    programs = db.scalars(select(Program).order_by(Program.name.asc())).all()
    return [serialize_program_data_policy(ensure_program_data_policy(db, program)) for program in programs]


def update_program_data_policy(
    db: Session,
    program_id: str,
    payload: schemas.ProgramDataPolicyUpdate,
) -> schemas.ProgramDataPolicyRead:
    program = db.get(Program, program_id)
    if program is None:
        raise ValueError("Program not found")
    policy = ensure_program_data_policy(db, program)
    policy.storage_mode = payload.storage_mode
    policy.data_residency_region = payload.data_residency_region
    policy.cross_border_transfers_allowed = payload.cross_border_transfers_allowed
    policy.pii_tokenization_enabled = payload.pii_tokenization_enabled
    policy.consent_required = payload.consent_required
    policy.federated_learning_enabled = payload.federated_learning_enabled
    db.add(policy)
    db.commit()
    db.refresh(policy)
    return serialize_program_data_policy(policy)


def can_export_program_pii(program: Program, *, include_pii: bool) -> tuple[bool, str | None]:
    policy = program.data_policy
    if not include_pii or policy is None:
        return True, None
    if policy.storage_mode == "self_hosted":
        return True, None
    if policy.data_residency_region == settings.deployment_region:
        return True, None
    if policy.cross_border_transfers_allowed:
        return True, None
    return False, (
        f"PII export blocked for {program.name}: policy requires data residency in "
        f"{policy.data_residency_region}, but this deployment is running in {settings.deployment_region}."
    )
