"""FastAPI application entrypoint for RetainAI.

This module assembles the HTTP surface for the entire platform. It wires
authentication, governance, ingestion, scoring, evaluation, exports, runtime
health, and model operations into one API application. For maintainers, this is
the best starting point when you need to answer "which endpoint owns which
workflow?" or "what service layer backs this route?".

The broader pattern is:

1. validate the request and caller role
2. delegate business logic to a service module
3. record an audit event where appropriate
4. return a schema-backed response model
"""

from __future__ import annotations

import json
import logging
from contextlib import asynccontextmanager
from datetime import datetime
from time import perf_counter
from typing import Literal
from uuid import uuid4

import httpx
from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, Query, Request, Response, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app import schemas
from app.core.config import get_settings
from app.core.observability import (
    CONTENT_TYPE_LATEST,
    HTTP_REQUESTS_IN_PROGRESS,
    clear_request_id,
    configure_observability,
    observe_http_request,
    render_metrics,
    set_request_id,
)
from app.core.time import utc_now
from app.db import SessionLocal, get_db, init_db
from app.models import AuditLog, Beneficiary, DataConnector, ImportBatch, Intervention, JobRecord, ModelSchedule, Program, User, UserSession
from app.seed import seed_database
from app.services.analytics import (
    build_donor_excel_report,
    build_donor_pdf_report,
    build_donor_report_summary,
    build_dashboard_summary,
    build_follow_up_export,
    build_intervention_effectiveness_summary,
    build_retention_analytics,
    build_retention_curves,
    build_risk_cases,
    filter_risk_cases,
    list_interventions,
    list_program_operational_settings,
    update_program_operational_setting,
)
from app.services.automation import ensure_model_schedule, update_model_schedule
from app.services.audit import record_audit_event
from app.services.auth import (
    ROLE_ADMIN,
    ROLE_COUNTRY_DIRECTOR,
    ROLE_FIELD_COORDINATOR,
    ROLE_ME_OFFICER,
    authenticate_user,
    create_user_session,
    create_access_token,
    ensure_bootstrap_admin,
    get_current_active_user,
    get_current_user_session,
    list_active_sessions,
    login_allowed,
    mark_login_success,
    require_roles,
    revoke_user_session,
    upsert_sso_user,
)
from app.services.connectors import (
    build_preview_connector,
    create_connector,
    dispatch_risk_queue,
    list_connectors,
    list_dispatch_runs,
    list_sync_runs,
    probe_connector,
    update_connector as update_connector_service,
)
from app.services.evaluation import (
    create_shadow_run,
    evaluate_model_backtest,
    list_evaluation_reports,
    list_program_validation_settings,
    list_shadow_runs,
    persist_evaluation_report,
    update_program_validation_setting,
)
from app.services.governance import (
    build_csv_export,
    build_misuse_alerts,
    list_governance_beneficiaries,
    update_beneficiary_opt_out,
)
from app.services.imports import (
    DatasetType,
    analyze_import_file,
    detect_mapping,
    import_beneficiaries,
    import_events,
    list_quality_issues,
    parse_csv_bytes,
    parse_tabular_bytes,
    validate_mapping,
)
from app.services.jobs import (
    JOB_TYPE_AUTOMATION_RUN_DUE,
    JOB_TYPE_CONNECTOR_SYNC,
    JOB_TYPE_MODEL_TRAIN,
    enqueue_job,
    list_jobs,
    requeue_job,
    run_pending_jobs,
    serialize_job,
)
from app.services.labeling import build_operational_settings_profile, canonical_protocol_step, project_tracing_protocol
from app.services.operations import build_runtime_status, build_worker_health, enforce_runtime_status
from app.services.federated import (
    aggregate_federated_round,
    build_federated_status,
    export_federated_update,
    list_federated_rounds,
)
from app.services.modeling import build_feature_store_summary, build_model_status, ensure_model_ready, refresh_model_drift_report
from app.services.modeling import load_deployed_model, score_beneficiary
from app.services.privacy import can_export_program_pii, list_program_data_policies, update_program_data_policy
from app.services.secrets import decrypt_secret
from app.services.sso import (
    SSOAuthenticationError,
    SSOConfigurationError,
    build_oidc_authorization_url,
    build_sso_config,
    exchange_oidc_code,
)
from app.services.synthetic_data import list_stress_scenarios, summarize_stress_suite, summarize_synthetic_portfolio


settings = get_settings()
configure_observability()
logger = logging.getLogger("retainai.http")


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    with SessionLocal() as session:
        ensure_bootstrap_admin(session)
        if settings.auto_seed:
            seed_database(session)
        ensure_model_schedule(session)
        ensure_model_ready(session)
        enforce_runtime_status(session)
    yield


app = FastAPI(
    title=settings.app_name,
    version="0.6.0",
    description="Operational retention intelligence API for RetainAI.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=settings.cors_allowed_methods,
    allow_headers=settings.cors_allowed_headers,
)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.trusted_hosts)


@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    request_id = request.headers.get("X-Request-ID", "").strip() or str(uuid4())
    set_request_id(request_id)
    HTTP_REQUESTS_IN_PROGRESS.inc()
    started_at = perf_counter()
    response: Response | None = None
    route_path = request.url.path

    try:
        response = await call_next(request)
        route = request.scope.get("route")
        if route is not None and getattr(route, "path", None):
            route_path = str(route.path)

        response.headers["X-Request-ID"] = request_id
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = settings.security_referrer_policy
        response.headers["Permissions-Policy"] = settings.security_permissions_policy
        response.headers["Cross-Origin-Opener-Policy"] = "same-origin"
        response.headers["Cross-Origin-Resource-Policy"] = "same-origin"
        response.headers["Cache-Control"] = "no-store"
        if settings.security_hsts_enabled:
            response.headers["Strict-Transport-Security"] = f"max-age={settings.security_hsts_max_age}; includeSubDomains"
        return response
    except Exception:
        duration_seconds = perf_counter() - started_at
        observe_http_request(
            method=request.method,
            path=route_path,
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            duration_seconds=duration_seconds,
        )
        logger.exception(
            "request_failed",
            extra={
                "event": "http.request",
                "method": request.method,
                "path": route_path,
                "status_code": status.HTTP_500_INTERNAL_SERVER_ERROR,
                "duration_ms": round(duration_seconds * 1000, 2),
            },
        )
        raise
    finally:
        if response is not None:
            duration_seconds = perf_counter() - started_at
            observe_http_request(
                method=request.method,
                path=route_path,
                status_code=response.status_code,
                duration_seconds=duration_seconds,
            )
            logger.info(
                "request_completed",
                extra={
                    "event": "http.request",
                    "method": request.method,
                    "path": route_path,
                    "status_code": response.status_code,
                    "duration_ms": round(duration_seconds * 1000, 2),
                },
            )
        HTTP_REQUESTS_IN_PROGRESS.dec()
        clear_request_id()


def _serialize_batch(batch: ImportBatch) -> schemas.ImportBatchRead:
    return schemas.ImportBatchRead(
        id=batch.id,
        program_id=batch.program_id,
        program_name=batch.program.name,
        dataset_type=batch.dataset_type,
        source_format=batch.source_format,
        filename=batch.filename,
        records_received=batch.records_received,
        records_processed=batch.records_processed,
        records_failed=batch.records_failed,
        duplicates_detected=batch.duplicates_detected,
        resolved_mapping=batch.resolved_mapping,
        warnings=batch.warning_preview,
        quality_summary=batch.quality_summary,
        created_at=batch.created_at,
    )


def _serialize_intervention(intervention: Intervention) -> schemas.InterventionRecord:
    return schemas.InterventionRecord(
        id=intervention.id,
        beneficiary_id=intervention.beneficiary_id,
        beneficiary_name=intervention.beneficiary.full_name,
        action_type=intervention.action_type,
        support_channel=intervention.support_channel,
        protocol_step=intervention.protocol_step,  # type: ignore[arg-type]
        status=intervention.status,
        verification_status=intervention.verification_status,
        assigned_to=intervention.assigned_to,
        assigned_site=intervention.assigned_site,
        due_at=intervention.due_at.isoformat() + "Z" if intervention.due_at else None,
        completed_at=intervention.completed_at.isoformat() + "Z" if intervention.completed_at else None,
        verified_at=intervention.verified_at.isoformat() + "Z" if intervention.verified_at else None,
        verification_note=intervention.verification_note,
        dismissal_reason=intervention.dismissal_reason,
        attempt_count=intervention.attempt_count,
        source=intervention.source,
        risk_level=intervention.risk_level,
        priority_rank=intervention.priority_rank,
        note=intervention.note,
        successful=intervention.successful,
        soft_signals=schemas.SoftSignalSnapshot(
            household_stability_signal=intervention.beneficiary.household_stability_signal,
            economic_stress_signal=intervention.beneficiary.economic_stress_signal,
            family_support_signal=intervention.beneficiary.family_support_signal,
            health_change_signal=intervention.beneficiary.health_change_signal,
            motivation_signal=intervention.beneficiary.motivation_signal,
        )
        if any(
            value is not None
            for value in (
                intervention.beneficiary.household_stability_signal,
                intervention.beneficiary.economic_stress_signal,
                intervention.beneficiary.family_support_signal,
                intervention.beneficiary.health_change_signal,
                intervention.beneficiary.motivation_signal,
            )
        )
        else None,
        logged_at=intervention.logged_at.isoformat() + "Z",
    )


