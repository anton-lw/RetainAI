from __future__ import annotations

from datetime import date, datetime, timedelta
from io import BytesIO

from fastapi.testclient import TestClient
from jose import jwt
from openpyxl import Workbook
from app.core.config import get_settings
from app.core.time import utc_now


def test_auth_me_returns_seeded_admin(client: TestClient, admin_headers: dict[str, str]) -> None:
    response = client.get("/api/v1/auth/me", headers=admin_headers)

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["email"] == "admin@retainai.local"
    assert payload["role"] == "admin"
    assert payload["is_active"] is True


def test_auth_logout_revokes_session_and_security_headers(client: TestClient, admin_headers: dict[str, str]) -> None:
    current = client.get("/api/v1/auth/me", headers=admin_headers)
    assert current.status_code == 200, current.text
    assert current.headers["x-content-type-options"] == "nosniff"
    assert current.headers["x-frame-options"] == "DENY"
    assert current.headers["referrer-policy"] == "no-referrer"

    sessions = client.get("/api/v1/auth/sessions", headers=admin_headers)
    assert sessions.status_code == 200, sessions.text
    assert sessions.json()

    logout = client.post("/api/v1/auth/logout", headers=admin_headers)
    assert logout.status_code == 200, logout.text
    assert logout.json()["status"] == "revoked"

    revoked = client.get("/api/v1/auth/me", headers=admin_headers)
    assert revoked.status_code == 401, revoked.text


def test_login_rate_limit_blocks_repeated_failures(client: TestClient, monkeypatch) -> None:
    settings = get_settings()
    monkeypatch.setattr(settings, "login_rate_limit_attempts", 2, raising=False)
    monkeypatch.setattr(settings, "login_rate_limit_window_minutes", 15, raising=False)

    for _ in range(2):
        failed = client.post(
            "/api/v1/auth/login",
            json={"email": "admin@retainai.local", "password": "wrong-password"},
        )
        assert failed.status_code == 401, failed.text

    blocked = client.post(
        "/api/v1/auth/login",
        json={"email": "admin@retainai.local", "password": "wrong-password"},
    )
    assert blocked.status_code == 429, blocked.text


def test_legacy_jwt_key_is_accepted_for_active_session(
    client: TestClient,
    admin_headers: dict[str, str],
    monkeypatch,
) -> None:
    from app.db import SessionLocal
    from app.models import UserSession

    settings = get_settings()
    original_key = settings.resolved_jwt_secret_key
    monkeypatch.setattr(settings, "jwt_secret_key", "rotated-primary-secret", raising=False)
    monkeypatch.setattr(settings, "jwt_legacy_keys", [original_key], raising=False)

    session_list = client.get("/api/v1/auth/sessions", headers=admin_headers)
    assert session_list.status_code == 200, session_list.text
    current_session = session_list.json()[0]

    with SessionLocal() as session:
        stored = session.get(UserSession, current_session["id"])
        assert stored is not None
        payload = {
            "sub": stored.user_id,
            "sid": stored.id,
            "jti": stored.token_jti,
            "email": "admin@retainai.local",
            "role": "admin",
            "iss": settings.jwt_issuer,
            "aud": settings.jwt_audience,
            "iat": int(utc_now().timestamp()),
            "nbf": int(utc_now().timestamp()),
            "exp": int((utc_now() + timedelta(minutes=10)).timestamp()),
        }
    legacy_token = jwt.encode(
        payload,
        original_key,
        algorithm=settings.jwt_algorithm,
        headers={"kid": "legacy-1"},
    )
    response = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {legacy_token}"})
    assert response.status_code == 200, response.text


def test_probe_endpoints_report_liveness_and_readiness(client: TestClient) -> None:
    livez = client.get("/livez")
    assert livez.status_code == 200, livez.text
    assert livez.json()["status"] == "ok"

    readyz = client.get("/readyz")
    assert readyz.status_code == 200, readyz.text
    assert readyz.json()["status"] == "ok"


def test_metrics_endpoint_and_request_id_header(client: TestClient) -> None:
    response = client.get("/health", headers={"X-Request-ID": "req-phase3-001"})
    assert response.status_code == 200, response.text
    assert response.headers["x-request-id"] == "req-phase3-001"

    metrics = client.get("/metrics")
    assert metrics.status_code == 200, metrics.text
    assert "retainai_http_requests_total" in metrics.text
    assert "retainai_http_request_duration_seconds" in metrics.text
    assert "retainai_programs_total" in metrics.text


def test_model_train_job_can_be_enqueued_and_executed(
    client: TestClient,
    admin_headers: dict[str, str],
) -> None:
    enqueue = client.post("/api/v1/model/train", json={"force": True}, headers=admin_headers)

    assert enqueue.status_code == 202, enqueue.text
    queued_job = enqueue.json()
    assert queued_job["job_type"] == "model_train"
    assert queued_job["status"] == "queued"

    run_pending = client.post("/api/v1/jobs/run-pending", json={"max_jobs": 5}, headers=admin_headers)
    assert run_pending.status_code == 200, run_pending.text
    assert run_pending.json()["processed"] >= 1

    jobs = client.get("/api/v1/jobs", headers=admin_headers)
    assert jobs.status_code == 200, jobs.text
    model_jobs = [job for job in jobs.json() if job["job_type"] == "model_train"]
    assert model_jobs
    assert model_jobs[0]["status"] == "succeeded"
    assert model_jobs[0]["result"]["training_rows"] > 0

    model_status = client.get("/api/v1/model/status", headers=admin_headers)
    assert model_status.status_code == 200, model_status.text
    status_payload = model_status.json()
    assert status_payload["status"] == "deployed"
    assert status_payload["metrics"]["hard_label_rows"] > 0
    assert status_payload["metrics"]["excluded_label_rows"] >= 0
    assert status_payload["metrics"]["label_source_hard_positive_inactivity_threshold_crossed"] >= 0


def test_connector_sync_job_executes_and_creates_sync_run(
    client: TestClient,
    admin_headers: dict[str, str],
    monkeypatch,
) -> None:
    from app.services import connectors as connector_service

    programs = client.get("/api/v1/programs", headers=admin_headers)
    assert programs.status_code == 200, programs.text
    first_program = programs.json()[0]
    beneficiary_prefix = first_program["program_type"][:3].upper()

    def fake_fetch_connector_rows(_connector):
        return (
            [
                {
                    "id": f"{beneficiary_prefix}-0001",
                    "event_date": "2026-03-01",
                    "event_type": "attendance",
                    "successful": "true",
                    "response_received": "true",
                    "notes": "Completed household visit",
                },
                {
                    "id": f"{beneficiary_prefix}-0002",
                    "event_date": "2026-03-02",
                    "event_type": "attendance",
                    "successful": "false",
                    "response_received": "false",
                    "notes": "Travel barrier reported",
                },
            ],
            connector_service.ConnectorProbe(
                http_status=200,
                record_count=2,
                pages_fetched=1,
                sample_headers=["id", "event_date", "event_type", "successful", "response_received", "notes"],
                inferred_mapping={},
                warnings=[],
                message="Fetched 2 records from fake connector.",
            ),
        )

    monkeypatch.setattr(connector_service, "fetch_connector_rows", fake_fetch_connector_rows)

    connector = client.post(
        "/api/v1/connectors",
        json={
            "program_id": first_program["id"],
            "name": "Test Events Connector",
            "connector_type": "kobotoolbox",
            "dataset_type": "events",
            "base_url": "https://example.test",
            "resource_path": "/events",
            "auth_scheme": "none",
            "record_path": None,
            "query_params": {},
            "field_mapping": {
                "external_id": "id",
                "event_date": "event_date",
                "event_type": "event_type",
                "successful": "successful",
                "response_received": "response_received",
                "notes": "notes",
            },
            "schedule_enabled": False,
            "sync_interval_hours": None,
        },
        headers=admin_headers,
    )
    assert connector.status_code == 201, connector.text
    connector_id = connector.json()["id"]

    enqueue = client.post(f"/api/v1/connectors/{connector_id}/sync", headers=admin_headers)
    assert enqueue.status_code == 202, enqueue.text
    assert enqueue.json()["job_type"] == "connector_sync"

    run_pending = client.post("/api/v1/jobs/run-pending", json={"max_jobs": 5}, headers=admin_headers)
    assert run_pending.status_code == 200, run_pending.text

    jobs = client.get("/api/v1/jobs", headers=admin_headers)
    connector_jobs = [job for job in jobs.json() if job["job_type"] == "connector_sync"]
    assert connector_jobs
    assert connector_jobs[0]["status"] == "succeeded"
    assert connector_jobs[0]["result"]["records_processed"] == 2

    sync_runs = client.get("/api/v1/connectors/sync-runs", headers=admin_headers)
    assert sync_runs.status_code == 200, sync_runs.text
    assert sync_runs.json()
    assert sync_runs.json()[0]["status"] == "succeeded"
    assert sync_runs.json()[0]["records_processed"] == 2


