"""SQLAlchemy models for RetainAI's operational domain.

The models capture three overlapping concerns:

- program operations: beneficiaries, events, interventions, imports, queues
- platform infrastructure: users, sessions, jobs, connectors, audit logs
- model governance: model versions, bias audits, drift reports, evaluations,
  shadow runs, and federated-learning exchange metadata

This file is intentionally broad because the platform is end-to-end: the same
database has to support case workflows, evidence generation, privacy controls,
and deployment operations.
"""

from __future__ import annotations

from datetime import date, datetime
from uuid import uuid4

from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.core.time import utc_now


def generate_uuid() -> str:
    return str(uuid4())


class Program(Base):
    __tablename__ = "programs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    name: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    program_type: Mapped[str] = mapped_column(String(100), index=True)
    country: Mapped[str] = mapped_column(String(100))
    delivery_modality: Mapped[str | None] = mapped_column(String(100), nullable=True)
    status: Mapped[str] = mapped_column(String(50), default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)

    beneficiaries: Mapped[list["Beneficiary"]] = relationship(
        back_populates="program",
        cascade="all, delete-orphan",
    )
    import_batches: Mapped[list["ImportBatch"]] = relationship(
        back_populates="program",
        cascade="all, delete-orphan",
    )
    connectors: Mapped[list["DataConnector"]] = relationship(
        back_populates="program",
        cascade="all, delete-orphan",
    )
    operational_setting: Mapped["ProgramOperationalSetting | None"] = relationship(
        back_populates="program",
        cascade="all, delete-orphan",
        uselist=False,
    )
    data_policy: Mapped["ProgramDataPolicy | None"] = relationship(
        back_populates="program",
        cascade="all, delete-orphan",
        uselist=False,
    )
    validation_setting: Mapped["ProgramValidationSetting | None"] = relationship(
        back_populates="program",
        cascade="all, delete-orphan",
        uselist=False,
    )
    shadow_runs: Mapped[list["ShadowRun"]] = relationship(
        back_populates="program",
        cascade="all, delete-orphan",
        order_by="ShadowRun.created_at.desc()",
    )


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    full_name: Mapped[str] = mapped_column(String(255))
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    role: Mapped[str] = mapped_column(String(80), index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, index=True)

    audit_logs: Mapped[list["AuditLog"]] = relationship(back_populates="actor")
    connector_sync_runs: Mapped[list["ConnectorSyncRun"]] = relationship(back_populates="triggered_by")
    dispatch_runs: Mapped[list["ConnectorDispatchRun"]] = relationship(back_populates="triggered_by")
    jobs: Mapped[list["JobRecord"]] = relationship(back_populates="created_by")
    evaluation_reports: Mapped[list["EvaluationReport"]] = relationship(back_populates="created_by")
    shadow_runs: Mapped[list["ShadowRun"]] = relationship(back_populates="created_by")
    sessions: Mapped[list["UserSession"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
        order_by="UserSession.issued_at.desc()",
    )


class Beneficiary(Base):
    __tablename__ = "beneficiaries"
    __table_args__ = (
        UniqueConstraint("program_id", "external_id", name="uq_program_beneficiary_external_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    program_id: Mapped[str] = mapped_column(ForeignKey("programs.id"), index=True)
    external_id: Mapped[str] = mapped_column(String(100), index=True)
    full_name: Mapped[str] = mapped_column(String(255))
    gender: Mapped[str | None] = mapped_column(String(50), nullable=True)
    region: Mapped[str] = mapped_column(String(120), index=True)
    cohort: Mapped[str | None] = mapped_column(String(120), nullable=True)
    phase: Mapped[str | None] = mapped_column(String(120), nullable=True)
    household_type: Mapped[str | None] = mapped_column(String(120), nullable=True)
    delivery_modality: Mapped[str | None] = mapped_column(String(120), nullable=True)
    enrollment_date: Mapped[date] = mapped_column(Date)
    dropout_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    completion_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(String(50), default="active", index=True)
    household_size: Mapped[int | None] = mapped_column(nullable=True)
    pmt_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    food_insecurity_index: Mapped[float | None] = mapped_column(Float, nullable=True)
    distance_to_service_km: Mapped[float | None] = mapped_column(Float, nullable=True)
    preferred_contact_phone: Mapped[str | None] = mapped_column(String(40), nullable=True)
    preferred_contact_channel: Mapped[str | None] = mapped_column(String(40), nullable=True)
    current_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    assigned_case_worker: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    assigned_site: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    household_stability_signal: Mapped[int | None] = mapped_column(nullable=True)
    economic_stress_signal: Mapped[int | None] = mapped_column(nullable=True)
    family_support_signal: Mapped[int | None] = mapped_column(nullable=True)
    health_change_signal: Mapped[int | None] = mapped_column(nullable=True)
    motivation_signal: Mapped[int | None] = mapped_column(nullable=True)
    opted_out: Mapped[bool] = mapped_column(Boolean, default=False)
    modeling_consent_status: Mapped[str] = mapped_column(String(40), default="granted", index=True)
    consent_captured_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    consent_explained_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    consent_method: Mapped[str | None] = mapped_column(String(80), nullable=True)
    consent_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    pii_token: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True, unique=True)
    pii_tokenized_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=utc_now,
        onupdate=utc_now,
    )

    program: Mapped[Program] = relationship(back_populates="beneficiaries")
    monitoring_events: Mapped[list["MonitoringEvent"]] = relationship(
        back_populates="beneficiary",
        cascade="all, delete-orphan",
        order_by="MonitoringEvent.event_date.desc()",
    )
    interventions: Mapped[list["Intervention"]] = relationship(
        back_populates="beneficiary",
        cascade="all, delete-orphan",
        order_by="Intervention.logged_at.desc()",
    )


class MonitoringEvent(Base):
    __tablename__ = "monitoring_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    beneficiary_id: Mapped[str] = mapped_column(ForeignKey("beneficiaries.id"), index=True)
    event_date: Mapped[date] = mapped_column(Date, index=True)
    event_type: Mapped[str] = mapped_column(String(100), index=True)
    successful: Mapped[bool] = mapped_column(Boolean, default=True)
    response_received: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    source: Mapped[str | None] = mapped_column(String(100), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)

    beneficiary: Mapped[Beneficiary] = relationship(back_populates="monitoring_events")


class Intervention(Base):
    __tablename__ = "interventions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    beneficiary_id: Mapped[str] = mapped_column(ForeignKey("beneficiaries.id"), index=True)
    action_type: Mapped[str] = mapped_column(String(120))
    support_channel: Mapped[str | None] = mapped_column(String(40), nullable=True)
    protocol_step: Mapped[str | None] = mapped_column(String(20), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(40), default="queued", index=True)
    verification_status: Mapped[str | None] = mapped_column(String(60), nullable=True, index=True)
    risk_level: Mapped[str | None] = mapped_column(String(20), nullable=True)
    assigned_to: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    assigned_site: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    due_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    verification_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    dismissal_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    attempt_count: Mapped[int] = mapped_column(default=0)
    source: Mapped[str] = mapped_column(String(40), default="manual")
    priority_rank: Mapped[int | None] = mapped_column(nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    successful: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    logged_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, index=True)

    beneficiary: Mapped[Beneficiary] = relationship(back_populates="interventions")


class ImportBatch(Base):
    __tablename__ = "import_batches"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    program_id: Mapped[str] = mapped_column(ForeignKey("programs.id"), index=True)
    dataset_type: Mapped[str] = mapped_column(String(50), index=True)
    source_format: Mapped[str] = mapped_column(String(20), default="csv")
    filename: Mapped[str] = mapped_column(String(255))
    records_received: Mapped[int] = mapped_column(default=0)
    records_processed: Mapped[int] = mapped_column(default=0)
    records_failed: Mapped[int] = mapped_column(default=0)
    duplicates_detected: Mapped[int] = mapped_column(default=0)
    resolved_mapping: Mapped[dict[str, str | None]] = mapped_column(JSON, default=dict)
    warning_preview: Mapped[list[str]] = mapped_column(JSON, default=list)
    quality_summary: Mapped[dict[str, str | int | float | bool | None] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, index=True)

    program: Mapped[Program] = relationship(back_populates="import_batches")
    quality_issues: Mapped[list["DataQualityIssue"]] = relationship(
        back_populates="import_batch",
        cascade="all, delete-orphan",
        order_by="DataQualityIssue.created_at.desc()",
    )


class ModelVersion(Base):
    __tablename__ = "model_versions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    name: Mapped[str] = mapped_column(String(120), index=True)
    algorithm: Mapped[str] = mapped_column(String(120))
    status: Mapped[str] = mapped_column(String(50), default="candidate", index=True)
    artifact_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    mlflow_run_id: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    trained_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, index=True)
    training_rows: Mapped[int] = mapped_column(default=0)
    positive_rows: Mapped[int] = mapped_column(default=0)
    features: Mapped[list[str]] = mapped_column(JSON, default=list)
    metrics: Mapped[dict[str, float | int | str]] = mapped_column(JSON, default=dict)
    top_drivers: Mapped[list[dict[str, float | str]]] = mapped_column(JSON, default=list)
    training_profile: Mapped[dict[str, object] | None] = mapped_column(JSON, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    bias_audits: Mapped[list["ModelBiasAudit"]] = relationship(
        back_populates="model_version",
        cascade="all, delete-orphan",
        order_by="ModelBiasAudit.dimension.asc()",
    )
    feature_snapshots: Mapped[list["FeatureSnapshot"]] = relationship(
        back_populates="model_version",
        cascade="all, delete-orphan",
        order_by="FeatureSnapshot.snapshot_date.desc()",
    )
    drift_reports: Mapped[list["ModelDriftReport"]] = relationship(
        back_populates="model_version",
        cascade="all, delete-orphan",
        order_by="ModelDriftReport.monitored_at.desc()",
    )
    federated_updates: Mapped[list["FederatedModelUpdate"]] = relationship(
        back_populates="model_version",
        cascade="all, delete-orphan",
        order_by="FederatedModelUpdate.created_at.desc()",
    )


class ModelBiasAudit(Base):
    __tablename__ = "model_bias_audits"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    model_version_id: Mapped[str] = mapped_column(ForeignKey("model_versions.id"), index=True)
    dimension: Mapped[str] = mapped_column(String(80), index=True)
    group_name: Mapped[str] = mapped_column(String(120), index=True)
    sample_size: Mapped[int] = mapped_column(default=0)
    positive_count: Mapped[int] = mapped_column(default=0)
    predicted_positive_count: Mapped[int] = mapped_column(default=0)
    flagged_rate: Mapped[float | None] = mapped_column(Float, nullable=True)
    false_positive_rate: Mapped[float | None] = mapped_column(Float, nullable=True)
    recall_rate: Mapped[float | None] = mapped_column(Float, nullable=True)
    severity: Mapped[str] = mapped_column(String(50), default="ok", index=True)
    guidance: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, index=True)

    model_version: Mapped[ModelVersion] = relationship(back_populates="bias_audits")