def _serialize_audit_log(item: AuditLog) -> schemas.AuditLogRecord:
    return schemas.AuditLogRecord(
        id=item.id,
        actor_email=item.actor_email,
        actor_role=item.actor_role,
        action=item.action,
        resource_type=item.resource_type,
        resource_id=item.resource_id,
        details=item.details,
        ip_address=item.ip_address,
        created_at=item.created_at,
    )


def _apply_soft_signals_to_beneficiary(
    beneficiary: Beneficiary,
    payload: schemas.BeneficiarySoftSignalsUpdate | None,
) -> None:
    if payload is None:
        return
    update_payload = payload.model_dump(exclude_unset=True)
    for field_name, value in update_payload.items():
        setattr(beneficiary, field_name, value)


def _derive_intervention_success(verification_status: str | None) -> bool | None:
    positive_statuses = {"still_enrolled", "re_engaged", "silent_transfer", "completed_elsewhere"}
    negative_statuses = {"deceased", "unreachable", "declined_support", "dropped_out_confirmed"}
    if verification_status in positive_statuses:
        return True
    if verification_status in negative_statuses:
        return False
    return None


def _apply_intervention_payload(
    intervention: Intervention,
    beneficiary: Beneficiary,
    payload: schemas.InterventionRequest | schemas.InterventionUpdate,
) -> None:
    update_payload = payload.model_dump(exclude_unset=True)
    soft_signals = update_payload.pop("soft_signals", None)
    if "action_type" in update_payload and update_payload["action_type"] is not None:
        intervention.action_type = str(update_payload["action_type"])
    if "support_channel" in update_payload:
        intervention.support_channel = update_payload["support_channel"]
    if "protocol_step" in update_payload:
        intervention.protocol_step = update_payload["protocol_step"]
    if "status" in update_payload and update_payload["status"] is not None:
        intervention.status = str(update_payload["status"])
    if "verification_status" in update_payload:
        intervention.verification_status = update_payload["verification_status"]
    if "assigned_to" in update_payload:
        intervention.assigned_to = update_payload["assigned_to"]
        beneficiary.assigned_case_worker = update_payload["assigned_to"]
    if "assigned_site" in update_payload:
        intervention.assigned_site = update_payload["assigned_site"]
        beneficiary.assigned_site = update_payload["assigned_site"]
    if "due_at" in update_payload:
        intervention.due_at = update_payload["due_at"]
    if "verification_note" in update_payload:
        intervention.verification_note = update_payload["verification_note"]
    if "dismissal_reason" in update_payload:
        intervention.dismissal_reason = update_payload["dismissal_reason"]
    if "attempt_count" in update_payload and update_payload["attempt_count"] is not None:
        intervention.attempt_count = int(update_payload["attempt_count"])
    if "source" in update_payload and update_payload["source"] is not None:
        intervention.source = str(update_payload["source"])
    if "risk_level" in update_payload:
        intervention.risk_level = update_payload["risk_level"]
    if "priority_rank" in update_payload:
        intervention.priority_rank = update_payload["priority_rank"]
    if "note" in update_payload:
        intervention.note = update_payload["note"]
    if "successful" in update_payload:
        intervention.successful = update_payload["successful"]

    if intervention.protocol_step is None and intervention.support_channel:
        intervention.protocol_step = canonical_protocol_step(intervention.support_channel)
    elif intervention.protocol_step is not None and not intervention.support_channel:
        intervention.support_channel = intervention.protocol_step

    if beneficiary.program is not None:
        profile = build_operational_settings_profile(
            beneficiary.program.program_type,
            beneficiary.program.operational_setting,
        )
        if intervention.risk_level is None:
            intervention.risk_level = "Medium"
        projection = project_tracing_protocol(
            risk_level=intervention.risk_level,
            profile=profile,
            workflow=intervention,
            reference_time=utc_now(),
        )
        intervention.protocol_step = projection.current_step
        if "support_channel" not in update_payload or update_payload.get("support_channel") in {None, ""}:
            intervention.support_channel = projection.current_channel
        if ("due_at" not in update_payload or update_payload.get("due_at") is None) and intervention.status not in {
            "verified",
            "closed",
            "dismissed",
        }:
            intervention.due_at = projection.current_due_at

    _apply_soft_signals_to_beneficiary(
        beneficiary,
        schemas.BeneficiarySoftSignalsUpdate(**soft_signals) if soft_signals else None,
    )

    now = utc_now()
    if intervention.status in {"attempted", "reached", "verified", "closed", "dismissed", "escalated"} and intervention.completed_at is None:
        intervention.completed_at = now
    if intervention.status in {"verified", "closed"} and intervention.verified_at is None:
        intervention.verified_at = now
    if intervention.status == "dismissed" and not intervention.dismissal_reason:
        intervention.dismissal_reason = "Dismissed by user"
    if intervention.successful is None:
        intervention.successful = _derive_intervention_success(intervention.verification_status)


def _serialize_model_schedule(schedule: ModelSchedule) -> schemas.ModelScheduleRead:
    return schemas.ModelScheduleRead(
        id=schedule.id,
        enabled=schedule.enabled,
        cadence=schedule.cadence,  # type: ignore[arg-type]
        auto_retrain_after_sync=schedule.auto_retrain_after_sync,
        last_run_at=schedule.last_run_at,
        next_run_at=schedule.next_run_at,
        updated_at=schedule.updated_at,
    )


def _serialize_job_record(job: JobRecord) -> schemas.JobRead:
    return serialize_job(job)


def _enforce_pii_export_policy(db: Session, programs: list[Program], include_pii: bool) -> None:
    if not include_pii:
        return
    for program in programs:
        allowed, message = can_export_program_pii(program, include_pii=include_pii)
        if not allowed:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=message or "PII export blocked by policy")


def _serialize_session(session: UserSession) -> schemas.SessionRecord:
    return schemas.SessionRecord(
        id=session.id,
        auth_method=session.auth_method,
        token_key_id=session.token_key_id,
        source_ip=session.source_ip,
        user_agent=session.user_agent,
        issued_at=session.issued_at,
        expires_at=session.expires_at,
        last_seen_at=session.last_seen_at,
        revoked_at=session.revoked_at,
        revoked_reason=session.revoked_reason,
    )


def _build_token_response(user: User, session: UserSession) -> schemas.TokenResponse:
    return schemas.TokenResponse(
        access_token=create_access_token(user, session),
        expires_in_seconds=settings.access_token_expire_minutes * 60,
        session_id=session.id,
        user=user,
    )


@app.get("/health", response_model=schemas.HealthResponse)
def health(db: Session = Depends(get_db)) -> schemas.HealthResponse:
    program_count = db.scalar(select(func.count(Program.id))) or 0
    return schemas.HealthResponse(
        status="ok",
        environment=settings.environment,
        database_configured=bool(settings.database_url),
        programs=program_count,
    )


@app.get("/livez", response_model=schemas.ProbeResponse)
def livez() -> schemas.ProbeResponse:
    return schemas.ProbeResponse(status="ok", component="api", detail="Application process is running.")


@app.get("/readyz", response_model=schemas.ProbeResponse)
def readyz(response: Response, db: Session = Depends(get_db)) -> schemas.ProbeResponse:
    try:
        db.scalar(select(func.count(Program.id)))
    except Exception as exc:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return schemas.ProbeResponse(status="degraded", component="database", detail=str(exc))
    return schemas.ProbeResponse(status="ok", component="database", detail="Database connection is ready.")


@app.get(settings.observability_metrics_path)
def metrics(db: Session = Depends(get_db)) -> Response:
    return Response(content=render_metrics(db), media_type=CONTENT_TYPE_LATEST)