def test_connector_probe_uses_native_pagination_and_mapping(
    client: TestClient,
    admin_headers: dict[str, str],
    monkeypatch,
) -> None:
    from app.services import connectors as connector_service

    programs = client.get("/api/v1/programs", headers=admin_headers)
    assert programs.status_code == 200, programs.text
    first_program = programs.json()[0]

    connector = client.post(
        "/api/v1/connectors",
        json={
            "program_id": first_program["id"],
            "name": "Salesforce Beneficiaries",
            "connector_type": "salesforce_npsp",
            "dataset_type": "beneficiaries",
            "base_url": "https://example.test",
            "resource_path": "/services/data/v61.0/query",
            "auth_scheme": "bearer",
            "secret": "demo-token",
            "query_params": {},
            "field_mapping": {},
            "schedule_enabled": False,
            "sync_interval_hours": None,
        },
        headers=admin_headers,
    )
    assert connector.status_code == 201, connector.text
    connector_id = connector.json()["id"]

    class FakeResponse:
        def __init__(self, payload: dict[str, object], status_code: int = 200) -> None:
            self._payload = payload
            self.status_code = status_code
            self.headers = {"content-type": "application/json"}
            self.content = b""

        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, object]:
            return self._payload

    class FakeClient:
        def __init__(self, *args, **kwargs) -> None:
            pass

        def __enter__(self) -> "FakeClient":
            return self

        def __exit__(self, exc_type, exc, tb) -> bool:
            return False

        def get(self, url: str, headers=None, params=None, auth=None) -> FakeResponse:
            if url.endswith("/services/data/v61.0/query"):
                return FakeResponse(
                    {
                        "records": [
                            {
                                "Id": "003A",
                                "Name": "Alice Example",
                                "Region__c": "Northern",
                                "Enrollment__c": "2026-01-10",
                                "attributes": {"type": "Contact"},
                            }
                        ],
                        "nextRecordsUrl": "/services/data/v61.0/query/01gNEXT",
                    }
                )
            if url.endswith("/services/data/v61.0/query/01gNEXT"):
                return FakeResponse(
                    {
                        "records": [
                            {
                                "Id": "003B",
                                "Name": "Bob Example",
                                "Region__c": "Central",
                                "Enrollment__c": "2026-01-12",
                                "attributes": {"type": "Contact"},
                            }
                        ]
                    }
                )
            raise AssertionError(f"Unexpected URL {url}")

    monkeypatch.setattr(connector_service.httpx, "Client", FakeClient)

    probe = client.post(f"/api/v1/connectors/{connector_id}/test", headers=admin_headers)
    assert probe.status_code == 200, probe.text
    probe_payload = probe.json()
    assert probe_payload["record_count"] == 2
    assert probe_payload["pages_fetched"] == 2
    assert "Id" in probe_payload["sample_headers"]
    assert probe_payload["inferred_mapping"]["external_id"] == "Id"

    connectors = client.get("/api/v1/connectors", headers=admin_headers)
    assert connectors.status_code == 200, connectors.text
    connector_payload = next(item for item in connectors.json() if item["id"] == connector_id)
    assert connector_payload["pagination_mode"] == "next_url"
    assert connector_payload["effective_record_path"] == "records"
    assert connector_payload["supports_incremental_sync"] is True


def test_connector_preview_webhook_and_follow_up_exports(
    client: TestClient,
    admin_headers: dict[str, str],
    monkeypatch,
) -> None:
    from app.services import connectors as connector_service

    programs = client.get("/api/v1/programs", headers=admin_headers)
    assert programs.status_code == 200, programs.text
    first_program = programs.json()[0]

    def fake_fetch_connector_rows(_connector):
        return (
            [
                {
                    "id": "EDU-9001",
                    "event_date": "2026-03-01",
                    "event_type": "attendance",
                    "successful": "false",
                    "response_received": "false",
                    "notes": "Transport barrier",
                }
            ],
            connector_service.ConnectorProbe(
                http_status=200,
                record_count=1,
                pages_fetched=1,
                sample_headers=["id", "event_date", "event_type", "successful", "response_received", "notes"],
                inferred_mapping={
                    "external_id": "id",
                    "event_date": "event_date",
                    "event_type": "event_type",
                    "successful": "successful",
                    "response_received": "response_received",
                    "notes": "notes",
                },
                warnings=[],
                message="Fetched 1 preview record.",
            ),
        )

    monkeypatch.setattr(connector_service, "fetch_connector_rows", fake_fetch_connector_rows)

    preview = client.post(
        "/api/v1/connectors/preview",
        json={
            "program_id": first_program["id"],
            "name": "Preview Connector",
            "connector_type": "kobotoolbox",
            "dataset_type": "events",
            "base_url": "https://example.test",
            "resource_path": "/events",
            "auth_scheme": "none",
            "query_params": {},
            "field_mapping": {},
            "schedule_enabled": False,
            "sync_interval_hours": None,
            "webhook_enabled": True,
            "webhook_secret": "preview-secret",
        },
        headers=admin_headers,
    )
    assert preview.status_code == 200, preview.text
    assert preview.json()["inferred_mapping"]["external_id"] == "id"

    connector = client.post(
        "/api/v1/connectors",
        json={
            "program_id": first_program["id"],
            "name": "Webhook Connector",
            "connector_type": "kobotoolbox",
            "dataset_type": "events",
            "base_url": "https://example.test",
            "resource_path": "/events",
            "auth_scheme": "none",
            "query_params": {},
            "field_mapping": {
                "external_id": "id",
                "event_date": "event_date",
                "event_type": "event_type",
                "successful": "successful",
                "response_received": "response_received",
                "notes": "notes",
            },
            "schedule_enabled": False,
            "sync_interval_hours": None,
            "webhook_enabled": True,
            "webhook_secret": "shared-secret",
        },
        headers=admin_headers,
    )
    assert connector.status_code == 201, connector.text
    connector_payload = connector.json()
    assert connector_payload["webhook_enabled"] is True
    assert connector_payload["has_webhook_secret"] is True

    webhook = client.post(
        f"/api/v1/connectors/{connector_payload['id']}/webhook",
        headers={"X-RetainAI-Webhook-Secret": "shared-secret"},
    )
    assert webhook.status_code == 202, webhook.text
    assert webhook.json()["job_type"] == "connector_sync"

    export = client.post(
        "/api/v1/exports/followup/whatsapp",
        json={
            "purpose": "weekly review",
            "include_pii": False,
            "risk_level": "High",
        },
        headers=admin_headers,
    )
    assert export.status_code == 200, export.text
    assert "message" in export.text.lower()
    assert "channel" in export.text.lower()