class DataConnector(Base):
    __tablename__ = "data_connectors"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    program_id: Mapped[str] = mapped_column(ForeignKey("programs.id"), index=True)
    name: Mapped[str] = mapped_column(String(255), index=True)
    connector_type: Mapped[str] = mapped_column(String(80), index=True)
    dataset_type: Mapped[str] = mapped_column(String(50), index=True)
    status: Mapped[str] = mapped_column(String(50), default="draft", index=True)
    base_url: Mapped[str] = mapped_column(String(500))
    resource_path: Mapped[str] = mapped_column(String(500))
    auth_scheme: Mapped[str] = mapped_column(String(50), default="bearer")
    auth_username: Mapped[str | None] = mapped_column(String(255), nullable=True)
    encrypted_secret: Mapped[str | None] = mapped_column(Text, nullable=True)
    record_path: Mapped[str | None] = mapped_column(String(255), nullable=True)
    query_params: Mapped[dict[str, str | int | float | bool | None]] = mapped_column(JSON, default=dict)
    field_mapping: Mapped[dict[str, str | None]] = mapped_column(JSON, default=dict)
    sync_state: Mapped[dict[str, str | int | float | bool | None]] = mapped_column(JSON, default=dict)
    schedule_enabled: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    sync_interval_hours: Mapped[int | None] = mapped_column(nullable=True)
    writeback_enabled: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    writeback_mode: Mapped[str] = mapped_column(String(80), default="none")
    writeback_resource_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    writeback_field_mapping: Mapped[dict[str, str | int | float | bool | None]] = mapped_column(JSON, default=dict)
    webhook_enabled: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    encrypted_webhook_secret: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_webhook_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    last_dispatched_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    next_sync_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, index=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=utc_now,
        onupdate=utc_now,
    )

    program: Mapped[Program] = relationship(back_populates="connectors")
    sync_runs: Mapped[list["ConnectorSyncRun"]] = relationship(
        back_populates="connector",
        cascade="all, delete-orphan",
        order_by="ConnectorSyncRun.started_at.desc()",
    )
    dispatch_runs: Mapped[list["ConnectorDispatchRun"]] = relationship(
        back_populates="connector",
        cascade="all, delete-orphan",
        order_by="ConnectorDispatchRun.started_at.desc()",
    )