@app.get(f"{settings.api_prefix}/ops/runtime-status", response_model=schemas.RuntimeStatusRead)
def get_runtime_status(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> schemas.RuntimeStatusRead:
    payload = schemas.RuntimeStatusRead(**build_runtime_status(db))
    record_audit_event(
        db,
        actor=current_user,
        action="ops.runtime_status_viewed",
        resource_type="operations",
        details={"status": payload.status, "violations": len(payload.violations)},
        request=request,
    )
    return payload


@app.get(f"{settings.api_prefix}/ops/worker-health", response_model=schemas.WorkerHealthRead)
def get_worker_health(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> schemas.WorkerHealthRead:
    payload = schemas.WorkerHealthRead(**build_worker_health(db))
    record_audit_event(
        db,
        actor=current_user,
        action="ops.worker_health_viewed",
        resource_type="operations",
        details={"status": payload.status, "backend": payload.backend},
        request=request,
    )
    return payload


@app.post(f"{settings.api_prefix}/auth/login", response_model=schemas.TokenResponse)
def login(
    payload: schemas.LoginRequest,
    request: Request,
    db: Session = Depends(get_db),
) -> schemas.TokenResponse:
    allowed, reason = login_allowed(
        db,
        email=payload.email,
        source_ip=request.client.host if request.client else None,
    )
    if not allowed:
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=reason or "Too many sign-in attempts")
    user = authenticate_user(db, payload.email, payload.password)
    if user is None:
        record_audit_event(
            db,
            actor=None,
            action="auth.login_failed",
            resource_type="session",
            details={"email": payload.email.strip().lower()},
            request=request,
            actor_email_override=payload.email.strip().lower(),
        )
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")

    mark_login_success(db, user)
    session = create_user_session(db, user=user, auth_method="password", request=request)
    record_audit_event(
        db,
        actor=user,
        action="auth.login",
        resource_type="session",
        resource_id=session.id,
        details={"email": user.email, "auth_method": "password"},
        request=request,
    )
    return _build_token_response(user, session)


@app.get(f"{settings.api_prefix}/auth/me", response_model=schemas.CurrentUser)
def get_current_session(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> User:
    record_audit_event(
        db,
        actor=current_user,
        action="auth.session_viewed",
        resource_type="session",
        resource_id=current_user.id,
        request=request,
    )
    return current_user


@app.get(f"{settings.api_prefix}/auth/sessions", response_model=list[schemas.SessionRecord])
def get_auth_sessions(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> list[schemas.SessionRecord]:
    sessions = [_serialize_session(item) for item in list_active_sessions(db, current_user)]
    record_audit_event(
        db,
        actor=current_user,
        action="auth.sessions_viewed",
        resource_type="session",
        details={"count": len(sessions)},
        request=request,
    )
    return sessions


@app.post(f"{settings.api_prefix}/auth/logout", response_model=schemas.LogoutResponse)
def logout(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    current_session: UserSession = Depends(get_current_user_session),
) -> schemas.LogoutResponse:
    revoked = revoke_user_session(db, current_session, reason="user_logout")
    record_audit_event(
        db,
        actor=current_user,
        action="auth.logout",
        resource_type="session",
        resource_id=revoked.id,
        details={"auth_method": revoked.auth_method},
        request=request,
    )
    return schemas.LogoutResponse(status="revoked", session_id=revoked.id)


@app.get(f"{settings.api_prefix}/auth/sso/config", response_model=schemas.SSOConfigRead)
def get_sso_config() -> schemas.SSOConfigRead:
    return schemas.SSOConfigRead(**build_sso_config())


@app.post(f"{settings.api_prefix}/auth/sso/header-login", response_model=schemas.TokenResponse)
def sso_header_login(
    request: Request,
    db: Session = Depends(get_db),
) -> schemas.TokenResponse:
    if not settings.sso_enabled:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="SSO is not enabled for this deployment")

    email = request.headers.get(settings.sso_header_email)
    if not email:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing SSO identity header")

    user = upsert_sso_user(
        db,
        email=email,
        full_name=request.headers.get(settings.sso_header_name),
        role=request.headers.get(settings.sso_header_role),
    )
    mark_login_success(db, user)
    session = create_user_session(db, user=user, auth_method="sso_header", request=request)
    record_audit_event(
        db,
        actor=user,
        action="auth.sso_login",
        resource_type="session",
        resource_id=session.id,
        details={"provider": settings.sso_provider_label or "header_sso"},
        request=request,
    )
    return _build_token_response(user, session)


@app.get(f"{settings.api_prefix}/auth/sso/oidc/start", response_model=schemas.SSOOidcStartRead)
def start_oidc_login(
    redirect_uri: str = Query(min_length=8, max_length=1000),
) -> schemas.SSOOidcStartRead:
    try:
        payload = build_oidc_authorization_url(redirect_uri)
    except SSOConfigurationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return schemas.SSOOidcStartRead(**payload)


@app.post(f"{settings.api_prefix}/auth/sso/oidc/exchange", response_model=schemas.TokenResponse)
def exchange_oidc_login(
    payload: schemas.SSOOidcExchangeRequest,
    request: Request,
    db: Session = Depends(get_db),
) -> schemas.TokenResponse:
    try:
        user = exchange_oidc_code(
            db,
            code=payload.code,
            state_token=payload.state,
            redirect_uri=payload.redirect_uri,
        )
    except (SSOConfigurationError, SSOAuthenticationError, httpx.HTTPError) as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc
    mark_login_success(db, user)
    session = create_user_session(db, user=user, auth_method="oidc", request=request)
    record_audit_event(
        db,
        actor=user,
        action="auth.sso_login",
        resource_type="session",
        resource_id=session.id,
        details={"provider": settings.sso_provider_label or "oidc"},
        request=request,
    )
    return _build_token_response(user, session)


@app.get(f"{settings.api_prefix}/programs", response_model=list[schemas.ProgramRead])
def list_programs(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> list[Program]:
    programs = list(db.scalars(select(Program).order_by(Program.created_at.desc())).all())
    record_audit_event(
        db,
        actor=current_user,
        action="program.list_viewed",
        resource_type="program",
        details={"count": len(programs)},
        request=request,
    )
    return programs


@app.post(
    f"{settings.api_prefix}/programs",
    response_model=schemas.ProgramRead,
    status_code=status.HTTP_201_CREATED,
)
def create_program(
    payload: schemas.ProgramCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(ROLE_ADMIN, ROLE_ME_OFFICER)),
) -> Program:
    existing = db.scalar(select(Program).where(Program.name == payload.name))
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Program name already exists")

    program = Program(
        name=payload.name,
        program_type=payload.program_type,
        country=payload.country,
        delivery_modality=payload.delivery_modality,
        status="active",
    )
    db.add(program)
    db.commit()
    db.refresh(program)

    record_audit_event(
        db,
        actor=current_user,
        action="program.created",
        resource_type="program",
        resource_id=program.id,
        details={"name": program.name, "program_type": program.program_type},
        request=request,
    )
    return program


@app.get(f"{settings.api_prefix}/imports", response_model=list[schemas.ImportBatchRead])
def list_import_batches(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> list[schemas.ImportBatchRead]:
    statement = (
        select(ImportBatch)
        .options(selectinload(ImportBatch.program))
        .order_by(ImportBatch.created_at.desc())
        .limit(10)
    )
    batches = [_serialize_batch(batch) for batch in db.scalars(statement).all()]
    record_audit_event(
        db,
        actor=current_user,
        action="import.list_viewed",
        resource_type="import_batch",
        details={"count": len(batches)},
        request=request,
    )
    return batches


@app.post(f"{settings.api_prefix}/imports/analyze", response_model=schemas.ImportAnalysisRead)
async def analyze_import_batch(
    request: Request,
    dataset_type: DatasetType = Form(...),
    file: UploadFile = File(...),
    mapping_json: str | None = Form(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(ROLE_ADMIN, ROLE_ME_OFFICER)),
) -> schemas.ImportAnalysisRead:
    file_bytes = await file.read()
    provided_mapping: dict[str, str | None] | None = None
    if mapping_json:
        try:
            provided_mapping = json.loads(mapping_json)
        except json.JSONDecodeError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid mapping_json payload: {exc.msg}",
            ) from exc

    analysis = analyze_import_file(
        file_bytes,
        filename=file.filename or f"{dataset_type}.csv",
        dataset_type=dataset_type,
        provided_mapping=provided_mapping,
    )
    record_audit_event(
        db,
        actor=current_user,
        action="import.analyzed",
        resource_type="import_analysis",
        details={
            "dataset_type": dataset_type,
            "records_received": analysis.records_received,
            "quality_score": analysis.quality_score,
        },
        request=request,
    )
    return schemas.ImportAnalysisRead(
        dataset_type=analysis.dataset_type,
        source_format=analysis.source_format,
        records_received=analysis.records_received,
        duplicate_rows=analysis.duplicate_rows,
        inferred_types=analysis.inferred_types,
        suggested_mapping=analysis.suggested_mapping,
        quality_score=analysis.quality_score,
        warnings=analysis.warnings,
        issues=analysis.issues,
        available_columns=list(analysis.sample_rows[0].keys()) if analysis.sample_rows else [],
        sample_rows=analysis.sample_rows,
    )


@app.get(f"{settings.api_prefix}/imports/{{import_batch_id}}/issues", response_model=list[schemas.DataQualityIssueRecord])
def get_import_issues(
    import_batch_id: str,
    request: Request,
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> list[schemas.DataQualityIssueRecord]:
    batch = db.get(ImportBatch, import_batch_id)
    if batch is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Import batch not found")

    issues = list_quality_issues(db, import_batch_id, limit=limit)
    record_audit_event(
        db,
        actor=current_user,
        action="import.issues_viewed",
        resource_type="data_quality_issue",
        resource_id=import_batch_id,
        details={"count": len(issues), "limit": limit},
        request=request,
    )
    return issues


@app.get(
    f"{settings.api_prefix}/beneficiaries/governance",
    response_model=list[schemas.BeneficiaryGovernanceRecord],
)
def get_governance_beneficiaries(
    request: Request,
    limit: int = Query(default=25, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> list[schemas.BeneficiaryGovernanceRecord]:
    records = list_governance_beneficiaries(db, limit=limit)
    record_audit_event(
        db,
        actor=current_user,
        action="beneficiary.governance_viewed",
        resource_type="beneficiary",
        details={"count": len(records), "limit": limit},
        request=request,
    )
    return records


@app.patch(
    f"{settings.api_prefix}/beneficiaries/{{beneficiary_id}}/governance",
    response_model=schemas.BeneficiaryGovernanceRecord,
)
def patch_beneficiary_governance(
    beneficiary_id: str,
    payload: schemas.BeneficiaryGovernanceUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(ROLE_ADMIN, ROLE_ME_OFFICER)),
) -> schemas.BeneficiaryGovernanceRecord:
    beneficiary = db.scalar(
        select(Beneficiary)
        .options(
            selectinload(Beneficiary.program),
            selectinload(Beneficiary.monitoring_events),
            selectinload(Beneficiary.interventions),
        )
        .where(Beneficiary.id == beneficiary_id)
    )
    if beneficiary is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Beneficiary not found")

    previous = beneficiary.opted_out
    updated = update_beneficiary_opt_out(
        db,
        beneficiary,
        opted_out=payload.opted_out,
        modeling_consent_status=payload.modeling_consent_status,
        consent_method=payload.consent_method,
        consent_note=payload.consent_note,
        explained_to_beneficiary=payload.explained_to_beneficiary,
    )
    record = next(
        item for item in list_governance_beneficiaries(db, limit=200) if item.id == updated.id
    )
    record_audit_event(
        db,
        actor=current_user,
        action="beneficiary.governance_updated",
        resource_type="beneficiary",
        resource_id=updated.id,
        details={
            "previous_opted_out": previous,
            "opted_out": updated.opted_out,
            "modeling_consent_status": updated.modeling_consent_status,
        },
        request=request,
    )
    return record


@app.post(
    f"{settings.api_prefix}/imports/csv",
    response_model=schemas.ImportBatchRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_import_batch(
    request: Request,
    dataset_type: DatasetType = Form(...),
    program_id: str = Form(...),
    file: UploadFile = File(...),
    mapping_json: str | None = Form(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(ROLE_ADMIN, ROLE_ME_OFFICER)),
) -> schemas.ImportBatchRead:
    program = db.get(Program, program_id)
    if program is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Program not found")

    file_bytes = await file.read()
    rows, source_format = parse_tabular_bytes(file_bytes, file.filename or f"{dataset_type}.csv")
    if not rows:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Uploaded file is empty")

    detected_mapping = detect_mapping(list(rows[0].keys()), dataset_type)
    if mapping_json:
        try:
            provided_mapping = json.loads(mapping_json)
        except json.JSONDecodeError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid mapping_json payload: {exc.msg}",
            ) from exc
        mapping = {**detected_mapping, **provided_mapping}
    else:
        mapping = detected_mapping

    missing_fields = validate_mapping(mapping, dataset_type)
    if missing_fields:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Missing required columns: {', '.join(sorted(missing_fields))}",
        )

    if dataset_type == "beneficiaries":
        batch = import_beneficiaries(
            db,
            program,
            rows,
            mapping,
            file.filename or "beneficiaries.csv",
            source_format=source_format,
        )
    else:
        batch = import_events(
            db,
            program,
            rows,
            mapping,
            file.filename or "events.csv",
            source_format=source_format,
        )

    hydrated_batch = db.scalar(
        select(ImportBatch)
        .options(selectinload(ImportBatch.program))
        .where(ImportBatch.id == batch.id)
    )
    assert hydrated_batch is not None

    record_audit_event(
        db,
        actor=current_user,
        action="import.created",
        resource_type="import_batch",
        resource_id=hydrated_batch.id,
        details={
            "dataset_type": hydrated_batch.dataset_type,
            "filename": hydrated_batch.filename,
            "records_processed": hydrated_batch.records_processed,
            "records_failed": hydrated_batch.records_failed,
        },
        request=request,
    )
    return _serialize_batch(hydrated_batch)


@app.get(f"{settings.api_prefix}/connectors", response_model=list[schemas.DataConnectorRead])
def get_connectors(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> list[schemas.DataConnectorRead]:
    connectors = list_connectors(db)
    record_audit_event(
        db,
        actor=current_user,
        action="connector.list_viewed",
        resource_type="data_connector",
        details={"count": len(connectors)},
        request=request,
    )
    return connectors


@app.post(
    f"{settings.api_prefix}/connectors",
    response_model=schemas.DataConnectorRead,
    status_code=status.HTTP_201_CREATED,
)
def create_data_connector(
    payload: schemas.DataConnectorCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(ROLE_ADMIN, ROLE_ME_OFFICER)),
) -> schemas.DataConnectorRead:
    try:
        connector = create_connector(db, payload)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    record_audit_event(
        db,
        actor=current_user,
        action="connector.created",
        resource_type="data_connector",
        resource_id=connector.id,
        details={"connector_type": connector.connector_type, "dataset_type": connector.dataset_type},
        request=request,
    )
    return connector


@app.post(f"{settings.api_prefix}/connectors/preview", response_model=schemas.ConnectorProbeResult)
def preview_data_connector(
    payload: schemas.DataConnectorCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(ROLE_ADMIN, ROLE_ME_OFFICER)),
) -> schemas.ConnectorProbeResult:
    program = db.get(Program, payload.program_id)
    if program is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Program not found")

    try:
        preview_connector = build_preview_connector(program, payload)
        probe = probe_connector(preview_connector)
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    record_audit_event(
        db,
        actor=current_user,
        action="connector.preview_tested",
        resource_type="data_connector",
        details={
            "connector_type": payload.connector_type,
            "dataset_type": payload.dataset_type,
            "record_count": probe.record_count,
            "http_status": probe.http_status,
        },
        request=request,
    )
    return probe


@app.put(f"{settings.api_prefix}/connectors/{{connector_id}}", response_model=schemas.DataConnectorRead)
def update_data_connector(
    connector_id: str,
    payload: schemas.DataConnectorUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(ROLE_ADMIN, ROLE_ME_OFFICER)),
) -> schemas.DataConnectorRead:
    connector = db.scalar(
        select(DataConnector)
        .options(selectinload(DataConnector.program))
        .where(DataConnector.id == connector_id)
    )
    if connector is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Connector not found")

    try:
        updated = update_connector_service(db, connector, payload)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    record_audit_event(
        db,
        actor=current_user,
        action="connector.updated",
        resource_type="data_connector",
        resource_id=updated.id,
        details={"connector_type": updated.connector_type, "schedule_enabled": updated.schedule_enabled},
        request=request,
    )
    return updated


@app.post(f"{settings.api_prefix}/connectors/{{connector_id}}/test", response_model=schemas.ConnectorProbeResult)
def test_data_connector(
    connector_id: str,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(ROLE_ADMIN, ROLE_ME_OFFICER)),
) -> schemas.ConnectorProbeResult:
    connector = db.scalar(
        select(DataConnector)
        .options(selectinload(DataConnector.program))
        .where(DataConnector.id == connector_id)
    )
    if connector is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Connector not found")

    try:
        probe = probe_connector(connector)
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    record_audit_event(
        db,
        actor=current_user,
        action="connector.tested",
        resource_type="data_connector",
        resource_id=connector.id,
        details={"record_count": probe.record_count, "http_status": probe.http_status},
        request=request,
    )
    return probe