def test_automation_job_enqueues_and_processes_due_connector(
    client: TestClient,
    admin_headers: dict[str, str],
    monkeypatch,
) -> None:
    from app.db import SessionLocal
    from app.models import DataConnector
    from app.services import connectors as connector_service

    programs = client.get("/api/v1/programs", headers=admin_headers)
    first_program = programs.json()[0]
    beneficiary_prefix = first_program["program_type"][:3].upper()

    def fake_fetch_connector_rows(_connector):
        return (
            [
                {
                    "id": f"{beneficiary_prefix}-0003",
                    "event_date": "2026-03-03",
                    "event_type": "checkin",
                    "successful": "true",
                }
            ],
            connector_service.ConnectorProbe(
                http_status=200,
                record_count=1,
                pages_fetched=1,
                sample_headers=["id", "event_date", "event_type", "successful"],
                inferred_mapping={},
                warnings=[],
                message="Fetched 1 record from fake scheduled connector.",
            ),
        )

    monkeypatch.setattr(connector_service, "fetch_connector_rows", fake_fetch_connector_rows)

    connector = client.post(
        "/api/v1/connectors",
        json={
            "program_id": first_program["id"],
            "name": "Scheduled Connector",
            "connector_type": "kobotoolbox",
            "dataset_type": "events",
            "base_url": "https://example.test",
            "resource_path": "/scheduled-events",
            "auth_scheme": "none",
            "query_params": {},
            "field_mapping": {
                "external_id": "id",
                "event_date": "event_date",
                "event_type": "event_type",
                "successful": "successful",
            },
            "schedule_enabled": True,
            "sync_interval_hours": 24,
        },
        headers=admin_headers,
    )
    assert connector.status_code == 201, connector.text
    connector_id = connector.json()["id"]

    with SessionLocal() as session:
        connector_row = session.get(DataConnector, connector_id)
        assert connector_row is not None
        connector_row.next_sync_at = utc_now() - timedelta(minutes=5)
        session.add(connector_row)
        session.commit()

    enqueue = client.post("/api/v1/automation/run-due", headers=admin_headers)
    assert enqueue.status_code == 202, enqueue.text
    assert enqueue.json()["job_type"] == "automation_run_due"

    run_pending = client.post("/api/v1/jobs/run-pending", json={"max_jobs": 5}, headers=admin_headers)
    assert run_pending.status_code == 200, run_pending.text

    jobs = client.get("/api/v1/jobs", headers=admin_headers)
    automation_jobs = [job for job in jobs.json() if job["job_type"] == "automation_run_due"]
    assert automation_jobs
    assert automation_jobs[0]["status"] == "succeeded"
    assert automation_jobs[0]["result"]["connector_runs_triggered"] >= 1


def test_governance_opt_out_and_exports(
    client: TestClient,
    admin_headers: dict[str, str],
) -> None:
    governance = client.get("/api/v1/beneficiaries/governance?limit=5", headers=admin_headers)
    assert governance.status_code == 200, governance.text
    assert governance.json()
    beneficiary = governance.json()[0]

    update = client.patch(
        f"/api/v1/beneficiaries/{beneficiary['id']}/governance",
        json={"opted_out": True},
        headers=admin_headers,
    )
    assert update.status_code == 200, update.text
    assert update.json()["opted_out"] is True

    risk_cases = client.get("/api/v1/risk-cases", headers=admin_headers)
    assert risk_cases.status_code == 200, risk_cases.text
    matching_risk_case = next(case for case in risk_cases.json() if case["id"] == beneficiary["id"])
    assert matching_risk_case["opted_out"] is True
    assert matching_risk_case["confidence"] == "Opted out of modeling"

    export = client.post(
        "/api/v1/exports/risk-cases",
        json={"purpose": "weekly review", "include_pii": False},
        headers=admin_headers,
    )
    assert export.status_code == 200, export.text
    assert "text/csv" in export.headers["content-type"]
    assert "Beneficiary " in export.text

    director_login = client.post(
        "/api/v1/auth/login",
        json={"email": "country.director@retainai.local", "password": "retainai-demo"},
    )
    assert director_login.status_code == 200, director_login.text
    director_headers = {"Authorization": f"Bearer {director_login.json()['access_token']}"}
    denied = client.post(
        "/api/v1/exports/risk-cases",
        json={"purpose": "board review", "include_pii": True},
        headers=director_headers,
    )
    assert denied.status_code == 403, denied.text


def test_import_analysis_and_quality_issue_persistence(
    client: TestClient,
    admin_headers: dict[str, str],
) -> None:
    programs = client.get("/api/v1/programs", headers=admin_headers)
    assert programs.status_code == 200, programs.text
    first_program = programs.json()[0]

    csv_payload = "\n".join(
        [
            "external_id,full_name,region,enrollment_date,household_size,opted_out",
            "B-9001,Amina Yusuf,Northern,2026-01-15,30,maybe",
            "B-9001,Amina Yusuf,Northern,2026-01-15,30,maybe",
            "B-9002,Joseph Banda,Central,2026-02-01,5,true",
        ]
    )

    analysis = client.post(
        "/api/v1/imports/analyze",
        data={"dataset_type": "beneficiaries"},
        files={"file": ("beneficiaries.csv", csv_payload, "text/csv")},
        headers=admin_headers,
    )
    assert analysis.status_code == 200, analysis.text
    analysis_payload = analysis.json()
    assert analysis_payload["source_format"] == "csv"
    assert analysis_payload["records_received"] == 3
    assert analysis_payload["duplicate_rows"] == 1
    assert "external_id" in analysis_payload["available_columns"]
    assert any(issue["issue_type"] == "duplicate_row" for issue in analysis_payload["issues"])
    assert any(issue["issue_type"] == "outlier_household_size" for issue in analysis_payload["issues"])

    imported = client.post(
        "/api/v1/imports/csv",
        data={"dataset_type": "beneficiaries", "program_id": first_program["id"]},
        files={"file": ("beneficiaries.csv", csv_payload, "text/csv")},
        headers=admin_headers,
    )
    assert imported.status_code == 201, imported.text
    imported_payload = imported.json()
    assert imported_payload["records_received"] == 3
    assert imported_payload["duplicates_detected"] == 1
    assert imported_payload["quality_summary"]["quality_score"] < 100

    issues = client.get(
        f"/api/v1/imports/{imported_payload['id']}/issues",
        headers=admin_headers,
    )
    assert issues.status_code == 200, issues.text