class ConnectorSyncRun(Base):
    __tablename__ = "connector_sync_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    connector_id: Mapped[str] = mapped_column(ForeignKey("data_connectors.id"), index=True)
    triggered_by_user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    trigger_mode: Mapped[str] = mapped_column(String(50), default="manual", index=True)
    status: Mapped[str] = mapped_column(String(50), default="queued", index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, index=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    records_fetched: Mapped[int] = mapped_column(default=0)
    records_processed: Mapped[int] = mapped_column(default=0)
    records_failed: Mapped[int] = mapped_column(default=0)
    warnings: Mapped[list[str]] = mapped_column(JSON, default=list)
    import_batch_id: Mapped[str | None] = mapped_column(ForeignKey("import_batches.id"), nullable=True, index=True)
    model_retrained: Mapped[bool] = mapped_column(Boolean, default=False)
    model_version_id: Mapped[str | None] = mapped_column(ForeignKey("model_versions.id"), nullable=True, index=True)
    log_excerpt: Mapped[str | None] = mapped_column(Text, nullable=True)

    connector: Mapped[DataConnector] = relationship(back_populates="sync_runs")
    triggered_by: Mapped[User | None] = relationship(back_populates="connector_sync_runs")
    import_batch: Mapped[ImportBatch | None] = relationship()
    model_version: Mapped[ModelVersion | None] = relationship()


class ConnectorDispatchRun(Base):
    __tablename__ = "connector_dispatch_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    connector_id: Mapped[str] = mapped_column(ForeignKey("data_connectors.id"), index=True)
    triggered_by_user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(50), default="queued", index=True)
    target_mode: Mapped[str] = mapped_column(String(80), default="none", index=True)
    payload_preview: Mapped[dict[str, object] | None] = mapped_column(JSON, nullable=True)
    records_sent: Mapped[int] = mapped_column(default=0)
    cases_included: Mapped[int] = mapped_column(default=0)
    cases_skipped: Mapped[int] = mapped_column(default=0)
    warnings: Mapped[list[str]] = mapped_column(JSON, default=list)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, index=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    log_excerpt: Mapped[str | None] = mapped_column(Text, nullable=True)

    connector: Mapped[DataConnector] = relationship(back_populates="dispatch_runs")
    triggered_by: Mapped[User | None] = relationship(back_populates="dispatch_runs")