@app.post(
    f"{settings.api_prefix}/connectors/{{connector_id}}/webhook",
    response_model=schemas.JobRead,
    status_code=status.HTTP_202_ACCEPTED,
)
def trigger_connector_webhook(
    connector_id: str,
    request: Request,
    x_retainai_webhook_secret: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> schemas.JobRead:
    connector = db.scalar(
        select(DataConnector)
        .options(selectinload(DataConnector.program))
        .where(DataConnector.id == connector_id)
    )
    if connector is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Connector not found")
    if not connector.webhook_enabled:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Webhook sync is not enabled for this connector")

    provided_secret = x_retainai_webhook_secret or request.query_params.get("secret")
    expected_secret = decrypt_secret(connector.encrypted_webhook_secret)
    if expected_secret and provided_secret != expected_secret:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid webhook secret")
    if connector.encrypted_webhook_secret and not provided_secret:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Webhook secret is required")

    schedule = ensure_model_schedule(db)
    connector.last_webhook_at = utc_now()
    db.add(connector)
    db.commit()
    db.refresh(connector)

    job = enqueue_job(
        db,
        job_type=JOB_TYPE_CONNECTOR_SYNC,
        payload={
            "connector_id": connector.id,
            "trigger_mode": "webhook",
            "auto_retrain": schedule.auto_retrain_after_sync,
        },
        created_by=None,
    )
    record_audit_event(
        db,
        actor=None,
        action="connector.webhook_received",
        resource_type="data_connector",
        resource_id=connector.id,
        details={
            "job_id": job.job.id,
            "created": job.created,
            "client_host": request.client.host if request.client else None,
        },
        request=request,
    )
    return _serialize_job_record(job.job)


@app.get(f"{settings.api_prefix}/connectors/sync-runs", response_model=list[schemas.ConnectorSyncRunRead])
def get_connector_sync_runs(
    request: Request,
    limit: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> list[schemas.ConnectorSyncRunRead]:
    runs = list_sync_runs(db, limit=limit)
    record_audit_event(
        db,
        actor=current_user,
        action="connector.sync_runs_viewed",
        resource_type="connector_sync_run",
        details={"count": len(runs), "limit": limit},
        request=request,
    )
    return runs


@app.get(f"{settings.api_prefix}/connectors/dispatch-runs", response_model=list[schemas.ConnectorDispatchRunRead])
def get_connector_dispatch_runs(
    request: Request,
    limit: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> list[schemas.ConnectorDispatchRunRead]:
    runs = list_dispatch_runs(db, limit=limit)
    record_audit_event(
        db,
        actor=current_user,
        action="connector.dispatch_runs_viewed",
        resource_type="connector_dispatch_run",
        details={"count": len(runs), "limit": limit},
        request=request,
    )
    return runs


@app.post(
    f"{settings.api_prefix}/connectors/{{connector_id}}/dispatch",
    response_model=schemas.ConnectorDispatchRunRead,
)
def dispatch_connector_queue(
    connector_id: str,
    payload: schemas.ConnectorDispatchRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(ROLE_ADMIN, ROLE_ME_OFFICER)),
) -> schemas.ConnectorDispatchRunRead:
    connector = db.scalar(
        select(DataConnector)
        .options(selectinload(DataConnector.program))
        .where(DataConnector.id == connector_id)
    )
    if connector is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Connector not found")
    try:
        outcome = dispatch_risk_queue(db, connector, triggered_by=current_user, payload=payload)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    record_audit_event(
        db,
        actor=current_user,
        action="connector.dispatch_run",
        resource_type="connector_dispatch_run",
        resource_id=outcome.run.id,
        details={
            "connector_id": connector.id,
            "writeback_mode": connector.writeback_mode,
            "status": outcome.run.status,
            "cases_included": outcome.run.cases_included,
            "preview_only": payload.preview_only,
        },
        request=request,
    )
    return outcome.run


@app.get(f"{settings.api_prefix}/jobs", response_model=list[schemas.JobRead])
def get_jobs(
    request: Request,
    limit: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> list[schemas.JobRead]:
    jobs = list_jobs(db, limit=limit)
    record_audit_event(
        db,
        actor=current_user,
        action="job.list_viewed",
        resource_type="job",
        details={"count": len(jobs), "limit": limit},
        request=request,
    )
    return jobs


@app.get(f"{settings.api_prefix}/model/schedule", response_model=schemas.ModelScheduleRead)
def get_model_schedule(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> schemas.ModelScheduleRead:
    schedule = ensure_model_schedule(db)
    serialized = _serialize_model_schedule(schedule)
    record_audit_event(
        db,
        actor=current_user,
        action="model.schedule_viewed",
        resource_type="model_schedule",
        resource_id=schedule.id,
        details={"cadence": schedule.cadence, "enabled": schedule.enabled},
        request=request,
    )
    return serialized


@app.put(f"{settings.api_prefix}/model/schedule", response_model=schemas.ModelScheduleRead)
def put_model_schedule(
    payload: schemas.ModelScheduleUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(ROLE_ADMIN, ROLE_ME_OFFICER)),
) -> schemas.ModelScheduleRead:
    schedule = ensure_model_schedule(db)
    updated = update_model_schedule(
        db,
        schedule,
        cadence=payload.cadence,
        enabled=payload.enabled,
        auto_retrain_after_sync=payload.auto_retrain_after_sync,
    )
    serialized = _serialize_model_schedule(updated)
    record_audit_event(
        db,
        actor=current_user,
        action="model.schedule_updated",
        resource_type="model_schedule",
        resource_id=updated.id,
        details={"cadence": updated.cadence, "enabled": updated.enabled},
        request=request,
    )
    return serialized


@app.post(f"{settings.api_prefix}/automation/run-due", response_model=schemas.JobRead, status_code=status.HTTP_202_ACCEPTED)
def run_due_jobs(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(ROLE_ADMIN, ROLE_ME_OFFICER)),
) -> schemas.JobRead:
    job = enqueue_job(
        db,
        job_type=JOB_TYPE_AUTOMATION_RUN_DUE,
        payload={},
        created_by=current_user,
    )
    record_audit_event(
        db,
        actor=current_user,
        action="job.enqueued",
        resource_type="job",
        resource_id=job.job.id,
        details={
            "job_type": JOB_TYPE_AUTOMATION_RUN_DUE,
            "created": job.created,
        },
        request=request,
    )
    return _serialize_job_record(job.job)


@app.get(f"{settings.api_prefix}/program-settings", response_model=list[schemas.ProgramOperationalSettingRead])
def get_program_settings(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> list[schemas.ProgramOperationalSettingRead]:
    settings_rows = list_program_operational_settings(db)
    record_audit_event(
        db,
        actor=current_user,
        action="program_settings.viewed",
        resource_type="program_operational_setting",
        details={"count": len(settings_rows)},
        request=request,
    )
    return settings_rows


@app.put(f"{settings.api_prefix}/program-settings/{{program_id}}", response_model=schemas.ProgramOperationalSettingRead)
def put_program_setting(
    program_id: str,
    payload: schemas.ProgramOperationalSettingUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(ROLE_ADMIN, ROLE_ME_OFFICER)),
) -> schemas.ProgramOperationalSettingRead:
    try:
        setting = update_program_operational_setting(db, program_id, payload)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    record_audit_event(
        db,
        actor=current_user,
        action="program_settings.updated",
        resource_type="program_operational_setting",
        resource_id=setting.id,
        details={
            "program_id": program_id,
            "weekly_followup_capacity": setting.weekly_followup_capacity,
            "worker_count": setting.worker_count,
            "label_definition_preset": setting.label_definition_preset,
            "prediction_window_days": setting.prediction_window_days,
        },
        request=request,
    )
    return setting


@app.get(f"{settings.api_prefix}/program-validation", response_model=list[schemas.ProgramValidationSettingRead])
def get_program_validation_settings(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> list[schemas.ProgramValidationSettingRead]:
    settings_payload = list_program_validation_settings(db)
    record_audit_event(
        db,
        actor=current_user,
        action="program_validation.viewed",
        resource_type="program_validation_setting",
        details={"count": len(settings_payload)},
        request=request,
    )
    return settings_payload


@app.put(f"{settings.api_prefix}/program-validation/{{program_id}}", response_model=schemas.ProgramValidationSettingRead)
def put_program_validation_setting(
    program_id: str,
    payload: schemas.ProgramValidationSettingUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(ROLE_ADMIN, ROLE_ME_OFFICER)),
) -> schemas.ProgramValidationSettingRead:
    try:
        setting = update_program_validation_setting(db, program_id, payload)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    record_audit_event(
        db,
        actor=current_user,
        action="program_validation.updated",
        resource_type="program_validation_setting",
        resource_id=setting.id,
        details={
            "program_id": program_id,
            "shadow_mode_enabled": setting.shadow_mode_enabled,
            "shadow_prediction_window_days": setting.shadow_prediction_window_days,
        },
        request=request,
    )
    return setting


@app.get(f"{settings.api_prefix}/program-data-policies", response_model=list[schemas.ProgramDataPolicyRead])
def get_program_data_policies(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> list[schemas.ProgramDataPolicyRead]:
    policies = list_program_data_policies(db)
    record_audit_event(
        db,
        actor=current_user,
        action="program_data_policies.viewed",
        resource_type="program_data_policy",
        details={"count": len(policies)},
        request=request,
    )
    return policies


@app.put(f"{settings.api_prefix}/program-data-policies/{{program_id}}", response_model=schemas.ProgramDataPolicyRead)
def put_program_data_policy(
    program_id: str,
    payload: schemas.ProgramDataPolicyUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(ROLE_ADMIN, ROLE_ME_OFFICER)),
) -> schemas.ProgramDataPolicyRead:
    try:
        policy = update_program_data_policy(db, program_id, payload)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    record_audit_event(
        db,
        actor=current_user,
        action="program_data_policies.updated",
        resource_type="program_data_policy",
        resource_id=policy.id,
        details={"program_id": program_id, "storage_mode": policy.storage_mode, "residency": policy.data_residency_region},
        request=request,
    )
    return policy


@app.get(f"{settings.api_prefix}/dashboard/summary", response_model=schemas.DashboardSummary)
def get_dashboard_summary(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> schemas.DashboardSummary:
    risk_cases = build_risk_cases(db)
    summary = build_dashboard_summary(db, risk_cases)
    record_audit_event(
        db,
        actor=current_user,
        action="dashboard.summary_viewed",
        resource_type="dashboard",
        details={
            "high_risk_cases": summary.high_risk_cases,
            "predicted_30_day_dropout": summary.predicted_30_day_dropout,
        },
        request=request,
    )
    return summary


@app.get(f"{settings.api_prefix}/governance/alerts", response_model=list[schemas.GovernanceAlert])
def get_governance_alerts(
    request: Request,
    limit: int = Query(default=10, ge=1, le=50),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(ROLE_ADMIN, ROLE_ME_OFFICER, ROLE_COUNTRY_DIRECTOR)),
) -> list[schemas.GovernanceAlert]:
    alerts = build_misuse_alerts(db, limit=limit)
    record_audit_event(
        db,
        actor=current_user,
        action="governance.alerts_viewed",
        resource_type="governance_alert",
        details={"count": len(alerts), "limit": limit},
        request=request,
    )
    return alerts


@app.get(f"{settings.api_prefix}/model/status", response_model=schemas.ModelStatus)
def get_model_status(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> schemas.ModelStatus:
    model_status = build_model_status(db)
    record_audit_event(
        db,
        actor=current_user,
        action="model.status_viewed",
        resource_type="model_version",
        resource_id=model_status.id,
        details={"model_mode": model_status.model_mode, "algorithm": model_status.algorithm},
        request=request,
    )
    return model_status


@app.post(f"{settings.api_prefix}/model/evaluate/backtest", response_model=schemas.ModelEvaluationReport)
def evaluate_model_backtest_report(
    payload: schemas.EvaluationRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(ROLE_ADMIN, ROLE_ME_OFFICER, ROLE_COUNTRY_DIRECTOR)),
) -> schemas.ModelEvaluationReport:
    try:
        report = evaluate_model_backtest(db, payload)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    persisted_report = persist_evaluation_report(
        db,
        payload=payload,
        report=report,
        created_by=current_user,
    )
    record_audit_event(
        db,
        actor=current_user,
        action="model.backtest_evaluated",
        resource_type="model_evaluation",
        details={
            "evaluation_report_id": persisted_report.id,
            "status": report.status,
            "algorithm": report.algorithm,
            "horizon_days": report.horizon_days,
            "samples_evaluated": report.samples_evaluated,
        },
        request=request,
    )
    return report


@app.get(f"{settings.api_prefix}/model/evaluations", response_model=list[schemas.ModelEvaluationRecordRead])
def get_model_evaluations(
    request: Request,
    limit: int = Query(default=12, ge=1, le=100),
    program_id: str | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(ROLE_ADMIN, ROLE_ME_OFFICER, ROLE_COUNTRY_DIRECTOR)),
) -> list[schemas.ModelEvaluationRecordRead]:
    reports = list_evaluation_reports(db, limit=limit, program_id=program_id)
    record_audit_event(
        db,
        actor=current_user,
        action="model.evaluations_viewed",
        resource_type="model_evaluation",
        details={"count": len(reports), "program_id": program_id},
        request=request,
    )
    return reports


@app.get(f"{settings.api_prefix}/program-validation/shadow-runs", response_model=list[schemas.ShadowRunRead])
def get_shadow_runs(
    request: Request,
    limit: int = Query(default=12, ge=1, le=100),
    program_id: str | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(ROLE_ADMIN, ROLE_ME_OFFICER, ROLE_COUNTRY_DIRECTOR)),
) -> list[schemas.ShadowRunRead]:
    runs = list_shadow_runs(db, limit=limit, program_id=program_id)
    record_audit_event(
        db,
        actor=current_user,
        action="program_validation.shadow_runs_viewed",
        resource_type="shadow_run",
        details={"count": len(runs), "program_id": program_id},
        request=request,
    )
    return runs


