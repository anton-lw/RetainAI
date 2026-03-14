"""Connector lifecycle, probing, sync, and write-back logic.

RetainAI connectors do more than read external records. They also support
previewing schema assumptions, maintaining sync state, and optionally writing
queue actions back into upstream systems. This file is therefore both an
ingestion adapter layer and an embedded-operations integration layer.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any
from urllib.parse import parse_qs, urljoin, urlparse

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app import schemas
from app.core.config import get_settings
from app.core.time import coerce_utc, utc_isoformat, utc_now, utc_timestamp_slug
from app.models import Beneficiary, ConnectorDispatchRun, ConnectorSyncRun, DataConnector, Intervention, ModelSchedule, ModelVersion, Program, User
from app.services.analytics import build_risk_cases, ensure_program_operational_setting
from app.services.automation import ensure_model_schedule, mark_model_schedule_run
from app.services.imports import (
    detect_mapping,
    import_beneficiaries,
    import_events,
    validate_mapping,
)
from app.services.labeling import build_operational_settings_profile, project_tracing_protocol
from app.services.modeling import build_model_status, train_and_deploy_model
from app.services.secrets import decrypt_secret, encrypt_secret, mask_secret


settings = get_settings()

CONNECTOR_LABELS: dict[str, str] = {
    "kobotoolbox": "KoboToolbox",
    "commcare": "CommCare",
    "odk_central": "ODK Central",
    "dhis2": "DHIS2",
    "salesforce_npsp": "Salesforce NPSP",
}

WRITEBACK_LABELS: dict[str, str] = {
    "none": "Disabled",
    "commcare_case_updates": "CommCare case updates",
    "dhis2_working_list": "DHIS2 working list",
    "generic_webhook": "Generic webhook",
}

@dataclass
class ConnectorProbe:
    http_status: int | None
    record_count: int
    pages_fetched: int
    sample_headers: list[str]
    inferred_mapping: dict[str, str | None]
    warnings: list[str]
    message: str


@dataclass
class ConnectorSyncOutcome:
    run: ConnectorSyncRun
    connector: DataConnector
    model_status: schemas.ModelStatus | None


@dataclass
class ConnectorDispatchOutcome:
    run: schemas.ConnectorDispatchRunRead
    connector: DataConnector


@dataclass(frozen=True)
class DispatchWorkflowProjection:
    protocol_step: str
    support_channel: str
    due_at: datetime
    workflow_status: str


@dataclass
class AutomationOutcome:
    connector_runs: list[ConnectorSyncRun]
    connector_failures: int
    model_retrained: bool
    model_status: schemas.ModelStatus | None


@dataclass(frozen=True)
class ConnectorProfile:
    default_record_paths: dict[str, str | None]
    next_page_paths: tuple[str, ...] = ()
    pagination_mode: str = "single_page"
    page_size_param: str | None = None
    page_param: str | None = None
    default_query_params: dict[str, str | int | float | bool | None] = field(default_factory=dict)
    supports_incremental_sync: bool = True


CONNECTOR_PROFILES: dict[str, ConnectorProfile] = {
    "kobotoolbox": ConnectorProfile(
        default_record_paths={"beneficiaries": "results", "events": "results"},
        next_page_paths=("next",),
        pagination_mode="next_url",
        page_size_param="limit",
    ),
    "commcare": ConnectorProfile(
        default_record_paths={"beneficiaries": "objects", "events": "objects"},
        next_page_paths=("meta.next", "next"),
        pagination_mode="next_url",
        page_size_param="limit",
    ),
    "odk_central": ConnectorProfile(
        default_record_paths={"beneficiaries": "value", "events": "value"},
        next_page_paths=("@odata.nextLink", "next"),
        pagination_mode="next_url",
        page_size_param="$top",
    ),
    "dhis2": ConnectorProfile(
        default_record_paths={"beneficiaries": "trackedEntityInstances", "events": "events"},
        next_page_paths=("pager.nextPage", "next"),
        pagination_mode="page_number",
        page_size_param="pageSize",
        page_param="page",
    ),
    "salesforce_npsp": ConnectorProfile(
        default_record_paths={"beneficiaries": "records", "events": "records"},
        next_page_paths=("nextRecordsUrl", "next"),
        pagination_mode="next_url",
    ),
}


def _validate_connector_type(connector_type: str) -> str:
    normalized = connector_type.strip().lower()
    if normalized not in CONNECTOR_LABELS:
        raise ValueError(f"Unsupported connector type: {connector_type}")
    return normalized


def _normalize_path(value: str) -> str:
    return value.strip().lstrip("/")


def compute_next_connector_sync(
    schedule_enabled: bool,
    sync_interval_hours: int | None,
    reference: datetime | None = None,
) -> datetime | None:
    if not schedule_enabled or not sync_interval_hours or sync_interval_hours <= 0:
        return None
    return (reference or utc_now()) + timedelta(hours=sync_interval_hours)


def _resolve_headers(connector: DataConnector) -> tuple[dict[str, str], httpx.BasicAuth | None]:
    secret = decrypt_secret(connector.encrypted_secret)
    headers: dict[str, str] = {}
    basic_auth = None

    if connector.auth_scheme == "bearer" and secret:
        headers["Authorization"] = f"Bearer {secret}"
    elif connector.auth_scheme == "token" and secret:
        headers["Authorization"] = f"Token {secret}"
    elif connector.auth_scheme == "basic" and connector.auth_username and secret:
        basic_auth = httpx.BasicAuth(connector.auth_username, secret)
    elif connector.auth_scheme not in {"none", "bearer", "token", "basic"}:
        raise ValueError(f"Unsupported auth scheme: {connector.auth_scheme}")

    return headers, basic_auth


def _build_connector_url(connector: DataConnector) -> str:
    base = connector.base_url.rstrip("/") + "/"
    return urljoin(base, _normalize_path(connector.resource_path))


def _webhook_endpoint(connector: DataConnector) -> str:
    base = settings.api_prefix.rstrip("/")
    return f"{base}/connectors/{connector.id}/webhook"


def _connector_profile(connector: DataConnector) -> ConnectorProfile:
    return CONNECTOR_PROFILES[connector.connector_type]


def _effective_record_path(connector: DataConnector) -> str | None:
    if connector.record_path:
        return connector.record_path
    return _connector_profile(connector).default_record_paths.get(connector.dataset_type)


def _extract_path_value(payload: Any, path: str | None) -> Any:
    if not path:
        return payload
    current = payload
    for segment in [item for item in path.split(".") if item]:
        if isinstance(current, dict):
            current = current.get(segment)
        else:
            return None
        if current is None:
            return None
    return current


def _flatten_record(value: Any, prefix: str = "") -> dict[str, str]:
    flattened: dict[str, str] = {}
    if isinstance(value, dict):
        for key, nested in value.items():
            nested_prefix = f"{prefix}.{key}" if prefix else str(key)
            flattened.update(_flatten_record(nested, nested_prefix))
        return flattened
    if isinstance(value, list):
        flattened[prefix] = ", ".join("" if item is None else str(item) for item in value)
        return flattened
    if isinstance(value, bool):
        flattened[prefix] = "true" if value else "false"
        return flattened
    flattened[prefix] = "" if value is None else str(value)
    return flattened


def _extract_json_records(payload: Any, record_path: str | None) -> list[dict[str, Any]]:
    current = _extract_path_value(payload, record_path)
    if current is payload and isinstance(payload, dict):
        for candidate in ("results", "data", "items", "objects", "value", "records", "events", "trackedEntityInstances"):
            if isinstance(payload.get(candidate), list):
                current = payload[candidate]
                break

    if isinstance(current, list):
        records = current
    elif isinstance(current, dict):
        records = [current]
    else:
        raise ValueError("Connector response did not contain a usable record list.")

    normalized_records: list[dict[str, Any]] = []
    for item in records:
        if isinstance(item, dict):
            normalized_records.append(item)
    if not normalized_records:
        raise ValueError("Connector response contained no object records.")
    return normalized_records


def _stringify_row(row: dict[str, Any]) -> dict[str, str]:
    normalized: dict[str, str] = {}
    for key, value in row.items():
        if value is None:
            normalized[str(key)] = ""
        elif isinstance(value, bool):
            normalized[str(key)] = "true" if value else "false"
        else:
            normalized[str(key)] = str(value)
    return normalized


def _resolve_query_params(
    connector: DataConnector,
    *,
    page_number: int,
    current_url: str,
) -> dict[str, str | int | float | bool]:
    profile = _connector_profile(connector)
    merged: dict[str, str | int | float | bool | None] = {
        **profile.default_query_params,
        **(connector.query_params or {}),
    }
    page_size = settings.connector_default_page_size
    if profile.page_size_param:
        raw_page_size = merged.get(profile.page_size_param)
        if isinstance(raw_page_size, (int, float)) and int(raw_page_size) > 0:
            page_size = int(raw_page_size)
        else:
            merged[profile.page_size_param] = page_size

    if profile.page_param and profile.pagination_mode == "page_number":
        merged[profile.page_param] = page_number

    last_synced = connector.last_synced_at.isoformat() + "Z" if connector.last_synced_at else None
    today_iso = utc_now().date().isoformat()
    yesterday_iso = (utc_now().date() - timedelta(days=1)).isoformat()
    resolved: dict[str, str | int | float | bool] = {}
    for key, value in merged.items():
        if value in (None, ""):
            continue
        if isinstance(value, str):
            if value == "$last_synced_at":
                if last_synced is None:
                    continue
                resolved[key] = last_synced
                continue
            if value == "$today":
                resolved[key] = today_iso
                continue
            if value == "$yesterday":
                resolved[key] = yesterday_iso
                continue
        resolved[key] = value

    if profile.pagination_mode == "next_url":
        parsed = urlparse(current_url)
        for key, values in parse_qs(parsed.query).items():
            if key not in resolved and values:
                resolved[key] = values[-1]
    return resolved


def _next_page_value(payload: Any, response: httpx.Response, connector: DataConnector) -> str | int | None:
    profile = _connector_profile(connector)
    for path in profile.next_page_paths:
        candidate = _extract_path_value(payload, path)
        if candidate not in (None, "", False):
            return candidate

    link_header = response.headers.get("link")
    if link_header:
        for part in link_header.split(","):
            if 'rel="next"' not in part:
                continue
            start = part.find("<")
            end = part.find(">", start + 1)
            if start >= 0 and end > start:
                return part[start + 1 : end]
    return None


def fetch_connector_rows(connector: DataConnector) -> tuple[list[dict[str, str]], ConnectorProbe]:
    """Fetch and normalize rows from one external connector configuration.

    This helper encapsulates pagination, auth, record-path extraction, and row
    flattening so that probe, preview, and sync flows can all share one fetch
    implementation.
    """
    headers, basic_auth = _resolve_headers(connector)
    base_url = _build_connector_url(connector)
    effective_record_path = _effective_record_path(connector)
    profile = _connector_profile(connector)
    warnings: list[str] = []
    rows: list[dict[str, str]] = []
    page_number = 1
    pages_fetched = 0
    current_url: str | None = base_url
    last_status_code: int | None = None

    with httpx.Client(timeout=settings.connector_request_timeout_seconds, follow_redirects=True) as client:
        while current_url and pages_fetched < settings.connector_max_pages:
            params = (
                None
                if profile.pagination_mode == "next_url" and current_url != base_url
                else _resolve_query_params(
                    connector,
                    page_number=page_number,
                    current_url=current_url,
                )
            )
            response = client.get(
                current_url,
                headers=headers,
                params=params or None,
                auth=basic_auth,
            )
            response.raise_for_status()
            last_status_code = response.status_code
            pages_fetched += 1

            content_type = response.headers.get("content-type", "").lower()
            if "csv" in content_type or current_url.lower().endswith(".csv"):
                from app.services.imports import parse_csv_bytes

                rows.extend(parse_csv_bytes(response.content))
                break

            payload = response.json()
            page_rows = [
                _stringify_row(_flatten_record(item))
                for item in _extract_json_records(payload, effective_record_path)
            ]
            rows.extend(page_rows)

            next_page = _next_page_value(payload, response, connector)
            if next_page is None:
                if profile.pagination_mode == "page_number" and profile.page_param and page_rows:
                    page_number += 1
                    page_size = (
                        int(params.get(profile.page_size_param, settings.connector_default_page_size))
                        if profile.page_size_param and params is not None
                        else settings.connector_default_page_size
                    )
                    if len(page_rows) < page_size:
                        current_url = None
                    else:
                        current_url = base_url
                else:
                    current_url = None
                continue

            if profile.pagination_mode == "page_number" and profile.page_param:
                try:
                    page_number = int(next_page)
                except (TypeError, ValueError):
                    current_url = urljoin(base_url, str(next_page))
                else:
                    current_url = base_url
                continue

            current_url = urljoin(base_url, str(next_page))

    if pages_fetched >= settings.connector_max_pages and current_url is not None:
        warnings.append(
            f"Connector pagination stopped after {settings.connector_max_pages} pages. Increase CONNECTOR_MAX_PAGES if this dataset is expected to be larger."
        )

    sample_headers = list(rows[0].keys())[:12] if rows else []
    inferred_mapping = detect_mapping(sample_headers, connector.dataset_type) if sample_headers else {}
    return rows, ConnectorProbe(
        http_status=last_status_code,
        record_count=len(rows),
        pages_fetched=pages_fetched,
        sample_headers=sample_headers,
        inferred_mapping=inferred_mapping,
        warnings=warnings,
        message=f"Fetched {len(rows)} records from {CONNECTOR_LABELS[connector.connector_type]} across {pages_fetched or 1} page(s).",
    )


def _sync_state_from_probe(probe: ConnectorProbe, connector: DataConnector) -> dict[str, str | int | float | bool | None]:
    previous = connector.sync_state or {}
    return {
        **previous,
        "last_probe_http_status": probe.http_status,
        "last_probe_record_count": probe.record_count,
        "last_probe_pages": probe.pages_fetched,
        "last_probe_at": utc_isoformat(),
    }


def _serialize_connector(connector: DataConnector) -> schemas.DataConnectorRead:
    return schemas.DataConnectorRead(
        id=connector.id,
        program_id=connector.program_id,
        program_name=connector.program.name,
        name=connector.name,
        connector_type=connector.connector_type,
        connector_label=CONNECTOR_LABELS.get(connector.connector_type, connector.connector_type),
        dataset_type=connector.dataset_type,
        status=connector.status,
        base_url=connector.base_url,
        resource_path=connector.resource_path,
        auth_scheme=connector.auth_scheme,
        auth_username=connector.auth_username,
        has_secret=bool(connector.encrypted_secret),
        masked_secret=mask_secret(decrypt_secret(connector.encrypted_secret)),
        record_path=connector.record_path,
        effective_record_path=_effective_record_path(connector),
        pagination_mode=_connector_profile(connector).pagination_mode,
        supports_incremental_sync=_connector_profile(connector).supports_incremental_sync,
        sync_state=connector.sync_state or {},
        query_params=connector.query_params,
        field_mapping=connector.field_mapping,
        schedule_enabled=connector.schedule_enabled,
        sync_interval_hours=connector.sync_interval_hours,
        writeback_enabled=connector.writeback_enabled,
        writeback_mode=connector.writeback_mode,
        writeback_resource_path=connector.writeback_resource_path,
        writeback_field_mapping=connector.writeback_field_mapping or {},
        webhook_enabled=connector.webhook_enabled,
        has_webhook_secret=bool(connector.encrypted_webhook_secret),
        masked_webhook_secret=mask_secret(decrypt_secret(connector.encrypted_webhook_secret)),
        webhook_endpoint=_webhook_endpoint(connector),
        last_webhook_at=connector.last_webhook_at,
        last_synced_at=connector.last_synced_at,
        last_dispatched_at=connector.last_dispatched_at,
        next_sync_at=connector.next_sync_at,
        last_error=connector.last_error,
        created_at=connector.created_at,
    )


def _serialize_sync_run(run: ConnectorSyncRun) -> schemas.ConnectorSyncRunRead:
    return schemas.ConnectorSyncRunRead(
        id=run.id,
        connector_id=run.connector_id,
        connector_name=run.connector.name,
        program_name=run.connector.program.name,
        trigger_mode=run.trigger_mode,
        status=run.status,
        records_fetched=run.records_fetched,
        records_processed=run.records_processed,
        records_failed=run.records_failed,
        warnings=run.warnings,
        model_retrained=run.model_retrained,
        started_at=run.started_at,
        completed_at=run.completed_at,
        triggered_by_email=run.triggered_by.email if run.triggered_by is not None else None,
        import_batch_id=run.import_batch_id,
    )


def _serialize_dispatch_run(run: ConnectorDispatchRun) -> schemas.ConnectorDispatchRunRead:
    return schemas.ConnectorDispatchRunRead(
        id=run.id,
        connector_id=run.connector_id,
        connector_name=run.connector.name,
        program_name=run.connector.program.name,
        status=run.status,
        target_mode=run.target_mode,
        records_sent=run.records_sent,
        cases_included=run.cases_included,
        cases_skipped=run.cases_skipped,
        warnings=run.warnings,
        payload_preview=run.payload_preview,
        started_at=run.started_at,
        completed_at=run.completed_at,
        triggered_by_email=run.triggered_by.email if run.triggered_by is not None else None,
    )


def list_connectors(db: Session) -> list[schemas.DataConnectorRead]:
    statement = (
        select(DataConnector)
        .options(selectinload(DataConnector.program))
        .order_by(DataConnector.created_at.desc())
    )
    return [_serialize_connector(item) for item in db.scalars(statement).all()]


def list_sync_runs(db: Session, limit: int = 20) -> list[schemas.ConnectorSyncRunRead]:
    statement = (
        select(ConnectorSyncRun)
        .options(
            selectinload(ConnectorSyncRun.connector).selectinload(DataConnector.program),
            selectinload(ConnectorSyncRun.triggered_by),
        )
        .order_by(ConnectorSyncRun.started_at.desc())
        .limit(limit)
    )
    return [_serialize_sync_run(item) for item in db.scalars(statement).all()]


def list_dispatch_runs(db: Session, limit: int = 20) -> list[schemas.ConnectorDispatchRunRead]:
    statement = (
        select(ConnectorDispatchRun)
        .options(
            selectinload(ConnectorDispatchRun.connector).selectinload(DataConnector.program),
            selectinload(ConnectorDispatchRun.triggered_by),
        )
        .order_by(ConnectorDispatchRun.started_at.desc())
        .limit(limit)
    )
    return [_serialize_dispatch_run(item) for item in db.scalars(statement).all()]


def _default_writeback_mapping(mode: str) -> dict[str, str | int | float | bool | None]:
    if mode == "commcare_case_updates":
        return {
            "external_id": "case_id",
            "risk_level": "retainai_risk_level",
            "risk_score": "retainai_risk_score",
            "queue_bucket": "retainai_queue_bucket",
            "queue_rank": "retainai_queue_rank",
            "assigned_worker": "retainai_assigned_worker",
            "assigned_site": "retainai_assigned_site",
            "due_at": "retainai_due_at",
            "workflow_status": "retainai_workflow_status",
            "protocol_step": "retainai_protocol_step",
            "next_channel": "retainai_next_channel",
        }
    if mode == "dhis2_working_list":
        return {
            "external_id": "trackedEntityInstance",
            "assigned_site": "orgUnit",
            "risk_level": "riskLevel",
            "risk_score": "riskScore",
            "queue_bucket": "queueBucket",
            "queue_rank": "queueRank",
            "due_at": "dueAt",
            "workflow_status": "status",
            "recommended_action": "action",
            "protocol_step": "protocolStep",
            "next_channel": "nextChannel",
        }
    return {}


def create_connector(db: Session, payload: schemas.DataConnectorCreate) -> schemas.DataConnectorRead:
    """Create and persist a connector definition for one program.

    Connector creation is more than storing a URL. It normalizes paths, applies
    default mapping and write-back assumptions, encrypts secrets, and makes the
    connector immediately usable by probe and sync flows.
    """
    program = db.get(Program, payload.program_id)
    if program is None:
        raise ValueError("Program not found")

    connector = DataConnector(
        program_id=program.id,
        name=payload.name.strip(),
        connector_type=_validate_connector_type(payload.connector_type),
        dataset_type=payload.dataset_type,
        status="ready",
        base_url=payload.base_url.strip(),
        resource_path=_normalize_path(payload.resource_path),
        auth_scheme=payload.auth_scheme,
        auth_username=payload.auth_username,
        encrypted_secret=encrypt_secret(payload.secret),
        record_path=payload.record_path.strip() if payload.record_path else None,
        query_params=payload.query_params,
        field_mapping=payload.field_mapping,
        sync_state={},
        schedule_enabled=payload.schedule_enabled,
        sync_interval_hours=payload.sync_interval_hours,
        writeback_enabled=payload.writeback_enabled,
        writeback_mode=payload.writeback_mode,
        writeback_resource_path=payload.writeback_resource_path.strip() if payload.writeback_resource_path else None,
        writeback_field_mapping=payload.writeback_field_mapping or _default_writeback_mapping(payload.writeback_mode),
        webhook_enabled=payload.webhook_enabled,
        encrypted_webhook_secret=encrypt_secret(payload.webhook_secret),
        next_sync_at=compute_next_connector_sync(payload.schedule_enabled, payload.sync_interval_hours),
    )
    db.add(connector)
    db.commit()

    hydrated = db.scalar(
        select(DataConnector)
        .options(selectinload(DataConnector.program))
        .where(DataConnector.id == connector.id)
    )
    assert hydrated is not None
    return _serialize_connector(hydrated)


def update_connector(
    db: Session,
    connector: DataConnector,
    payload: schemas.DataConnectorUpdate,
) -> schemas.DataConnectorRead:
    if payload.name is not None:
        connector.name = payload.name.strip()
    if payload.connector_type is not None:
        connector.connector_type = _validate_connector_type(payload.connector_type)
    if payload.dataset_type is not None:
        connector.dataset_type = payload.dataset_type
    if payload.base_url is not None:
        connector.base_url = payload.base_url.strip()
    if payload.resource_path is not None:
        connector.resource_path = _normalize_path(payload.resource_path)
    if payload.auth_scheme is not None:
        connector.auth_scheme = payload.auth_scheme
    if payload.auth_username is not None:
        connector.auth_username = payload.auth_username
    if payload.secret is not None:
        connector.encrypted_secret = encrypt_secret(payload.secret)
    if payload.record_path is not None:
        connector.record_path = payload.record_path.strip() or None
    if payload.query_params is not None:
        connector.query_params = payload.query_params
    if payload.field_mapping is not None:
        connector.field_mapping = payload.field_mapping
    if payload.webhook_enabled is not None:
        connector.webhook_enabled = payload.webhook_enabled
    if payload.webhook_secret is not None:
        connector.encrypted_webhook_secret = encrypt_secret(payload.webhook_secret)
    if payload.schedule_enabled is not None:
        connector.schedule_enabled = payload.schedule_enabled
    if payload.sync_interval_hours is not None:
        connector.sync_interval_hours = payload.sync_interval_hours
    if payload.writeback_enabled is not None:
        connector.writeback_enabled = payload.writeback_enabled
    if payload.writeback_mode is not None:
        connector.writeback_mode = payload.writeback_mode
        if not connector.writeback_field_mapping:
            connector.writeback_field_mapping = _default_writeback_mapping(payload.writeback_mode)
    if payload.writeback_resource_path is not None:
        connector.writeback_resource_path = payload.writeback_resource_path.strip() or None
    if payload.writeback_field_mapping is not None:
        connector.writeback_field_mapping = payload.writeback_field_mapping

    connector.next_sync_at = compute_next_connector_sync(connector.schedule_enabled, connector.sync_interval_hours)
    connector.status = "ready"
    connector.last_error = None
    db.add(connector)
    db.commit()
    db.refresh(connector)

    hydrated = db.scalar(
        select(DataConnector)
        .options(selectinload(DataConnector.program))
        .where(DataConnector.id == connector.id)
    )
    assert hydrated is not None
    return _serialize_connector(hydrated)


def probe_connector(connector: DataConnector) -> schemas.ConnectorProbeResult:
    """Return a non-mutating diagnostic preview of a connector configuration.

    Probes are intentionally safe: they fetch and inspect upstream data without
    changing workflow state or importing records. They exist to help operators
    validate assumptions before a real sync.
    """
    rows, probe = fetch_connector_rows(connector)
    return schemas.ConnectorProbeResult(
        success=True,
        http_status=probe.http_status,
        record_count=len(rows),
        pages_fetched=probe.pages_fetched,
        sample_headers=probe.sample_headers,
        inferred_mapping=probe.inferred_mapping,
        warnings=probe.warnings,
        message=probe.message,
    )


def build_preview_connector(program: Program, payload: schemas.DataConnectorCreate) -> DataConnector:
    return DataConnector(
        program_id=program.id,
        name=payload.name.strip(),
        connector_type=_validate_connector_type(payload.connector_type),
        dataset_type=payload.dataset_type,
        status="draft",
        base_url=payload.base_url.strip(),
        resource_path=_normalize_path(payload.resource_path),
        auth_scheme=payload.auth_scheme,
        auth_username=payload.auth_username,
        encrypted_secret=encrypt_secret(payload.secret),
        record_path=payload.record_path.strip() if payload.record_path else None,
        query_params=payload.query_params,
        field_mapping=payload.field_mapping,
        sync_state={},
        schedule_enabled=payload.schedule_enabled,
        sync_interval_hours=payload.sync_interval_hours,
        writeback_enabled=payload.writeback_enabled,
        writeback_mode=payload.writeback_mode,
        writeback_resource_path=payload.writeback_resource_path.strip() if payload.writeback_resource_path else None,
        writeback_field_mapping=payload.writeback_field_mapping or _default_writeback_mapping(payload.writeback_mode),
        webhook_enabled=payload.webhook_enabled,
        encrypted_webhook_secret=encrypt_secret(payload.webhook_secret),
    )


def run_connector_sync(
    db: Session,
    connector: DataConnector,
    *,
    triggered_by: User | None,
    trigger_mode: str,
    auto_retrain: bool,
) -> ConnectorSyncOutcome:
    """Execute a connector sync and optionally trigger downstream automation.

    A sync run can import beneficiaries or events, update connector sync state,
    record an auditable run history, and optionally kick off retraining when the
    deployment is configured to do so.
    """
    run = ConnectorSyncRun(
        connector_id=connector.id,
        triggered_by_user_id=triggered_by.id if triggered_by is not None else None,
        trigger_mode=trigger_mode,
        status="running",
    )
    db.add(run)
    db.commit()
    db.refresh(run)

    model_status: schemas.ModelStatus | None = None

    try:
        rows, probe = fetch_connector_rows(connector)
        run.records_fetched = len(rows)
        connector.sync_state = _sync_state_from_probe(probe, connector)

        if not rows:
            raise ValueError("Connector returned no records.")

        mapping = connector.field_mapping or detect_mapping(list(rows[0].keys()), connector.dataset_type)  # type: ignore[arg-type]
        missing_fields = validate_mapping(mapping, connector.dataset_type)  # type: ignore[arg-type]
        if missing_fields:
            raise ValueError(f"Missing required connector fields: {', '.join(sorted(missing_fields))}")

        if connector.dataset_type == "beneficiaries":
            batch = import_beneficiaries(
                db,
                connector.program,
                rows,
                mapping,
                f"{connector.name}-{utc_timestamp_slug()}.json",
            )
        else:
            batch = import_events(
                db,
                connector.program,
                rows,
                mapping,
                f"{connector.name}-{utc_timestamp_slug()}.json",
            )

        connector.status = "ready"
        connector.last_error = None
        connector.last_synced_at = utc_now()
        connector.sync_state = {
            **(connector.sync_state or {}),
            "last_sync_status": "succeeded",
            "last_sync_at": connector.last_synced_at.isoformat() + "Z",
            "last_sync_records_processed": batch.records_processed,
        }
        connector.next_sync_at = compute_next_connector_sync(
            connector.schedule_enabled,
            connector.sync_interval_hours,
            connector.last_synced_at,
        )
        run.status = "succeeded"
        run.import_batch_id = batch.id
        run.records_processed = batch.records_processed
        run.records_failed = batch.records_failed
        run.warnings = batch.warning_preview
        run.log_excerpt = probe.message

        if auto_retrain:
            schedule = ensure_model_schedule(db)
            try:
                version = train_and_deploy_model(db, force=True)
            except ValueError as exc:
                run.warnings = [*run.warnings, str(exc)]
            else:
                run.model_retrained = True
                run.model_version_id = version.id
                model_status = build_model_status(db, version)
                mark_model_schedule_run(db, schedule)
        db.add(connector)
    except Exception as exc:
        connector.status = "error"
        connector.last_error = str(exc)
        connector.sync_state = {
            **(connector.sync_state or {}),
            "last_sync_status": "failed",
            "last_sync_error": str(exc),
            "last_sync_at": utc_isoformat(),
        }
        run.status = "failed"
        run.completed_at = utc_now()
        run.log_excerpt = str(exc)
        db.add(connector)
        db.add(run)
        db.commit()
        db.refresh(run)
        hydrated_run = db.scalar(
            select(ConnectorSyncRun)
            .options(
                selectinload(ConnectorSyncRun.connector).selectinload(DataConnector.program),
                selectinload(ConnectorSyncRun.triggered_by),
            )
            .where(ConnectorSyncRun.id == run.id)
        )
        assert hydrated_run is not None
        return ConnectorSyncOutcome(run=hydrated_run, connector=connector, model_status=None)

    run.completed_at = utc_now()
    db.add(run)
    db.add(connector)
    db.commit()

    hydrated_run = db.scalar(
        select(ConnectorSyncRun)
        .options(
            selectinload(ConnectorSyncRun.connector).selectinload(DataConnector.program),
            selectinload(ConnectorSyncRun.triggered_by),
        )
        .where(ConnectorSyncRun.id == run.id)
    )
    hydrated_connector = db.scalar(
        select(DataConnector)
        .options(selectinload(DataConnector.program))
        .where(DataConnector.id == connector.id)
    )
    assert hydrated_run is not None
    assert hydrated_connector is not None
    return ConnectorSyncOutcome(run=hydrated_run, connector=hydrated_connector, model_status=model_status)


def _connector_dispatch_url(connector: DataConnector) -> str:
    resource_path = connector.writeback_resource_path or connector.resource_path
    base = connector.base_url.rstrip("/") + "/"
    return urljoin(base, _normalize_path(resource_path))


def _project_dispatch_workflow(case: schemas.RiskCase, setting: Any) -> DispatchWorkflowProjection:
    profile = build_operational_settings_profile(case.program_type, setting)
    projected = project_tracing_protocol(
        risk_level=case.risk_level,
        profile=profile,
        workflow=case.workflow,
        reference_time=utc_now(),
    )
    workflow_status = case.workflow.status if case.workflow and case.workflow.status else "queued"
    if workflow_status in {"dismissed", "closed"}:
        workflow_status = "queued"
    elif workflow_status in {"attempted", "reached", "escalated"} and projected.current_step == "visit":
        workflow_status = "escalated"
    return DispatchWorkflowProjection(
        protocol_step=projected.current_step,
        support_channel=projected.current_channel,
        due_at=coerce_utc(projected.current_due_at),
        workflow_status=workflow_status,
    )


def _build_dispatch_case_rows(
    db: Session,
    connector: DataConnector,
    payload: schemas.ConnectorDispatchRequest,
) -> tuple[list[schemas.RiskCase], list[schemas.RiskCase]]:
    cases = build_risk_cases(db)
    connector_beneficiary_ids = {
        beneficiary_id
        for beneficiary_id, in db.execute(
            select(Beneficiary.id).where(Beneficiary.program_id == connector.program_id)
        ).all()
    }
    scoped_cases = [case for case in cases if case.id in connector_beneficiary_ids]
    included: list[schemas.RiskCase] = []
    skipped: list[schemas.RiskCase] = []

    for case in scoped_cases:
        if payload.only_due and case.queue_bucket == "Monitor":
            skipped.append(case)
            continue
        if not payload.include_this_week and case.queue_bucket == "This week":
            skipped.append(case)
            continue
        included.append(case)
        if len(included) >= payload.limit:
            skipped.extend(scoped_cases[len(included):])
            break
    return included, skipped


def _ensure_dispatch_workflow(
    db: Session,
    case: schemas.RiskCase,
    connector: DataConnector,
    setting: Any,
) -> Intervention:
    statement = (
        select(Intervention)
        .where(Intervention.beneficiary_id == case.id)
        .order_by(Intervention.logged_at.desc())
    )
    existing = db.scalars(statement).first()
    projection = _project_dispatch_workflow(case, setting)

    if existing is None or existing.status in {"dismissed", "closed"}:
        intervention = Intervention(
            beneficiary_id=case.id,
            action_type=case.recommended_action[:120],
            protocol_step=projection.protocol_step,
            support_channel=projection.support_channel,
            status=projection.workflow_status,
            verification_status="pending",
            assigned_to=case.assigned_worker,
            assigned_site=case.assigned_site,
            due_at=projection.due_at,
            source=f"embedded_dispatch:{connector.writeback_mode}",
            risk_level=case.risk_level,
            priority_rank=case.queue_rank,
            note=f"Dispatched to {WRITEBACK_LABELS.get(connector.writeback_mode, connector.writeback_mode)}.",
        )
        db.add(intervention)
        return intervention

    existing.protocol_step = projection.protocol_step
    existing.support_channel = projection.support_channel
    existing.assigned_to = case.assigned_worker
    existing.assigned_site = case.assigned_site
    existing.due_at = projection.due_at
    existing.priority_rank = case.queue_rank
    if projection.workflow_status != existing.status:
        existing.status = projection.workflow_status
    db.add(existing)
    return existing


def _commcare_dispatch_payload(
    connector: DataConnector,
    cases: list[schemas.RiskCase],
    setting: Any,
) -> dict[str, object]:
    mapping = connector.writeback_field_mapping or _default_writeback_mapping("commcare_case_updates")
    case_updates: list[dict[str, object]] = []
    for case in cases:
        projection = _project_dispatch_workflow(case, setting)
        properties = {
            str(mapping.get("risk_level", "retainai_risk_level")): case.risk_level,
            str(mapping.get("risk_score", "retainai_risk_score")): case.risk_score,
            str(mapping.get("queue_bucket", "retainai_queue_bucket")): case.queue_bucket,
            str(mapping.get("queue_rank", "retainai_queue_rank")): case.queue_rank,
            str(mapping.get("assigned_worker", "retainai_assigned_worker")): case.assigned_worker or "",
            str(mapping.get("assigned_site", "retainai_assigned_site")): case.assigned_site or "",
            str(mapping.get("due_at", "retainai_due_at")): projection.due_at.isoformat() + "Z",
            str(mapping.get("workflow_status", "retainai_workflow_status")): projection.workflow_status,
            str(mapping.get("protocol_step", "retainai_protocol_step")): projection.protocol_step,
            str(mapping.get("next_channel", "retainai_next_channel")): projection.support_channel,
        }
        case_updates.append(
            {
                str(mapping.get("external_id", "case_id")): case.id,
                "properties": properties,
                "task": {
                    "title": case.recommended_action,
                    "description": case.explanation,
                    "due_at": projection.due_at.isoformat() + "Z",
                    "assigned_to": case.assigned_worker,
                    "assigned_site": case.assigned_site,
                    "protocol_step": projection.protocol_step,
                    "channel": projection.support_channel,
                },
            }
        )
    return {
        "mode": "commcare_case_updates",
        "generated_at": utc_isoformat(),
        "connector_id": connector.id,
        "program_id": connector.program_id,
        "cases": case_updates,
    }


def _dhis2_dispatch_payload(
    connector: DataConnector,
    cases: list[schemas.RiskCase],
    setting: Any,
) -> dict[str, object]:
    mapping = connector.writeback_field_mapping or _default_writeback_mapping("dhis2_working_list")
    items: list[dict[str, object]] = []
    for case in cases:
        projection = _project_dispatch_workflow(case, setting)
        items.append(
            {
                str(mapping.get("external_id", "trackedEntityInstance")): case.id,
                str(mapping.get("assigned_site", "orgUnit")): case.assigned_site or case.region,
                str(mapping.get("risk_level", "riskLevel")): case.risk_level,
                str(mapping.get("risk_score", "riskScore")): case.risk_score,
                str(mapping.get("queue_bucket", "queueBucket")): case.queue_bucket,
                str(mapping.get("queue_rank", "queueRank")): case.queue_rank,
                str(mapping.get("due_at", "dueAt")): projection.due_at.isoformat() + "Z",
                str(mapping.get("workflow_status", "status")): projection.workflow_status,
                str(mapping.get("recommended_action", "action")): case.recommended_action,
                str(mapping.get("protocol_step", "protocolStep")): projection.protocol_step,
                str(mapping.get("next_channel", "nextChannel")): projection.support_channel,
                "comment": case.explanation,
                "flags": case.flags,
            }
        )
    return {
        "mode": "dhis2_working_list",
        "generated_at": utc_isoformat(),
        "connector_id": connector.id,
        "program_id": connector.program_id,
        "items": items,
    }


def _generic_dispatch_payload(
    connector: DataConnector,
    cases: list[schemas.RiskCase],
    setting: Any,
) -> dict[str, object]:
    items: list[dict[str, object]] = []
    for case in cases:
        projection = _project_dispatch_workflow(case, setting)
        items.append(
            {
                "beneficiary_id": case.id,
                "beneficiary_name": case.name,
                "risk_level": case.risk_level,
                "risk_score": case.risk_score,
                "program": case.program,
                "region": case.region,
                "assigned_worker": case.assigned_worker,
                "assigned_site": case.assigned_site,
                "queue_bucket": case.queue_bucket,
                "queue_rank": case.queue_rank,
                "due_at": projection.due_at.isoformat() + "Z",
                "protocol_step": projection.protocol_step,
                "next_channel": projection.support_channel,
                "workflow_status": projection.workflow_status,
                "recommended_action": case.recommended_action,
                "explanation": case.explanation,
            }
        )
    return {
        "mode": "generic_webhook",
        "generated_at": utc_isoformat(),
        "connector_id": connector.id,
        "program_id": connector.program_id,
        "items": items,
    }


def _build_dispatch_payload(
    connector: DataConnector,
    cases: list[schemas.RiskCase],
    setting: Any,
) -> dict[str, object]:
    if connector.writeback_mode == "commcare_case_updates":
        return _commcare_dispatch_payload(connector, cases, setting)
    if connector.writeback_mode == "dhis2_working_list":
        return _dhis2_dispatch_payload(connector, cases, setting)
    return _generic_dispatch_payload(connector, cases, setting)


def dispatch_risk_queue(
    db: Session,
    connector: DataConnector,
    *,
    triggered_by: User | None,
    payload: schemas.ConnectorDispatchRequest,
) -> ConnectorDispatchOutcome:
    """Push a filtered risk queue back into an upstream operational system.

    This is the backend side of the embedded-operations strategy. Instead of
    forcing staff to work only in the RetainAI dashboard, the queue can be
    written back into systems such as CommCare or DHIS2 as structured tasks or
    working-list entries.
    """
    if not connector.writeback_enabled or connector.writeback_mode == "none":
        raise ValueError("Connector write-back is not enabled for this connector.")

    setting = ensure_program_operational_setting(db, connector.program)
    cases, skipped_cases = _build_dispatch_case_rows(db, connector, payload)
    warnings: list[str] = []
    if not cases:
        warnings.append("No queue items matched the requested dispatch scope.")

    dispatch_payload = _build_dispatch_payload(connector, cases, setting)

    run = ConnectorDispatchRun(
        connector_id=connector.id,
        triggered_by_user_id=triggered_by.id if triggered_by is not None else None,
        status="preview" if payload.preview_only else "running",
        target_mode=connector.writeback_mode,
        payload_preview=dispatch_payload,
        cases_included=len(cases),
        cases_skipped=len(skipped_cases),
        warnings=warnings,
    )
    db.add(run)
    db.commit()
    db.refresh(run)

    if payload.preview_only:
        run.completed_at = utc_now()
        db.add(run)
        db.commit()
    else:
        for case in cases:
            _ensure_dispatch_workflow(db, case, connector, setting)
        db.commit()
        headers, basic_auth = _resolve_headers(connector)
        endpoint = _connector_dispatch_url(connector)
        try:
            with httpx.Client(timeout=settings.connector_request_timeout_seconds, follow_redirects=True) as client:
                response = client.post(endpoint, headers=headers, json=dispatch_payload, auth=basic_auth)
                response.raise_for_status()
            connector.last_dispatched_at = utc_now()
            run.records_sent = len(cases)
            run.status = "succeeded"
            run.completed_at = utc_now()
            run.log_excerpt = f"Dispatched {len(cases)} queue items to {WRITEBACK_LABELS.get(connector.writeback_mode, connector.writeback_mode)}."
            db.add(connector)
            db.add(run)
            db.commit()
        except Exception as exc:
            run.status = "failed"
            run.completed_at = utc_now()
            run.log_excerpt = str(exc)
            run.warnings = [*run.warnings, str(exc)]
            db.add(run)
            db.commit()

    hydrated_run = db.scalar(
        select(ConnectorDispatchRun)
        .options(
            selectinload(ConnectorDispatchRun.connector).selectinload(DataConnector.program),
            selectinload(ConnectorDispatchRun.triggered_by),
        )
        .where(ConnectorDispatchRun.id == run.id)
    )
    hydrated_connector = db.scalar(
        select(DataConnector)
        .options(selectinload(DataConnector.program))
        .where(DataConnector.id == connector.id)
    )
    assert hydrated_run is not None
    assert hydrated_connector is not None
    return ConnectorDispatchOutcome(run=_serialize_dispatch_run(hydrated_run), connector=hydrated_connector)


def run_due_automation(db: Session) -> AutomationOutcome:
    """Execute any connector syncs or model runs that are currently due.

    This function is the orchestration entrypoint used by job workers or manual
    operator triggers when the system needs to process all time-based automation
    that should have fired by now.
    """
    now = utc_now()
    due_connectors = list(
        db.scalars(
            select(DataConnector)
            .options(selectinload(DataConnector.program))
            .where(
                DataConnector.schedule_enabled.is_(True),
                DataConnector.next_sync_at.is_not(None),
                DataConnector.next_sync_at <= now,
            )
            .order_by(DataConnector.next_sync_at.asc())
        ).all()
    )
    schedule = ensure_model_schedule(db)
    runs: list[ConnectorSyncRun] = []
    failures = 0

    for connector in due_connectors:
        outcome = run_connector_sync(
            db,
            connector,
            triggered_by=None,
            trigger_mode="scheduled",
            auto_retrain=False,
        )
        runs.append(outcome.run)
        if outcome.run.status != "succeeded":
            failures += 1

    model_status: schemas.ModelStatus | None = None
    model_retrained = False

    should_retrain_after_sync = bool(runs) and schedule.auto_retrain_after_sync
    schedule_due = bool(schedule.enabled and schedule.next_run_at and schedule.next_run_at <= now)

    if should_retrain_after_sync or schedule_due:
        try:
            version = train_and_deploy_model(db, force=True)
        except ValueError:
            model_status = build_model_status(db)
        else:
            model_retrained = True
            model_status = build_model_status(db, version)
            mark_model_schedule_run(db, schedule)

    return AutomationOutcome(
        connector_runs=runs,
        connector_failures=failures,
        model_retrained=model_retrained,
        model_status=model_status,
    )


def serialize_connector(connector: DataConnector) -> schemas.DataConnectorRead:
    return _serialize_connector(connector)


def serialize_sync_run(run: ConnectorSyncRun) -> schemas.ConnectorSyncRunRead:
    return _serialize_sync_run(run)