class ModelSchedule(Base):
    __tablename__ = "model_schedules"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    cadence: Mapped[str] = mapped_column(String(50), default="manual")
    auto_retrain_after_sync: Mapped[bool] = mapped_column(Boolean, default=False)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    next_run_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, index=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=utc_now,
        onupdate=utc_now,
    )


class JobRecord(Base):
    __tablename__ = "jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    job_type: Mapped[str] = mapped_column(String(80), index=True)
    status: Mapped[str] = mapped_column(String(50), default="queued", index=True)
    created_by_user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    payload: Mapped[dict[str, str | int | float | bool | None]] = mapped_column(JSON, default=dict)
    result: Mapped[dict[str, str | int | float | bool | None] | None] = mapped_column(JSON, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    attempts: Mapped[int] = mapped_column(default=0)
    max_attempts: Mapped[int] = mapped_column(default=3)
    retry_backoff_seconds: Mapped[int] = mapped_column(default=45)
    available_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, index=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    last_error_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    dead_lettered_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, index=True)

    created_by: Mapped[User | None] = relationship(back_populates="jobs")


class DataQualityIssue(Base):
    __tablename__ = "data_quality_issues"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    import_batch_id: Mapped[str | None] = mapped_column(ForeignKey("import_batches.id"), nullable=True, index=True)
    severity: Mapped[str] = mapped_column(String(20), default="warning", index=True)
    issue_type: Mapped[str] = mapped_column(String(80), index=True)
    field_name: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    row_number: Mapped[int | None] = mapped_column(nullable=True)
    message: Mapped[str] = mapped_column(Text)
    sample_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, index=True)

    import_batch: Mapped[ImportBatch | None] = relationship(back_populates="quality_issues")


