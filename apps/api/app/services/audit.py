"""Audit-log helpers for security-sensitive and governance-sensitive actions.

Routes call into this module when they need a stable, low-friction way to
persist who did what, when, and in what context. Audit coverage is a core
product requirement because RetainAI operates on sensitive beneficiary data and
must support misuse review, export review, and administrative forensics.
"""

from __future__ import annotations

from collections.abc import Mapping

from fastapi import Request
from sqlalchemy.orm import Session

from app.models import AuditLog, User


def _serialize_detail(value: object) -> str | int | float | bool | None:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def record_audit_event(
    db: Session,
    actor: User | None,
    action: str,
    resource_type: str,
    resource_id: str | None = None,
    details: Mapping[str, object] | None = None,
    request: Request | None = None,
    actor_email_override: str | None = None,
    actor_role_override: str | None = None,
) -> AuditLog:
    serialized_details = None
    if details:
        serialized_details = {key: _serialize_detail(value) for key, value in details.items()}

    log = AuditLog(
        actor_id=actor.id if actor is not None else None,
        actor_email=actor.email if actor is not None else actor_email_override,
        actor_role=actor.role if actor is not None else actor_role_override,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        details=serialized_details,
        ip_address=request.client.host if request and request.client else None,
    )
    db.add(log)
    db.commit()
    db.refresh(log)
    return log