def test_retention_reporting_capacity_and_federated_endpoints(
    client: TestClient,
    admin_headers: dict[str, str],
) -> None:
    programs = client.get("/api/v1/programs", headers=admin_headers)
    assert programs.status_code == 200, programs.text
    first_program = programs.json()[0]

    settings_response = client.get("/api/v1/program-settings", headers=admin_headers)
    assert settings_response.status_code == 200, settings_response.text
    assert settings_response.json()

    updated_setting = client.put(
        f"/api/v1/program-settings/{first_program['id']}",
        json={
            "weekly_followup_capacity": 12,
            "medium_risk_multiplier": 2.5,
            "high_risk_share_floor": 0.1,
            "review_window_days": 45,
        },
        headers=admin_headers,
    )
    assert updated_setting.status_code == 200, updated_setting.text
    assert updated_setting.json()["weekly_followup_capacity"] == 12

    retention_analytics = client.get("/api/v1/retention/analytics", headers=admin_headers)
    assert retention_analytics.status_code == 200, retention_analytics.text
    assert retention_analytics.json()["breakdowns"]

    intervention_effectiveness = client.get("/api/v1/interventions/effectiveness", headers=admin_headers)
    assert intervention_effectiveness.status_code == 200, intervention_effectiveness.text
    assert "rows" in intervention_effectiveness.json()

    donor_summary = client.get("/api/v1/reports/donor-summary", headers=admin_headers)
    assert donor_summary.status_code == 200, donor_summary.text
    assert "headline_metrics" in donor_summary.json()

    donor_xlsx = client.get("/api/v1/reports/donor-summary.xlsx", headers=admin_headers)
    assert donor_xlsx.status_code == 200, donor_xlsx.text
    assert "spreadsheetml" in donor_xlsx.headers["content-type"]

    donor_pdf = client.get("/api/v1/reports/donor-summary.pdf", headers=admin_headers)
    assert donor_pdf.status_code == 200, donor_pdf.text
    assert "application/pdf" in donor_pdf.headers["content-type"]

    train = client.post("/api/v1/model/train", json={"force": True}, headers=admin_headers)
    assert train.status_code == 202, train.text
    run_pending = client.post("/api/v1/jobs/run-pending", json={"max_jobs": 5}, headers=admin_headers)
    assert run_pending.status_code == 200, run_pending.text

    export_update = client.post(
        "/api/v1/federated/export-update",
        json={
            "round_name": "round-alpha",
            "deployment_label": "test-suite",
            "source_program_id": first_program["id"],
        },
        headers=admin_headers,
    )
    assert export_update.status_code == 200, export_update.text
    assert export_update.json()["deployment_label"] == "test-suite"
    export_update_two = client.post(
        "/api/v1/federated/export-update",
        json={
            "round_name": "round-alpha",
            "deployment_label": "test-suite-2",
            "source_program_id": first_program["id"],
        },
        headers=admin_headers,
    )
    assert export_update_two.status_code == 200, export_update_two.text

    federated_rounds = client.get("/api/v1/federated/rounds", headers=admin_headers)
    assert federated_rounds.status_code == 200, federated_rounds.text
    assert federated_rounds.json()

    aggregate = client.post(
        "/api/v1/federated/aggregate",
        json={"round_name": "round-alpha", "close_round": True},
        headers=admin_headers,
    )
    assert aggregate.status_code == 200, aggregate.text
    assert aggregate.json()["aggregated_payload"]["participant_updates"] >= 1