class FeatureSnapshot(Base):
    __tablename__ = "feature_snapshots"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    beneficiary_id: Mapped[str] = mapped_column(ForeignKey("beneficiaries.id"), index=True)
    model_version_id: Mapped[str | None] = mapped_column(ForeignKey("model_versions.id"), nullable=True, index=True)
    source_kind: Mapped[str] = mapped_column(String(30), index=True)
    snapshot_date: Mapped[date] = mapped_column(Date, index=True)
    label: Mapped[int | None] = mapped_column(nullable=True)
    uncertainty_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    values: Mapped[dict[str, object]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, index=True)

    beneficiary: Mapped[Beneficiary] = relationship()
    model_version: Mapped[ModelVersion | None] = relationship(back_populates="feature_snapshots")


class ModelDriftReport(Base):
    __tablename__ = "model_drift_reports"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    model_version_id: Mapped[str] = mapped_column(ForeignKey("model_versions.id"), index=True)
    status: Mapped[str] = mapped_column(String(30), default="ok", index=True)
    overall_psi: Mapped[float] = mapped_column(Float, default=0.0)
    feature_reports: Mapped[list[dict[str, object]]] = mapped_column(JSON, default=list)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    monitored_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, index=True)

    model_version: Mapped[ModelVersion] = relationship(back_populates="drift_reports")


class ProgramOperationalSetting(Base):
    __tablename__ = "program_operational_settings"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    program_id: Mapped[str] = mapped_column(ForeignKey("programs.id"), unique=True, index=True)
    weekly_followup_capacity: Mapped[int] = mapped_column(default=30)
    worker_count: Mapped[int] = mapped_column(default=4)
    medium_risk_multiplier: Mapped[float] = mapped_column(Float, default=2.0)
    high_risk_share_floor: Mapped[float] = mapped_column(Float, default=0.08)
    review_window_days: Mapped[int] = mapped_column(default=30)
    label_definition_preset: Mapped[str] = mapped_column(String(40), default="custom")
    dropout_inactivity_days: Mapped[int] = mapped_column(default=30)
    prediction_window_days: Mapped[int] = mapped_column(default=30)
    label_noise_strategy: Mapped[str] = mapped_column(String(40), default="operational_soft_labels")
    soft_label_weight: Mapped[float] = mapped_column(Float, default=0.35)
    silent_transfer_detection_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    low_risk_channel: Mapped[str] = mapped_column(String(20), default="sms")
    medium_risk_channel: Mapped[str] = mapped_column(String(20), default="call")
    high_risk_channel: Mapped[str] = mapped_column(String(20), default="visit")
    tracing_sms_delay_days: Mapped[int] = mapped_column(default=3)
    tracing_call_delay_days: Mapped[int] = mapped_column(default=7)
    tracing_visit_delay_days: Mapped[int] = mapped_column(default=14)
    escalation_window_days: Mapped[int] = mapped_column(default=7)
    escalation_max_attempts: Mapped[int] = mapped_column(default=2)
    fairness_reweighting_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    fairness_target_dimensions: Mapped[list[str]] = mapped_column(JSON, default=list)
    fairness_max_gap: Mapped[float] = mapped_column(Float, default=0.15)
    fairness_min_group_size: Mapped[int] = mapped_column(default=20)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=utc_now,
        onupdate=utc_now,
    )

    program: Mapped[Program] = relationship(back_populates="operational_setting")