@app.post(
    f"{settings.api_prefix}/program-validation/{{program_id}}/shadow-runs",
    response_model=schemas.ShadowRunRead,
)
def post_shadow_run(
    program_id: str,
    payload: schemas.ShadowRunCreateRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(ROLE_ADMIN, ROLE_ME_OFFICER)),
) -> schemas.ShadowRunRead:
    try:
        run = create_shadow_run(
            db,
            program_id=program_id,
            payload=payload,
            created_by=current_user,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    record_audit_event(
        db,
        actor=current_user,
        action="program_validation.shadow_run_created",
        resource_type="shadow_run",
        resource_id=run.id,
        details={
            "program_id": program_id,
            "status": run.status,
            "cases_captured": run.cases_captured,
            "top_k_count": run.top_k_count,
        },
        request=request,
    )
    return run


@app.get(f"{settings.api_prefix}/model/drift", response_model=schemas.ModelDriftReportRead)
def get_model_drift(
    request: Request,
    refresh: bool = Query(default=False),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> schemas.ModelDriftReportRead:
    if refresh:
        report = refresh_model_drift_report(db)
    else:
        report = build_model_status(db).drift_report or refresh_model_drift_report(db)
    record_audit_event(
        db,
        actor=current_user,
        action="model.drift_viewed",
        resource_type="model_drift_report",
        resource_id=report.id,
        details={"status": report.status, "overall_psi": report.overall_psi, "refresh": refresh},
        request=request,
    )
    return report


@app.get(f"{settings.api_prefix}/feature-store/summary", response_model=schemas.FeatureStoreSummary)
def get_feature_store_summary(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> schemas.FeatureStoreSummary:
    summary = build_feature_store_summary(db)
    record_audit_event(
        db,
        actor=current_user,
        action="feature_store.summary_viewed",
        resource_type="feature_store",
        details={"total_snapshots": summary.total_snapshots},
        request=request,
    )
    return summary


@app.get(f"{settings.api_prefix}/federated/status")
def get_federated_status(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> dict[str, object]:
    status_payload = build_federated_status(db)
    record_audit_event(
        db,
        actor=current_user,
        action="federated.status_viewed",
        resource_type="federated_learning",
        details={"rounds": len(status_payload.get("recent_rounds", []))},
        request=request,
    )
    return status_payload


@app.get(f"{settings.api_prefix}/federated/rounds", response_model=list[schemas.FederatedLearningRoundRead])
def get_federated_rounds(
    request: Request,
    limit: int = Query(default=10, ge=1, le=25),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> list[schemas.FederatedLearningRoundRead]:
    rounds = list_federated_rounds(db, limit=limit)
    record_audit_event(
        db,
        actor=current_user,
        action="federated.rounds_viewed",
        resource_type="federated_learning_round",
        details={"count": len(rounds)},
        request=request,
    )
    return rounds


@app.post(f"{settings.api_prefix}/federated/export-update", response_model=schemas.FederatedModelUpdateRead)
def post_federated_update(
    payload: schemas.FederatedUpdateRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(ROLE_ADMIN, ROLE_ME_OFFICER)),
) -> schemas.FederatedModelUpdateRead:
    update = export_federated_update(
        db,
        round_name=payload.round_name,
        deployment_label=payload.deployment_label,
        source_program_id=payload.source_program_id,
    )
    record_audit_event(
        db,
        actor=current_user,
        action="federated.update_exported",
        resource_type="federated_model_update",
        resource_id=update.id,
        details={"round_name": payload.round_name, "deployment_label": payload.deployment_label},
        request=request,
    )
    return update


@app.post(f"{settings.api_prefix}/federated/aggregate", response_model=schemas.FederatedLearningRoundRead)
def post_federated_aggregate(
    payload: schemas.FederatedAggregateRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(ROLE_ADMIN, ROLE_ME_OFFICER)),
) -> schemas.FederatedLearningRoundRead:
    try:
        round_record = aggregate_federated_round(db, payload.round_name, close_round=payload.close_round)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    record_audit_event(
        db,
        actor=current_user,
        action="federated.round_aggregated",
        resource_type="federated_learning_round",
        resource_id=round_record.id,
        details={"round_name": payload.round_name, "status": round_record.status},
        request=request,
    )
    return round_record


@app.post(
    f"{settings.api_prefix}/model/train",
    response_model=schemas.JobRead,
    status_code=status.HTTP_202_ACCEPTED,
)
def train_model(
    request: Request,
    payload: schemas.TrainingRequest | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(ROLE_ADMIN, ROLE_ME_OFFICER)),
) -> schemas.JobRead:
    force = payload.force if payload is not None else False
    job = enqueue_job(
        db,
        job_type=JOB_TYPE_MODEL_TRAIN,
        payload={"force": force},
        created_by=current_user,
    )
    record_audit_event(
        db,
        actor=current_user,
        action="job.enqueued",
        resource_type="job",
        resource_id=job.job.id,
        details={
            "job_type": JOB_TYPE_MODEL_TRAIN,
            "force": force,
            "created": job.created,
        },
        request=request,
    )
    return _serialize_job_record(job.job)


@app.post(
    f"{settings.api_prefix}/jobs/run-pending",
    response_model=schemas.JobRunSummary,
)
def execute_pending_jobs(
    request: Request,
    payload: schemas.JobRunRequest | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(ROLE_ADMIN, ROLE_ME_OFFICER)),
) -> schemas.JobRunSummary:
    max_jobs = payload.max_jobs if payload is not None else 10
    jobs = run_pending_jobs(db, max_jobs=max_jobs)
    serialized_jobs = [_serialize_job_record(job) for job in jobs]
    record_audit_event(
        db,
        actor=current_user,
        action="job.run_pending",
        resource_type="job",
        details={"requested": max_jobs, "processed": len(serialized_jobs)},
        request=request,
    )
    return schemas.JobRunSummary(requested=max_jobs, processed=len(serialized_jobs), jobs=serialized_jobs)


@app.post(f"{settings.api_prefix}/jobs/{{job_id}}/requeue", response_model=schemas.JobRead)
def requeue_existing_job(
    job_id: str,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(ROLE_ADMIN, ROLE_ME_OFFICER)),
) -> schemas.JobRead:
    try:
        job = requeue_job(db, job_id)
    except ValueError as exc:
        status_code = status.HTTP_404_NOT_FOUND if "not found" in str(exc).lower() else status.HTTP_400_BAD_REQUEST
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc
    record_audit_event(
        db,
        actor=current_user,
        action="job.requeued",
        resource_type="job",
        resource_id=job.id,
        details={"job_type": job.job_type},
        request=request,
    )
    return _serialize_job_record(job)