def test_xlsx_analysis_feature_store_and_drift_endpoints(
    client: TestClient,
    admin_headers: dict[str, str],
) -> None:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Events"
    sheet.append(["external_id", "event_date", "event_type", "successful", "notes"])
    sheet.append(["CAS-0001", "2026-03-01", "attendance", "true", "Household reached"])
    sheet.append(["CAS-0001", "2026-03-01", "attendance", "true", "Duplicate row retained"])
    sheet.append(["CAS-0002", "2026-03-04", "checkin", "false", "Transport barrier"])
    buffer = BytesIO()
    workbook.save(buffer)
    workbook.close()

    analysis = client.post(
        "/api/v1/imports/analyze",
        data={"dataset_type": "events"},
        files={
            "file": (
                "events.xlsx",
                buffer.getvalue(),
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
        headers=admin_headers,
    )
    assert analysis.status_code == 200, analysis.text
    analysis_payload = analysis.json()
    assert analysis_payload["source_format"] == "xlsx"
    assert analysis_payload["records_received"] == 3
    assert analysis_payload["duplicate_rows"] == 1

    enqueue = client.post("/api/v1/model/train", json={"force": True}, headers=admin_headers)
    assert enqueue.status_code == 202, enqueue.text
    run_pending = client.post("/api/v1/jobs/run-pending", json={"max_jobs": 5}, headers=admin_headers)
    assert run_pending.status_code == 200, run_pending.text

    risk_cases = client.get("/api/v1/risk-cases", headers=admin_headers)
    assert risk_cases.status_code == 200, risk_cases.text
    assert risk_cases.json()

    feature_store = client.get("/api/v1/feature-store/summary", headers=admin_headers)
    assert feature_store.status_code == 200, feature_store.text
    feature_store_payload = feature_store.json()
    assert feature_store_payload["training_snapshots"] > 0
    assert feature_store_payload["scoring_snapshots"] > 0

    drift = client.get("/api/v1/model/drift?refresh=true", headers=admin_headers)
    assert drift.status_code == 200, drift.text
    drift_payload = drift.json()
    assert drift_payload["status"] in {"ok", "attention", "insufficient_data"}
    assert "feature_reports" in drift_payload

    model_status = client.get("/api/v1/model/status", headers=admin_headers)
    assert model_status.status_code == 200, model_status.text
    metrics = model_status.json()["metrics"]
    assert metrics["high_risk_threshold_score"] >= metrics["medium_risk_threshold_score"]
    assert metrics["high_risk_precision"] >= 0
    assert metrics["medium_or_higher_recall"] >= 0


def test_governance_privacy_and_explanation_endpoints(
    client: TestClient,
    admin_headers: dict[str, str],
) -> None:
    programs = client.get("/api/v1/programs", headers=admin_headers)
    assert programs.status_code == 200, programs.text
    first_program = programs.json()[0]

    policies = client.get("/api/v1/program-data-policies", headers=admin_headers)
    assert policies.status_code == 200, policies.text
    assert policies.json()

    updated_policy = client.put(
        f"/api/v1/program-data-policies/{first_program['id']}",
        json={
            "storage_mode": "managed_region",
            "data_residency_region": "eu-central",
            "cross_border_transfers_allowed": False,
            "pii_tokenization_enabled": True,
            "consent_required": True,
            "federated_learning_enabled": False,
        },
        headers=admin_headers,
    )
    assert updated_policy.status_code == 200, updated_policy.text
    assert updated_policy.json()["storage_mode"] == "managed_region"

    governance_records = client.get("/api/v1/beneficiaries/governance?limit=5", headers=admin_headers)
    assert governance_records.status_code == 200, governance_records.text
    first_beneficiary = governance_records.json()[0]
    assert first_beneficiary["pii_token"]

    updated_governance = client.patch(
        f"/api/v1/beneficiaries/{first_beneficiary['id']}/governance",
        json={
            "opted_out": False,
            "modeling_consent_status": "granted",
            "consent_method": "dashboard_update",
            "explained_to_beneficiary": True,
        },
        headers=admin_headers,
    )
    assert updated_governance.status_code == 200, updated_governance.text
    assert updated_governance.json()["modeling_consent_status"] == "granted"

    explanation = client.get(f"/api/v1/beneficiaries/{first_beneficiary['id']}/explanation", headers=admin_headers)
    assert explanation.status_code == 200, explanation.text
    assert explanation.json()["beneficiary_facing_summary"]

    synthetic = client.get("/api/v1/synthetic/portfolio?rows_per_program=60", headers=admin_headers)
    assert synthetic.status_code == 200, synthetic.text
    assert len(synthetic.json()) >= 3


def test_oidc_sso_and_runtime_health_endpoints(
    client: TestClient,
    admin_headers: dict[str, str],
    monkeypatch,
) -> None:
    from app.services import sso as sso_service

    settings = get_settings()
    monkeypatch.setattr(settings, "sso_enabled", True, raising=False)
    monkeypatch.setattr(settings, "sso_mode", "oidc", raising=False)
    monkeypatch.setattr(settings, "sso_provider_label", "OpenID Provider", raising=False)
    monkeypatch.setattr(settings, "sso_oidc_issuer_url", "https://issuer.example", raising=False)
    monkeypatch.setattr(settings, "sso_oidc_client_id", "retainai-web", raising=False)
    monkeypatch.setattr(settings, "sso_oidc_client_secret", "retainai-secret", raising=False)

    class FakeResponse:
        def __init__(self, payload: dict[str, object], status_code: int = 200) -> None:
            self._payload = payload
            self.status_code = status_code

        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, object]:
            return self._payload

    class FakeClient:
        def __init__(self, *args, **kwargs) -> None:
            pass

        def __enter__(self) -> "FakeClient":
            return self

        def __exit__(self, exc_type, exc, tb) -> bool:
            return False

        def get(self, url: str, headers=None) -> FakeResponse:
            if url.endswith("/.well-known/openid-configuration"):
                return FakeResponse(
                    {
                        "issuer": "https://issuer.example",
                        "authorization_endpoint": "https://issuer.example/oauth2/authorize",
                        "token_endpoint": "https://issuer.example/oauth2/token",
                        "userinfo_endpoint": "https://issuer.example/oauth2/userinfo",
                    }
                )
            if url.endswith("/oauth2/userinfo"):
                return FakeResponse(
                    {
                        "email": "oidc.user@example.org",
                        "name": "OIDC User",
                        "role": "me_officer",
                    }
                )
            raise AssertionError(f"Unexpected OIDC GET URL {url}")

        def post(self, url: str, data=None, headers=None) -> FakeResponse:
            if url.endswith("/oauth2/token"):
                return FakeResponse({"access_token": "oidc-access-token", "token_type": "Bearer"})
            raise AssertionError(f"Unexpected OIDC POST URL {url}")

    monkeypatch.setattr(sso_service.httpx, "Client", FakeClient)

    config = client.get("/api/v1/auth/sso/config")
    assert config.status_code == 200, config.text
    assert config.json()["interactive"] is True
    assert config.json()["mode"] == "oidc"

    start = client.get(
        "/api/v1/auth/sso/oidc/start",
        params={"redirect_uri": "http://localhost:5173"},
    )
    assert start.status_code == 200, start.text
    start_payload = start.json()
    assert "authorization_url" in start_payload
    assert start_payload["provider_label"] == "OpenID Provider"

    exchange = client.post(
        "/api/v1/auth/sso/oidc/exchange",
        json={
            "code": "oidc-code",
            "state": start_payload["state"],
            "redirect_uri": "http://localhost:5173",
        },
    )
    assert exchange.status_code == 200, exchange.text
    assert exchange.json()["user"]["email"] == "oidc.user@example.org"
    assert exchange.json()["user"]["role"] == "me_officer"

    runtime_status = client.get("/api/v1/ops/runtime-status", headers=admin_headers)
    assert runtime_status.status_code == 200, runtime_status.text
    assert runtime_status.json()["deployment_region"]

    worker_health = client.get("/api/v1/ops/worker-health", headers=admin_headers)
    assert worker_health.status_code == 200, worker_health.text
    assert "queued" in worker_health.json()


def test_job_retry_and_dead_letter_behavior(
    client: TestClient,
    admin_headers: dict[str, str],
    monkeypatch,
) -> None:
    from app.db import SessionLocal
    from app.models import JobRecord
    from app.services import jobs as job_service

    settings = get_settings()
    monkeypatch.setattr(settings, "job_max_attempts", 2, raising=False)
    monkeypatch.setattr(settings, "job_retry_backoff_seconds", 1, raising=False)

    def failing_train(*args, **kwargs):
        raise RuntimeError("forced model failure for retry testing")

    monkeypatch.setattr(job_service, "train_and_deploy_model", failing_train)

    enqueue = client.post("/api/v1/model/train", json={"force": True}, headers=admin_headers)
    assert enqueue.status_code == 202, enqueue.text
    job_id = enqueue.json()["id"]

    first_run = client.post("/api/v1/jobs/run-pending", json={"max_jobs": 5}, headers=admin_headers)
    assert first_run.status_code == 200, first_run.text

    jobs_after_retry = client.get("/api/v1/jobs", headers=admin_headers)
    assert jobs_after_retry.status_code == 200, jobs_after_retry.text
    first_job = next(item for item in jobs_after_retry.json() if item["id"] == job_id)
    assert first_job["status"] == "queued"
    assert first_job["attempts"] == 1

    with SessionLocal() as session:
        job_row = session.get(JobRecord, job_id)
        assert job_row is not None
        job_row.available_at = utc_now()
        session.add(job_row)
        session.commit()

    second_run = client.post("/api/v1/jobs/run-pending", json={"max_jobs": 5}, headers=admin_headers)
    assert second_run.status_code == 200, second_run.text

    jobs_after_dead_letter = client.get("/api/v1/jobs", headers=admin_headers)
    assert jobs_after_dead_letter.status_code == 200, jobs_after_dead_letter.text
    dead_letter_job = next(item for item in jobs_after_dead_letter.json() if item["id"] == job_id)
    assert dead_letter_job["status"] == "dead_letter"
    assert dead_letter_job["attempts"] == 2
    assert dead_letter_job["dead_lettered_at"] is not None

    worker_health = client.get("/api/v1/ops/worker-health", headers=admin_headers)
    assert worker_health.status_code == 200, worker_health.text
    assert worker_health.json()["dead_letter"] >= 1

    metrics = client.get("/metrics")
    assert metrics.status_code == 200, metrics.text
    assert 'retainai_job_executions_total{job_type="model_train",status="dead_letter"}' in metrics.text
    assert 'retainai_jobs_by_status{status="dead_letter"}' in metrics.text

    requeue = client.post(f"/api/v1/jobs/{job_id}/requeue", headers=admin_headers)
    assert requeue.status_code == 200, requeue.text
    assert requeue.json()["status"] == "queued"
    assert requeue.json()["attempts"] == 0


def test_federated_duplicate_submission_is_rejected(
    client: TestClient,
    admin_headers: dict[str, str],
) -> None:
    programs = client.get("/api/v1/programs", headers=admin_headers)
    assert programs.status_code == 200, programs.text
    first_program = programs.json()[0]

    train = client.post("/api/v1/model/train", json={"force": True}, headers=admin_headers)
    assert train.status_code == 202, train.text
    run_pending = client.post("/api/v1/jobs/run-pending", json={"max_jobs": 5}, headers=admin_headers)
    assert run_pending.status_code == 200, run_pending.text

    for deployment_label in ("site-a", "site-a", "site-b"):
        response = client.post(
            "/api/v1/federated/export-update",
            json={
                "round_name": "round-replay-check",
                "deployment_label": deployment_label,
                "source_program_id": first_program["id"],
            },
            headers=admin_headers,
        )
        assert response.status_code == 200, response.text

    aggregate = client.post(
        "/api/v1/federated/aggregate",
        json={"round_name": "round-replay-check", "close_round": True},
        headers=admin_headers,
    )
    assert aggregate.status_code == 200, aggregate.text
    aggregated_payload = aggregate.json()["aggregated_payload"]
    assert aggregated_payload["verified_updates"] == 2
    assert aggregated_payload["rejected_updates"]
    assert aggregated_payload["rejected_updates"][0]["reason"] == "Duplicate deployment submission"


def test_temporal_backtest_evaluation_report(
    client: TestClient,
    admin_headers: dict[str, str],
) -> None:
    response = client.post(
        "/api/v1/model/evaluate/backtest",
        json={
            "temporal_strategy": "rolling",
            "horizon_days": 30,
            "min_history_days": 30,
            "holdout_share": 0.25,
            "rolling_folds": 3,
            "top_k_share": 0.2,
            "bootstrap_iterations": 20,
        },
        headers=admin_headers,
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["status"] in {"ready_for_shadow_mode", "needs_more_data", "not_ready"}
    assert payload["split"]["temporal_strategy"] == "rolling"
    assert payload["split"]["folds_considered"] >= 1
    assert payload["split"]["folds_used"] >= 0
    if payload["split"]["folds_used"] == 0:
        assert payload["status"] == "needs_more_data"
    assert payload["split"]["train_cases"] > 0
    assert payload["split"]["test_cases"] > 0
    assert 0 <= payload["metrics"]["top_k_recall"]["value"] <= 1
    assert 0 <= payload["metrics"]["auc_roc"]["value"] <= 1
    assert payload["metrics"]["top_k_lift"]["value"] >= 0
    assert payload["metrics"]["expected_calibration_error"]["value"] >= 0
    if payload["split"]["folds_used"] == 0:
        assert payload["calibration"] == []
    else:
        assert payload["calibration"]


def test_temporal_backtest_supports_filters(
    client: TestClient,
    admin_headers: dict[str, str],
) -> None:
    unfiltered_response = client.post(
        "/api/v1/model/evaluate/backtest",
        json={
            "temporal_strategy": "rolling",
            "horizon_days": 30,
            "min_history_days": 30,
            "holdout_share": 0.25,
            "rolling_folds": 2,
            "top_k_share": 0.2,
            "bootstrap_iterations": 20,
        },
        headers=admin_headers,
    )
    assert unfiltered_response.status_code == 200, unfiltered_response.text
    unfiltered_payload = unfiltered_response.json()

    programs_response = client.get("/api/v1/programs", headers=admin_headers)
    assert programs_response.status_code == 200, programs_response.text
    programs = programs_response.json()
    assert programs
    response = client.post(
        "/api/v1/model/evaluate/backtest",
        json={
            "temporal_strategy": "rolling",
            "horizon_days": 30,
            "min_history_days": 30,
            "holdout_share": 0.25,
            "rolling_folds": 2,
            "top_k_share": 0.2,
            "bootstrap_iterations": 20,
            "program_ids": [programs[0]["id"]],
        },
        headers=admin_headers,
    )
    assert response.status_code in {200, 400}, response.text
    if response.status_code == 200:
        payload = response.json()
        assert payload["samples_evaluated"] <= unfiltered_payload["samples_evaluated"]
        assert payload["split"]["folds_considered"] >= 1
    else:
        assert "Not enough retrospective snapshot cases" in response.text


def test_synthetic_stress_endpoints(
    client: TestClient,
    admin_headers: dict[str, str],
) -> None:
    scenarios = client.get("/api/v1/synthetic/stress-scenarios", headers=admin_headers)
    assert scenarios.status_code == 200, scenarios.text
    assert any(item["name"] == "fairness_gap" for item in scenarios.json())

    summary = client.get("/api/v1/synthetic/stress-summary?rows_per_program=60&seed=7", headers=admin_headers)
    assert summary.status_code == 200, summary.text
    payload = summary.json()
    assert payload
    assert any(item["scenario"] == "high_missingness" for item in payload)


def test_phase1_action_loop_program_settings_and_workflow_updates(
    client: TestClient,
    admin_headers: dict[str, str],
) -> None:
    programs = client.get("/api/v1/programs", headers=admin_headers)
    assert programs.status_code == 200, programs.text
    first_program = programs.json()[0]

    settings_response = client.put(
        f"/api/v1/program-settings/{first_program['id']}",
        json={
            "weekly_followup_capacity": 18,
            "worker_count": 3,
            "medium_risk_multiplier": 1.8,
            "high_risk_share_floor": 0.1,
            "review_window_days": 28,
            "label_definition_preset": "health_28d",
            "dropout_inactivity_days": 28,
            "prediction_window_days": 14,
            "label_noise_strategy": "operational_soft_labels",
            "soft_label_weight": 0.4,
            "silent_transfer_detection_enabled": True,
            "fairness_reweighting_enabled": True,
            "fairness_target_dimensions": ["gender", "region"],
            "fairness_max_gap": 0.2,
            "fairness_min_group_size": 12,
            "tracing_sms_delay_days": 3,
            "tracing_call_delay_days": 7,
            "tracing_visit_delay_days": 14,
        },
        headers=admin_headers,
    )
    assert settings_response.status_code == 200, settings_response.text
    setting_payload = settings_response.json()
    assert setting_payload["worker_count"] == 3
    assert setting_payload["label_definition_preset"] == "health_28d"
    assert setting_payload["prediction_window_days"] == 14
    assert setting_payload["label_noise_strategy"] == "operational_soft_labels"
    assert setting_payload["soft_label_weight"] == 0.4
    assert setting_payload["silent_transfer_detection_enabled"] is True
    assert setting_payload["tracing_sms_delay_days"] == 3
    assert setting_payload["tracing_call_delay_days"] == 7
    assert setting_payload["tracing_visit_delay_days"] == 14

    risk_cases = client.get("/api/v1/risk-cases", headers=admin_headers)
    assert risk_cases.status_code == 200, risk_cases.text
    queue_case = risk_cases.json()[0]
    assert queue_case["queue_bucket"] in {"Due now", "This week", "Monitor"}
    assert queue_case["queue_rank"] >= 1
    assert "workflow" in queue_case
    assert "soft_signals" in queue_case
    assert queue_case["tracing_protocol"]["current_step"] in {"sms", "call", "visit"}
    assert queue_case["tracing_protocol"]["current_channel"] in {"sms", "whatsapp", "call", "manual", "visit"}
    assert queue_case["tracing_protocol"]["sms_delay_days"] == 3
    assert queue_case["tracing_protocol"]["call_delay_days"] == 7
    assert queue_case["tracing_protocol"]["visit_delay_days"] == 14

    create_workflow = client.post(
        "/api/v1/interventions",
        json={
            "beneficiary_id": queue_case["id"],
            "action_type": "Schedule check-in",
            "support_channel": "call",
            "protocol_step": "call",
            "status": "queued",
            "verification_status": "pending",
            "assigned_to": "Grace Atieno",
            "assigned_site": "Northern Region Site 1",
            "due_at": "2026-03-20T09:00:00Z",
            "note": "Queued from phase-1 API test.",
            "risk_level": queue_case["risk_level"],
            "priority_rank": 1,
            "soft_signals": {
                "household_stability_signal": 4,
                "economic_stress_signal": 3,
                "family_support_signal": 2,
                "health_change_signal": None,
                "motivation_signal": 4,
            },
        },
        headers=admin_headers,
    )
    assert create_workflow.status_code == 201, create_workflow.text
    created_payload = create_workflow.json()
    assert created_payload["status"] == "queued"
    assert created_payload["assigned_to"] == "Grace Atieno"
    assert created_payload["soft_signals"]["household_stability_signal"] == 4
    assert created_payload["protocol_step"] == "call"

    update_workflow = client.patch(
        f"/api/v1/interventions/{created_payload['id']}",
        json={
            "status": "verified",
            "verification_status": "re_engaged",
            "verification_note": "Reached and confirmed re-engagement.",
            "attempt_count": 1,
            "successful": True,
        },
        headers=admin_headers,
    )
    assert update_workflow.status_code == 200, update_workflow.text
    updated_payload = update_workflow.json()
    assert updated_payload["status"] == "verified"
    assert updated_payload["verification_status"] == "re_engaged"
    assert updated_payload["successful"] is True
    assert updated_payload["verified_at"] is not None

    refreshed_cases = client.get("/api/v1/risk-cases", headers=admin_headers)
    assert refreshed_cases.status_code == 200, refreshed_cases.text
    refreshed_case = next(item for item in refreshed_cases.json() if item["id"] == queue_case["id"])
    assert refreshed_case["workflow"]["intervention_id"] == created_payload["id"]
    assert refreshed_case["workflow"]["status"] == "verified"
    assert refreshed_case["workflow"]["verification_status"] == "re_engaged"
    assert refreshed_case["workflow"]["protocol_step"] == "call"
    assert refreshed_case["workflow"]["tracing_protocol"]["current_step"] in {"call", "visit"}


def test_phase2_connector_dispatch_preview_and_writeback(
    client: TestClient,
    admin_headers: dict[str, str],
    monkeypatch,
) -> None:
    from sqlalchemy import select

    from app.db import SessionLocal
    from app.models import Intervention
    from app.services import connectors as connector_service

    programs = client.get("/api/v1/programs", headers=admin_headers)
    assert programs.status_code == 200, programs.text
    first_program = programs.json()[0]

    connector_response = client.post(
        "/api/v1/connectors",
        json={
            "program_id": first_program["id"],
            "name": "CommCare Dispatch",
            "connector_type": "commcare",
            "dataset_type": "beneficiaries",
            "base_url": "https://example.test",
            "resource_path": "/cases",
            "auth_scheme": "none",
            "query_params": {},
            "field_mapping": {},
            "schedule_enabled": False,
            "sync_interval_hours": None,
            "writeback_enabled": True,
            "writeback_mode": "commcare_case_updates",
            "writeback_resource_path": "/writeback/cases",
            "writeback_field_mapping": {},
        },
        headers=admin_headers,
    )
    assert connector_response.status_code == 201, connector_response.text
    connector_id = connector_response.json()["id"]

    with SessionLocal() as session:
        preview_interventions = list(
            session.scalars(
                select(Intervention).where(Intervention.source == "embedded_dispatch:commcare_case_updates")
            ).all()
        )
    assert preview_interventions == []

    preview = client.post(
        f"/api/v1/connectors/{connector_id}/dispatch",
        json={
            "only_due": False,
            "include_this_week": True,
            "limit": 25,
            "preview_only": True,
        },
        headers=admin_headers,
    )
    assert preview.status_code == 200, preview.text
    preview_payload = preview.json()
    assert preview_payload["status"] == "preview"
    assert preview_payload["target_mode"] == "commcare_case_updates"
    assert preview_payload["cases_included"] > 0

    with SessionLocal() as session:
        preview_interventions = list(
            session.scalars(
                select(Intervention).where(Intervention.source == "embedded_dispatch:commcare_case_updates")
            ).all()
        )
    assert preview_interventions == []

    captured_request: dict[str, object] = {}

    class FakeResponse:
        status_code = 200

        def raise_for_status(self) -> None:
            return None

    class FakeClient:
        def __init__(self, *args, **kwargs) -> None:
            pass

        def __enter__(self) -> "FakeClient":
            return self

        def __exit__(self, exc_type, exc, tb) -> bool:
            return False

        def post(self, url: str, headers=None, json=None, auth=None) -> FakeResponse:
            captured_request["url"] = url
            captured_request["headers"] = headers
            captured_request["json"] = json
            return FakeResponse()

    monkeypatch.setattr(connector_service.httpx, "Client", FakeClient)

    dispatch = client.post(
        f"/api/v1/connectors/{connector_id}/dispatch",
        json={
            "only_due": False,
            "include_this_week": True,
            "limit": 25,
            "preview_only": False,
        },
        headers=admin_headers,
    )
    assert dispatch.status_code == 200, dispatch.text
    dispatch_payload = dispatch.json()
    assert dispatch_payload["status"] == "succeeded"
    assert dispatch_payload["records_sent"] == dispatch_payload["cases_included"]
    assert dispatch_payload["records_sent"] > 0

    assert captured_request["url"] == "https://example.test/writeback/cases"
    outbound = captured_request["json"]
    assert isinstance(outbound, dict)
    assert outbound["mode"] == "commcare_case_updates"
    assert outbound["cases"]
    first_case = outbound["cases"][0]
    assert first_case["properties"]["retainai_protocol_step"] in {"sms", "call", "visit"}
    assert first_case["task"]["protocol_step"] in {"sms", "call", "visit"}

    dispatch_runs = client.get("/api/v1/connectors/dispatch-runs", headers=admin_headers)
    assert dispatch_runs.status_code == 200, dispatch_runs.text
    assert dispatch_runs.json()
    assert dispatch_runs.json()[0]["status"] == "succeeded"

    connectors = client.get("/api/v1/connectors", headers=admin_headers)
    assert connectors.status_code == 200, connectors.text
    connector_payload = next(item for item in connectors.json() if item["id"] == connector_id)
    assert connector_payload["last_dispatched_at"] is not None

    with SessionLocal() as session:
        dispatched_interventions = list(
            session.scalars(
                select(Intervention).where(Intervention.source == "embedded_dispatch:commcare_case_updates")
            ).all()
        )
    assert dispatched_interventions
    assert all(item.status in {"queued", "escalated", "verified", "reached", "attempted"} for item in dispatched_interventions)
    assert all(item.protocol_step in {"sms", "call", "visit"} for item in dispatched_interventions)


def test_operational_labeling_supports_soft_labels_and_silent_transfer_exclusion(
    client: TestClient,
    admin_headers: dict[str, str],
) -> None:
    from sqlalchemy import select

    from app.db import SessionLocal
    from app.models import Beneficiary, Intervention, MonitoringEvent, Program
    from app.services.analytics import ensure_program_operational_setting
    from app.services.labeling import build_operational_settings_profile, construct_operational_label

    programs = client.get("/api/v1/programs", headers=admin_headers)
    assert programs.status_code == 200, programs.text

    with SessionLocal() as session:
        program = session.scalar(select(Program).order_by(Program.created_at.asc()))
        assert program is not None
        setting = ensure_program_operational_setting(session, program)
        setting.dropout_inactivity_days = 28
        setting.prediction_window_days = 14
        setting.label_noise_strategy = "operational_soft_labels"
        setting.soft_label_weight = 0.4
        setting.silent_transfer_detection_enabled = True
        session.add(setting)

        soft_beneficiary = Beneficiary(
            program_id=program.id,
            external_id="TEST-SOFT-001",
            full_name="Soft Label Case",
            gender="Female",
            region="Northern Region",
            cohort="2026-Q1",
            phase="Enrollment",
            enrollment_date=date(2025, 1, 1),
            dropout_date=date(2025, 3, 12),
            status="dropped",
            household_stability_signal=4,
            economic_stress_signal=4,
            family_support_signal=3,
            health_change_signal=3,
            motivation_signal=4,
            modeling_consent_status="granted",
        )
        session.add(soft_beneficiary)
        session.flush()
        session.add_all(
            [
                MonitoringEvent(
                    beneficiary_id=soft_beneficiary.id,
                    event_date=date(2025, 1, 20),
                    event_type="attendance",
                    successful=True,
                    response_received=True,
                    source="clinic_a",
                ),
                MonitoringEvent(
                    beneficiary_id=soft_beneficiary.id,
                    event_date=date(2025, 2, 10),
                    event_type="attendance",
                    successful=True,
                    response_received=True,
                    source="clinic_a",
                ),
                MonitoringEvent(
                    beneficiary_id=soft_beneficiary.id,
                    event_date=date(2025, 2, 20),
                    event_type="checkin",
                    successful=False,
                    response_received=False,
                    source="clinic_a",
                    notes="Missed scheduled contact.",
                ),
                MonitoringEvent(
                    beneficiary_id=soft_beneficiary.id,
                    event_date=date(2025, 2, 25),
                    event_type="checkin",
                    successful=False,
                    response_received=False,
                    source="clinic_a",
                    notes="No response to outreach.",
                ),
                MonitoringEvent(
                    beneficiary_id=soft_beneficiary.id,
                    event_date=date(2025, 3, 5),
                    event_type="missed_visit",
                    successful=False,
                    response_received=None,
                    source="clinic_a",
                    notes="Still unreachable.",
                ),
            ]
        )

        transfer_beneficiary = Beneficiary(
            program_id=program.id,
            external_id="TEST-TRANSFER-001",
            full_name="Transfer Detection Case",
            gender="Male",
            region="Northern Region",
            cohort="2026-Q1",
            phase="Treatment",
            enrollment_date=date(2025, 1, 1),
            status="active",
            current_note="Household relocated and transferred to another clinic.",
            modeling_consent_status="granted",
        )
        session.add(transfer_beneficiary)
        session.flush()
        session.add_all(
            [
                MonitoringEvent(
                    beneficiary_id=transfer_beneficiary.id,
                    event_date=date(2025, 1, 18),
                    event_type="attendance",
                    successful=True,
                    response_received=True,
                    source="clinic_a",
                ),
                MonitoringEvent(
                    beneficiary_id=transfer_beneficiary.id,
                    event_date=date(2025, 2, 12),
                    event_type="attendance",
                    successful=True,
                    response_received=True,
                    source="clinic_b",
                    notes="Seen at another facility after relocation.",
                ),
                Intervention(
                    beneficiary_id=transfer_beneficiary.id,
                    action_type="Verify care status",
                    support_channel="call",
                    protocol_step="call",
                    status="verified",
                    verification_status="silent_transfer",
                    verification_note="Confirmed silent transfer to another clinic.",
                    logged_at=datetime(2025, 3, 20, 10, 0, 0),
                    source="manual",
                ),
            ]
        )
        session.commit()

        session.refresh(soft_beneficiary)
        session.refresh(transfer_beneficiary)
        profile = build_operational_settings_profile(program.program_type, setting)

        soft_label = construct_operational_label(
            soft_beneficiary,
            snapshot_date=date(2025, 3, 1),
            profile=profile,
            observation_end=date(2025, 3, 5),
        )
        transfer_label = construct_operational_label(
            transfer_beneficiary,
            snapshot_date=date(2025, 3, 1),
            profile=profile,
            observation_end=date(2025, 4, 1),
        )

    assert soft_label.excluded is False
    assert soft_label.hard_label is False
    assert soft_label.label == 1
    assert soft_label.source == "soft_positive_terminal_status_prior"
    assert soft_label.sample_weight == 0.4
    assert soft_label.label_probability is not None
    assert soft_label.label_probability >= 0.65

    assert transfer_label.excluded is True
    assert transfer_label.suspected_silent_transfer is True
    assert transfer_label.silent_transfer_assessment.status == "confirmed"
    assert transfer_label.source == "excluded_confirmed_silent_transfer"


def test_phase3_backtest_persistence_and_shadow_run_maturation(
    client: TestClient,
    admin_headers: dict[str, str],
) -> None:
    from sqlalchemy import select

    from app.db import SessionLocal
    from app.models import Beneficiary, Intervention, ShadowRun, ShadowRunCase

    programs = client.get("/api/v1/programs", headers=admin_headers)
    assert programs.status_code == 200, programs.text
    first_program = programs.json()[0]

    validation_update = client.put(
        f"/api/v1/program-validation/{first_program['id']}",
        json={
            "shadow_mode_enabled": True,
            "shadow_prediction_window_days": 30,
            "minimum_precision_at_capacity": 0.6,
            "minimum_recall_at_capacity": 0.4,
            "require_fairness_review": True,
        },
        headers=admin_headers,
    )
    assert validation_update.status_code == 200, validation_update.text
    assert validation_update.json()["shadow_mode_enabled"] is True

    backtest = client.post(
        "/api/v1/model/evaluate/backtest",
        json={
            "temporal_strategy": "rolling",
            "horizon_days": 30,
            "min_history_days": 30,
            "holdout_share": 0.25,
            "rolling_folds": 2,
            "top_k_share": 0.2,
            "bootstrap_iterations": 20,
        },
        headers=admin_headers,
    )
    assert backtest.status_code == 200, backtest.text
    backtest_payload = backtest.json()
    assert backtest_payload["status"] in {"ready_for_shadow_mode", "needs_more_data", "not_ready"}

    evaluation_reports = client.get(
        "/api/v1/model/evaluations?limit=10",
        headers=admin_headers,
    )
    assert evaluation_reports.status_code == 200, evaluation_reports.text
    reports_payload = evaluation_reports.json()
    assert reports_payload
    assert reports_payload[0]["created_by_email"] == "admin@retainai.local"
    assert reports_payload[0]["report"]["metrics"]["top_k_precision"]["value"] >= 0

    shadow_run_response = client.post(
        f"/api/v1/program-validation/{first_program['id']}/shadow-runs",
        json={"top_k_count": 3, "note": "Phase-3 maturation regression"},
        headers=admin_headers,
    )
    assert shadow_run_response.status_code == 200, shadow_run_response.text
    shadow_payload = shadow_run_response.json()
    assert shadow_payload["status"] == "captured"
    assert shadow_payload["cases_captured"] > 0

    with SessionLocal() as session:
        shadow_run = session.scalar(
            select(ShadowRun).where(ShadowRun.id == shadow_payload["id"])
        )
        assert shadow_run is not None
        shadow_cases = list(
            session.scalars(
                select(ShadowRunCase)
                .where(ShadowRunCase.shadow_run_id == shadow_run.id)
                .order_by(ShadowRunCase.rank_order.asc())
            ).all()
        )
        assert shadow_cases

        mature_snapshot_date = utc_now().date() - timedelta(days=45)
        shadow_run.snapshot_date = mature_snapshot_date
        for case in shadow_cases:
            case.snapshot_date = mature_snapshot_date

        top_case = next(case for case in shadow_cases if case.included_in_top_k)
        beneficiary = session.scalar(
            select(Beneficiary).where(Beneficiary.id == top_case.beneficiary_id)
        )
        assert beneficiary is not None
        beneficiary.dropout_date = mature_snapshot_date + timedelta(days=7)
        beneficiary.completion_date = None
        beneficiary.status = "active"

        session.add(
            Intervention(
                beneficiary_id=beneficiary.id,
                action_type="Shadow-mode outreach",
                support_channel="call",
                status="attempted",
                verification_status="pending",
                source="shadow_mode_test",
                logged_at=datetime.combine(
                    mature_snapshot_date + timedelta(days=2),
                    datetime.min.time(),
                ),
            )
        )
        session.commit()

    refreshed_shadow_runs = client.get(
        f"/api/v1/program-validation/shadow-runs?limit=10&program_id={first_program['id']}",
        headers=admin_headers,
    )
    assert refreshed_shadow_runs.status_code == 200, refreshed_shadow_runs.text
    refreshed_run = next(item for item in refreshed_shadow_runs.json() if item["id"] == shadow_payload["id"])
    assert refreshed_run["status"] == "matured"
    assert refreshed_run["matured_cases"] == refreshed_run["cases_captured"]
    assert refreshed_run["observed_positive_cases"] >= 1
    assert refreshed_run["actioned_cases"] >= 1
    assert refreshed_run["top_k_precision"] is not None
    assert refreshed_run["top_k_recall"] is not None