class ProgramValidationSetting(Base):
    __tablename__ = "program_validation_settings"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    program_id: Mapped[str] = mapped_column(ForeignKey("programs.id"), unique=True, index=True)
    shadow_mode_enabled: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    shadow_prediction_window_days: Mapped[int] = mapped_column(default=30)
    minimum_precision_at_capacity: Mapped[float] = mapped_column(Float, default=0.7)
    minimum_recall_at_capacity: Mapped[float] = mapped_column(Float, default=0.5)
    require_fairness_review: Mapped[bool] = mapped_column(Boolean, default=True)
    last_evaluation_status: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)
    last_shadow_run_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, index=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=utc_now,
        onupdate=utc_now,
    )

    program: Mapped[Program] = relationship(back_populates="validation_setting")


class ProgramDataPolicy(Base):
    __tablename__ = "program_data_policies"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    program_id: Mapped[str] = mapped_column(ForeignKey("programs.id"), unique=True, index=True)
    storage_mode: Mapped[str] = mapped_column(String(40), default="self_hosted")
    data_residency_region: Mapped[str] = mapped_column(String(80), default="eu-central")
    cross_border_transfers_allowed: Mapped[bool] = mapped_column(Boolean, default=False)
    pii_tokenization_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    consent_required: Mapped[bool] = mapped_column(Boolean, default=True)
    federated_learning_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=utc_now,
        onupdate=utc_now,
    )

    program: Mapped[Program] = relationship(back_populates="data_policy")


class EvaluationReport(Base):
    __tablename__ = "evaluation_reports"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    created_by_user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    program_scope: Mapped[list[str]] = mapped_column(JSON, default=list)
    cohort_scope: Mapped[list[str]] = mapped_column(JSON, default=list)
    temporal_strategy: Mapped[str] = mapped_column(String(30), index=True)
    status: Mapped[str] = mapped_column(String(40), index=True)
    algorithm: Mapped[str] = mapped_column(String(120))
    horizon_days: Mapped[int] = mapped_column(default=30)
    samples_evaluated: Mapped[int] = mapped_column(default=0)
    positive_cases: Mapped[int] = mapped_column(default=0)
    request_payload: Mapped[dict[str, object]] = mapped_column(JSON, default=dict)
    report_payload: Mapped[dict[str, object]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, index=True)

    created_by: Mapped[User | None] = relationship(back_populates="evaluation_reports")


class ShadowRun(Base):
    __tablename__ = "shadow_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    program_id: Mapped[str] = mapped_column(ForeignKey("programs.id"), index=True)
    created_by_user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(40), default="captured", index=True)
    snapshot_date: Mapped[date] = mapped_column(Date, index=True)
    horizon_days: Mapped[int] = mapped_column(default=30)
    top_k_count: Mapped[int] = mapped_column(default=0)
    cases_captured: Mapped[int] = mapped_column(default=0)
    high_risk_cases: Mapped[int] = mapped_column(default=0)
    due_now_cases: Mapped[int] = mapped_column(default=0)
    matured_cases: Mapped[int] = mapped_column(default=0)
    observed_positive_cases: Mapped[int] = mapped_column(default=0)
    actioned_cases: Mapped[int] = mapped_column(default=0)
    top_k_precision: Mapped[float | None] = mapped_column(Float, nullable=True)
    top_k_recall: Mapped[float | None] = mapped_column(Float, nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, index=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)

    program: Mapped[Program] = relationship(back_populates="shadow_runs")
    created_by: Mapped[User | None] = relationship(back_populates="shadow_runs")
    cases: Mapped[list["ShadowRunCase"]] = relationship(
        back_populates="shadow_run",
        cascade="all, delete-orphan",
        order_by="ShadowRunCase.rank_order.asc()",
    )