@app.get(f"{settings.api_prefix}/risk-cases", response_model=list[schemas.RiskCase])
def get_risk_cases(
    request: Request,
    program: str | None = Query(default=None),
    risk_level: Literal["High", "Medium", "Low"] | None = Query(default=None),
    region: str | None = Query(default=None),
    cohort: str | None = Query(default=None),
    phase: str | None = Query(default=None),
    search: str | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> list[schemas.RiskCase]:
    cases = filter_risk_cases(
        build_risk_cases(db),
        program=program,
        risk_level=risk_level,
        region=region,
        cohort=cohort,
        phase=phase,
        search=search,
    )

    record_audit_event(
        db,
        actor=current_user,
        action="risk_queue.viewed",
        resource_type="beneficiary_risk_queue",
        details={
            "count": len(cases),
            "program": program,
            "risk_level": risk_level,
            "region": region,
            "cohort": cohort,
            "phase": phase,
            "search": search,
        },
        request=request,
    )
    return cases


@app.get(f"{settings.api_prefix}/beneficiaries/{{beneficiary_id}}/explanation", response_model=schemas.BeneficiaryExplanationRead)
def get_beneficiary_explanation(
    beneficiary_id: str,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> schemas.BeneficiaryExplanationRead:
    beneficiary = db.scalar(
        select(Beneficiary)
        .options(
            selectinload(Beneficiary.program).selectinload(Program.data_policy),
            selectinload(Beneficiary.monitoring_events),
            selectinload(Beneficiary.interventions),
        )
        .where(Beneficiary.id == beneficiary_id)
    )
    if beneficiary is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Beneficiary not found")

    loaded_model = load_deployed_model(db)
    prediction, heuristic = score_beneficiary(beneficiary, loaded_model)
    explanation = schemas.BeneficiaryExplanationRead(
        beneficiary_id=beneficiary.id,
        beneficiary_label=beneficiary.full_name if current_user.role in {ROLE_ADMIN, ROLE_ME_OFFICER} else beneficiary.external_id,
        program_name=beneficiary.program.name,
        risk_level=prediction.risk_level,  # type: ignore[arg-type]
        explanation=prediction.explanation,
        beneficiary_facing_summary=(
            "RetainAI flagged this case because recent engagement signals suggest the beneficiary may need a supportive follow-up, not because the beneficiary did anything wrong."
        ),
        confidence=prediction.confidence,
        translated_ready_note="Use this explanation in local language and pair it with a human check-in before any action is taken.",
        data_points_used=[
            f"Last contact: {heuristic.last_contact_days} days",
            f"Attendance in 30 days: {heuristic.attendance_rate_30d}%",
            *prediction.flags[:3],
        ],
        support_recommendation=prediction.flags[0] if prediction.flags else "Schedule a supportive follow-up.",
    )
    record_audit_event(
        db,
        actor=current_user,
        action="beneficiary.explanation_viewed",
        resource_type="beneficiary",
        resource_id=beneficiary.id,
        details={"risk_level": prediction.risk_level},
        request=request,
    )
    return explanation


@app.get(f"{settings.api_prefix}/synthetic/portfolio", response_model=list[schemas.SyntheticProgramBundleSummary])
def get_synthetic_portfolio_summary(
    request: Request,
    rows_per_program: int = Query(default=180, ge=50, le=1000),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> list[schemas.SyntheticProgramBundleSummary]:
    summary = [schemas.SyntheticProgramBundleSummary(**item) for item in summarize_synthetic_portfolio(rows_per_program)]
    record_audit_event(
        db,
        actor=current_user,
        action="synthetic.portfolio_viewed",
        resource_type="synthetic_portfolio",
        details={"rows_per_program": rows_per_program},
        request=request,
    )
    return summary


@app.get(f"{settings.api_prefix}/synthetic/stress-scenarios", response_model=list[schemas.SyntheticStressScenarioRead])
def get_synthetic_stress_scenarios(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> list[schemas.SyntheticStressScenarioRead]:
    scenarios = [schemas.SyntheticStressScenarioRead(**item) for item in list_stress_scenarios()]
    record_audit_event(
        db,
        actor=current_user,
        action="synthetic.stress_scenarios_viewed",
        resource_type="synthetic_stress_suite",
        details={"scenario_count": len(scenarios)},
        request=request,
    )
    return scenarios


@app.get(f"{settings.api_prefix}/synthetic/stress-summary", response_model=list[schemas.SyntheticStressProgramSummary])
def get_synthetic_stress_summary(
    request: Request,
    rows_per_program: int = Query(default=180, ge=50, le=1000),
    seed: int = Query(default=42, ge=1, le=100000),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> list[schemas.SyntheticStressProgramSummary]:
    summary = [schemas.SyntheticStressProgramSummary(**item) for item in summarize_stress_suite(rows_per_program, seed)]
    record_audit_event(
        db,
        actor=current_user,
        action="synthetic.stress_summary_viewed",
        resource_type="synthetic_stress_suite",
        details={"rows_per_program": rows_per_program, "seed": seed, "rows_returned": len(summary)},
        request=request,
    )
    return summary


@app.get(f"{settings.api_prefix}/retention/curves", response_model=schemas.RetentionCurves)
def get_retention_curves(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> schemas.RetentionCurves:
    curves = build_retention_curves(db)
    record_audit_event(
        db,
        actor=current_user,
        action="retention_curve.viewed",
        resource_type="retention_curve",
        details={"series_count": len(curves.series)},
        request=request,
    )
    return curves


@app.get(f"{settings.api_prefix}/retention/analytics", response_model=schemas.RetentionAnalytics)
def get_retention_analytics(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> schemas.RetentionAnalytics:
    analytics = build_retention_analytics(db)
    record_audit_event(
        db,
        actor=current_user,
        action="retention.analytics_viewed",
        resource_type="retention_analytics",
        details={"breakdowns": len(analytics.breakdowns), "trend_rows": len(analytics.trend_rows)},
        request=request,
    )
    return analytics


@app.get(f"{settings.api_prefix}/interventions", response_model=list[schemas.InterventionRecord])
def get_interventions(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> list[schemas.InterventionRecord]:
    interventions = list_interventions(db)
    record_audit_event(
        db,
        actor=current_user,
        action="intervention.list_viewed",
        resource_type="intervention",
        details={"count": len(interventions)},
        request=request,
    )
    return interventions


@app.get(f"{settings.api_prefix}/interventions/effectiveness", response_model=schemas.InterventionEffectivenessSummary)
def get_intervention_effectiveness(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> schemas.InterventionEffectivenessSummary:
    summary = build_intervention_effectiveness_summary(db)
    record_audit_event(
        db,
        actor=current_user,
        action="intervention.effectiveness_viewed",
        resource_type="intervention_effectiveness",
        details={"rows": len(summary.rows), "labeled_outcomes": summary.outcome_labeled_interventions},
        request=request,
    )
    return summary


@app.get(f"{settings.api_prefix}/reports/donor-summary", response_model=schemas.DonorReportSummary)
def get_donor_report_summary(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> schemas.DonorReportSummary:
    summary = build_donor_report_summary(db)
    record_audit_event(
        db,
        actor=current_user,
        action="report.donor_summary_viewed",
        resource_type="donor_report",
        details={"generated_at": summary.generated_at},
        request=request,
    )
    return summary


@app.get(f"{settings.api_prefix}/reports/donor-summary.xlsx")
def export_donor_report_xlsx(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(ROLE_ADMIN, ROLE_ME_OFFICER, ROLE_COUNTRY_DIRECTOR)),
) -> Response:
    payload = build_donor_excel_report(db)
    record_audit_event(
        db,
        actor=current_user,
        action="export.generated",
        resource_type="donor_report_xlsx",
        details={"bytes": len(payload)},
        request=request,
    )
    return Response(
        content=payload,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="retainai-donor-summary.xlsx"'},
    )


@app.get(f"{settings.api_prefix}/reports/donor-summary.pdf")
def export_donor_report_pdf(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(ROLE_ADMIN, ROLE_ME_OFFICER, ROLE_COUNTRY_DIRECTOR)),
) -> Response:
    payload = build_donor_pdf_report(db)
    record_audit_event(
        db,
        actor=current_user,
        action="export.generated",
        resource_type="donor_report_pdf",
        details={"bytes": len(payload)},
        request=request,
    )
    return Response(
        content=payload,
        media_type="application/pdf",
        headers={"Content-Disposition": 'attachment; filename="retainai-donor-summary.pdf"'},
    )


@app.post(f"{settings.api_prefix}/exports/risk-cases")
def export_risk_cases(
    payload: schemas.ExportRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(ROLE_ADMIN, ROLE_ME_OFFICER, ROLE_COUNTRY_DIRECTOR)),
) -> Response:
    if payload.include_pii and current_user.role not in {ROLE_ADMIN, ROLE_ME_OFFICER}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="PII exports require admin or M&E officer access")

    export_programs = db.scalars(select(Program).options(selectinload(Program.data_policy))).all()
    _enforce_pii_export_policy(db, export_programs, payload.include_pii)
    risk_cases = build_risk_cases(db)
    csv_payload = build_csv_export(
        dataset="risk_cases",
        risk_cases=risk_cases,
        include_pii=payload.include_pii,
    )
    record_audit_event(
        db,
        actor=current_user,
        action="export.generated",
        resource_type="risk_case_export",
        details={
            "purpose": payload.purpose,
            "include_pii": payload.include_pii,
            "rows": len(risk_cases),
        },
        request=request,
    )
    return Response(
        content=csv_payload,
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="risk-cases.csv"'},
    )


@app.post(f"{settings.api_prefix}/exports/interventions")
def export_interventions(
    payload: schemas.ExportRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(ROLE_ADMIN, ROLE_ME_OFFICER, ROLE_COUNTRY_DIRECTOR)),
) -> Response:
    if payload.include_pii and current_user.role not in {ROLE_ADMIN, ROLE_ME_OFFICER}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="PII exports require admin or M&E officer access")

    export_programs = db.scalars(select(Program).options(selectinload(Program.data_policy))).all()
    _enforce_pii_export_policy(db, export_programs, payload.include_pii)
    interventions = list_interventions(db, limit=250)
    csv_payload = build_csv_export(
        dataset="interventions",
        interventions=interventions,
        include_pii=payload.include_pii,
    )
    record_audit_event(
        db,
        actor=current_user,
        action="export.generated",
        resource_type="intervention_export",
        details={
            "purpose": payload.purpose,
            "include_pii": payload.include_pii,
            "rows": len(interventions),
        },
        request=request,
    )
    return Response(
        content=csv_payload,
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="interventions.csv"'},
    )


def _export_follow_up_list(
    mode: Literal["whatsapp", "sms", "field_visit"],
    payload: schemas.RiskQueueExportRequest,
    request: Request,
    db: Session,
    current_user: User,
) -> Response:
    if payload.include_pii and current_user.role not in {ROLE_ADMIN, ROLE_ME_OFFICER}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="PII exports require admin or M&E officer access")

    program_name = None
    if payload.program_id:
        program = db.scalar(select(Program).options(selectinload(Program.data_policy)).where(Program.id == payload.program_id))
        program_name = program.name if program is not None else payload.program_id
        if program is not None:
            _enforce_pii_export_policy(db, [program], payload.include_pii)
    else:
        export_programs = db.scalars(select(Program).options(selectinload(Program.data_policy))).all()
        _enforce_pii_export_policy(db, export_programs, payload.include_pii)

    cases = filter_risk_cases(
        build_risk_cases(db),
        program=program_name,
        risk_level=payload.risk_level,
        region=payload.region,
        cohort=payload.cohort,
        phase=payload.phase,
        search=payload.search,
    )
    csv_payload = build_follow_up_export(db, cases=cases, mode=mode)
    record_audit_event(
        db,
        actor=current_user,
        action="export.generated",
        resource_type=f"{mode}_follow_up_export",
        details={
            "purpose": payload.purpose,
            "mode": mode,
            "rows": len(cases),
            "risk_level": payload.risk_level,
            "region": payload.region,
            "cohort": payload.cohort,
            "phase": payload.phase,
            "program_id": payload.program_id,
        },
        request=request,
    )
    filename = {
        "whatsapp": "whatsapp-follow-up-list.csv",
        "sms": "sms-follow-up-list.csv",
        "field_visit": "field-visit-schedule.csv",
    }[mode]
    return Response(
        content=csv_payload,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.post(f"{settings.api_prefix}/exports/followup/whatsapp")
def export_followup_whatsapp(
    payload: schemas.RiskQueueExportRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(ROLE_ADMIN, ROLE_ME_OFFICER, ROLE_COUNTRY_DIRECTOR)),
) -> Response:
    return _export_follow_up_list("whatsapp", payload, request, db, current_user)


@app.post(f"{settings.api_prefix}/exports/followup/sms")
def export_followup_sms(
    payload: schemas.RiskQueueExportRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(ROLE_ADMIN, ROLE_ME_OFFICER, ROLE_COUNTRY_DIRECTOR)),
) -> Response:
    return _export_follow_up_list("sms", payload, request, db, current_user)


@app.post(f"{settings.api_prefix}/exports/followup/field-visits")
def export_followup_field_visits(
    payload: schemas.RiskQueueExportRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(ROLE_ADMIN, ROLE_ME_OFFICER, ROLE_COUNTRY_DIRECTOR)),
) -> Response:
    return _export_follow_up_list("field_visit", payload, request, db, current_user)


@app.post(
    f"{settings.api_prefix}/interventions",
    response_model=schemas.InterventionRecord,
    status_code=status.HTTP_201_CREATED,
)
def create_intervention(
    payload: schemas.InterventionRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(ROLE_ADMIN, ROLE_ME_OFFICER, ROLE_FIELD_COORDINATOR)),
) -> schemas.InterventionRecord:
    beneficiary = db.get(Beneficiary, payload.beneficiary_id)
    if beneficiary is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Beneficiary not found")

    intervention = Intervention(
        beneficiary_id=beneficiary.id,
        action_type=payload.action_type,
        source=payload.source,
    )
    _apply_intervention_payload(intervention, beneficiary, payload)
    db.add(intervention)
    db.commit()

    statement = (
        select(Intervention)
        .options(selectinload(Intervention.beneficiary))
        .where(Intervention.id == intervention.id)
    )
    created = db.scalar(statement)
    assert created is not None

    record_audit_event(
        db,
        actor=current_user,
        action="intervention.created",
        resource_type="intervention",
        resource_id=created.id,
        details={
            "beneficiary_id": created.beneficiary_id,
            "action_type": created.action_type,
            "status": created.status,
            "verification_status": created.verification_status,
        },
        request=request,
    )
    return _serialize_intervention(created)