class ShadowRunCase(Base):
    __tablename__ = "shadow_run_cases"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    shadow_run_id: Mapped[str] = mapped_column(ForeignKey("shadow_runs.id"), index=True)
    beneficiary_id: Mapped[str] = mapped_column(ForeignKey("beneficiaries.id"), index=True)
    snapshot_date: Mapped[date] = mapped_column(Date, index=True)
    rank_order: Mapped[int] = mapped_column(default=0, index=True)
    included_in_top_k: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    risk_level: Mapped[str] = mapped_column(String(20))
    risk_score: Mapped[int] = mapped_column(default=0)
    queue_bucket: Mapped[str] = mapped_column(String(30), default="Monitor")
    queue_rank: Mapped[int] = mapped_column(default=0)
    assigned_worker: Mapped[str | None] = mapped_column(String(120), nullable=True)
    assigned_site: Mapped[str | None] = mapped_column(String(120), nullable=True)
    recommended_action: Mapped[str] = mapped_column(String(255))
    observed_outcome: Mapped[str] = mapped_column(String(40), default="pending", index=True)
    observed_at: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    action_logged: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, index=True)

    shadow_run: Mapped[ShadowRun] = relationship(back_populates="cases")
    beneficiary: Mapped[Beneficiary] = relationship()


class FederatedLearningRound(Base):
    __tablename__ = "federated_learning_rounds"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    round_name: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    round_nonce: Mapped[str] = mapped_column(String(120), default=generate_uuid, index=True)
    status: Mapped[str] = mapped_column(String(40), default="collecting", index=True)
    aggregation_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    aggregated_payload: Mapped[dict[str, object] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, index=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)

    updates: Mapped[list["FederatedModelUpdate"]] = relationship(
        back_populates="round",
        cascade="all, delete-orphan",
        order_by="FederatedModelUpdate.created_at.desc()",
    )


class FederatedModelUpdate(Base):
    __tablename__ = "federated_model_updates"
    __table_args__ = (
        UniqueConstraint("round_id", "update_fingerprint", name="uq_federated_update_fingerprint"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    round_id: Mapped[str] = mapped_column(ForeignKey("federated_learning_rounds.id"), index=True)
    source_program_id: Mapped[str | None] = mapped_column(ForeignKey("programs.id"), nullable=True, index=True)
    model_version_id: Mapped[str | None] = mapped_column(ForeignKey("model_versions.id"), nullable=True, index=True)
    deployment_label: Mapped[str] = mapped_column(String(120), index=True)
    source_nonce: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    update_fingerprint: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    training_rows: Mapped[int] = mapped_column(default=0)
    positive_rows: Mapped[int] = mapped_column(default=0)
    payload: Mapped[dict[str, object]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, index=True)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)

    round: Mapped[FederatedLearningRound] = relationship(back_populates="updates")
    program: Mapped[Program | None] = relationship()
    model_version: Mapped[ModelVersion | None] = relationship(back_populates="federated_updates")


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    actor_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    actor_email: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    actor_role: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    action: Mapped[str] = mapped_column(String(120), index=True)
    resource_type: Mapped[str] = mapped_column(String(120), index=True)
    resource_id: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    details: Mapped[dict[str, str | int | float | bool | None] | None] = mapped_column(JSON, nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(80), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, index=True)

    actor: Mapped[User | None] = relationship(back_populates="audit_logs")


class UserSession(Base):
    __tablename__ = "user_sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    token_jti: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    token_key_id: Mapped[str] = mapped_column(String(120), index=True)
    auth_method: Mapped[str] = mapped_column(String(40), default="password", index=True)
    source_ip: Mapped[str | None] = mapped_column(String(80), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(255), nullable=True)
    issued_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, index=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    revoked_reason: Mapped[str | None] = mapped_column(String(120), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, index=True)

    user: Mapped[User] = relationship(back_populates="sessions")