@app.patch(
    f"{settings.api_prefix}/interventions/{{intervention_id}}",
    response_model=schemas.InterventionRecord,
)
def update_intervention(
    intervention_id: str,
    payload: schemas.InterventionUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(ROLE_ADMIN, ROLE_ME_OFFICER, ROLE_FIELD_COORDINATOR)),
) -> schemas.InterventionRecord:
    statement = (
        select(Intervention)
        .options(selectinload(Intervention.beneficiary))
        .where(Intervention.id == intervention_id)
    )
    intervention = db.scalar(statement)
    if intervention is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Intervention not found")

    _apply_intervention_payload(intervention, intervention.beneficiary, payload)
    db.add(intervention)
    db.add(intervention.beneficiary)
    db.commit()
    db.refresh(intervention)

    record_audit_event(
        db,
        actor=current_user,
        action="intervention.updated",
        resource_type="intervention",
        resource_id=intervention.id,
        details={
            "beneficiary_id": intervention.beneficiary_id,
            "status": intervention.status,
            "verification_status": intervention.verification_status,
        },
        request=request,
    )
    return _serialize_intervention(intervention)


@app.get(f"{settings.api_prefix}/audit-logs", response_model=list[schemas.AuditLogRecord])
def get_audit_logs(
    request: Request,
    limit: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(ROLE_ADMIN, ROLE_ME_OFFICER, ROLE_COUNTRY_DIRECTOR)),
) -> list[schemas.AuditLogRecord]:
    logs = list(
        db.scalars(select(AuditLog).order_by(AuditLog.created_at.desc()).limit(limit)).all()
    )
    serialized_logs = [_serialize_audit_log(item) for item in logs]
    record_audit_event(
        db,
        actor=current_user,
        action="audit_log.viewed",
        resource_type="audit_log",
        details={"count": len(serialized_logs), "limit": limit},
        request=request,
    )
    return serialized_logs


@app.post(
    f"{settings.api_prefix}/connectors/{{connector_id}}/sync",
    response_model=schemas.JobRead,
    status_code=status.HTTP_202_ACCEPTED,
)
def sync_data_connector(
    connector_id: str,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(ROLE_ADMIN, ROLE_ME_OFFICER)),
) -> schemas.JobRead:
    connector = db.scalar(
        select(DataConnector)
        .options(selectinload(DataConnector.program))
        .where(DataConnector.id == connector_id)
    )
    if connector is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Connector not found")

    schedule = ensure_model_schedule(db)
    job = enqueue_job(
        db,
        job_type=JOB_TYPE_CONNECTOR_SYNC,
        payload={
            "connector_id": connector.id,
            "trigger_mode": "manual",
            "auto_retrain": schedule.auto_retrain_after_sync,
        },
        created_by=current_user,
    )
    record_audit_event(
        db,
        actor=current_user,
        action="job.enqueued",
        resource_type="job",
        resource_id=job.job.id,
        details={
            "job_type": JOB_TYPE_CONNECTOR_SYNC,
            "connector_id": connector.id,
            "created": job.created,
        },
        request=request,
    )
    return _serialize_job_record(job.job)
