"""Pydantic request/response schemas for RetainAI.

These models define the public API contract for the FastAPI application. They
are intentionally more descriptive than the ORM models because they also serve
as the source of truth for generated OpenAPI documentation, web-client typing,
and integration expectations for external adopters.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class HealthResponse(BaseModel):
    status: str
    environment: str
    database_configured: bool
    programs: int


class ProbeResponse(BaseModel):
    status: Literal["ok", "degraded"]
    component: str
    detail: str


class LoginRequest(BaseModel):
    email: str = Field(min_length=5, max_length=255)
    password: str = Field(min_length=8, max_length=255)


class CurrentUser(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    full_name: str
    email: str
    role: str
    is_active: bool
    last_login_at: datetime | None = None
    created_at: datetime


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in_seconds: int
    session_id: str | None = None
    user: CurrentUser


class SessionRecord(BaseModel):
    id: str
    auth_method: str
    token_key_id: str
    source_ip: str | None = None
    user_agent: str | None = None
    issued_at: datetime
    expires_at: datetime
    last_seen_at: datetime
    revoked_at: datetime | None = None
    revoked_reason: str | None = None


class LogoutResponse(BaseModel):
    status: Literal["revoked"]
    session_id: str


class DataConnectorCreate(BaseModel):
    program_id: str
    name: str = Field(min_length=3, max_length=255)
    connector_type: str = Field(min_length=3, max_length=80)
    dataset_type: Literal["beneficiaries", "events"]
    base_url: str = Field(min_length=8, max_length=500)
    resource_path: str = Field(min_length=1, max_length=500)
    auth_scheme: Literal["none", "bearer", "token", "basic"] = "bearer"
    auth_username: str | None = Field(default=None, max_length=255)
    secret: str | None = Field(default=None, max_length=2000)
    record_path: str | None = Field(default=None, max_length=255)
    query_params: dict[str, str | int | float | bool | None] = Field(default_factory=dict)
    field_mapping: dict[str, str | None] = Field(default_factory=dict)
    schedule_enabled: bool = False
    sync_interval_hours: int | None = Field(default=None, ge=1, le=720)
    writeback_enabled: bool = False
    writeback_mode: Literal["none", "commcare_case_updates", "dhis2_working_list", "generic_webhook"] = "none"
    writeback_resource_path: str | None = Field(default=None, max_length=500)
    writeback_field_mapping: dict[str, str | int | float | bool | None] = Field(default_factory=dict)
    webhook_enabled: bool = False
    webhook_secret: str | None = Field(default=None, max_length=2000)


class DataConnectorUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=3, max_length=255)
    connector_type: str | None = Field(default=None, min_length=3, max_length=80)
    dataset_type: Literal["beneficiaries", "events"] | None = None
    base_url: str | None = Field(default=None, min_length=8, max_length=500)
    resource_path: str | None = Field(default=None, min_length=1, max_length=500)
    auth_scheme: Literal["none", "bearer", "token", "basic"] | None = None
    auth_username: str | None = Field(default=None, max_length=255)
    secret: str | None = Field(default=None, max_length=2000)
    record_path: str | None = Field(default=None, max_length=255)
    query_params: dict[str, str | int | float | bool | None] | None = None
    field_mapping: dict[str, str | None] | None = None
    schedule_enabled: bool | None = None
    sync_interval_hours: int | None = Field(default=None, ge=1, le=720)
    writeback_enabled: bool | None = None
    writeback_mode: Literal["none", "commcare_case_updates", "dhis2_working_list", "generic_webhook"] | None = None
    writeback_resource_path: str | None = Field(default=None, max_length=500)
    writeback_field_mapping: dict[str, str | int | float | bool | None] | None = None
    webhook_enabled: bool | None = None
    webhook_secret: str | None = Field(default=None, max_length=2000)


class DataConnectorRead(BaseModel):
    id: str
    program_id: str
    program_name: str
    name: str
    connector_type: str
    connector_label: str
    dataset_type: Literal["beneficiaries", "events"]
    status: str
    base_url: str
    resource_path: str
    auth_scheme: str
    auth_username: str | None = None
    has_secret: bool
    masked_secret: str | None = None
    record_path: str | None = None
    effective_record_path: str | None = None
    pagination_mode: str = "single_page"
    supports_incremental_sync: bool = False
    sync_state: dict[str, str | int | float | bool | None] = Field(default_factory=dict)
    query_params: dict[str, str | int | float | bool | None]
    field_mapping: dict[str, str | None]
    schedule_enabled: bool
    sync_interval_hours: int | None = None
    writeback_enabled: bool = False
    writeback_mode: str = "none"
    writeback_resource_path: str | None = None
    writeback_field_mapping: dict[str, str | int | float | bool | None] = Field(default_factory=dict)
    webhook_enabled: bool = False
    has_webhook_secret: bool = False
    masked_webhook_secret: str | None = None
    webhook_endpoint: str | None = None
    last_webhook_at: datetime | None = None
    last_synced_at: datetime | None = None
    last_dispatched_at: datetime | None = None
    next_sync_at: datetime | None = None
    last_error: str | None = None
    created_at: datetime


class ConnectorProbeResult(BaseModel):
    success: bool
    http_status: int | None = None
    record_count: int
    pages_fetched: int = 1
    sample_headers: list[str]
    inferred_mapping: dict[str, str | None] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    message: str


class ConnectorSyncRunRead(BaseModel):
    id: str
    connector_id: str
    connector_name: str
    program_name: str
    trigger_mode: str
    status: str
    records_fetched: int
    records_processed: int
    records_failed: int
    warnings: list[str]
    model_retrained: bool
    started_at: datetime
    completed_at: datetime | None = None
    triggered_by_email: str | None = None
    import_batch_id: str | None = None


class ConnectorDispatchRequest(BaseModel):
    only_due: bool = True
    include_this_week: bool = True
    limit: int = Field(default=100, ge=1, le=5000)
    preview_only: bool = False


class ConnectorDispatchRunRead(BaseModel):
    id: str
    connector_id: str
    connector_name: str
    program_name: str
    status: str
    target_mode: str
    records_sent: int
    cases_included: int
    cases_skipped: int
    warnings: list[str]
    payload_preview: dict[str, object] | None = None
    started_at: datetime
    completed_at: datetime | None = None
    triggered_by_email: str | None = None


class ModelScheduleRead(BaseModel):
    id: str
    enabled: bool
    cadence: Literal["manual", "weekly", "monthly"]
    auto_retrain_after_sync: bool
    last_run_at: datetime | None = None
    next_run_at: datetime | None = None
    updated_at: datetime


class ModelScheduleUpdate(BaseModel):
    cadence: Literal["manual", "weekly", "monthly"]
    enabled: bool = False
    auto_retrain_after_sync: bool = False


class DataQualityIssueRecord(BaseModel):
    id: str | None = None
    severity: Literal["info", "warning", "error"]
    issue_type: str
    field_name: str | None = None
    row_number: int | None = None
    message: str
    sample_value: str | None = None
    created_at: datetime | None = None


class ImportAnalysisRead(BaseModel):
    dataset_type: Literal["beneficiaries", "events"]
    source_format: Literal["csv", "xlsx"]
    records_received: int
    duplicate_rows: int
    inferred_types: dict[str, str]
    suggested_mapping: dict[str, str | None]
    quality_score: int = Field(ge=0, le=100)
    warnings: list[str]
    issues: list[DataQualityIssueRecord]
    available_columns: list[str]
    sample_rows: list[dict[str, str]]


class AutomationRunSummary(BaseModel):
    connectors_considered: int
    connector_runs_triggered: int
    connector_runs_failed: int
    model_retrained: bool
    model_status: ModelStatus | None = None
    sync_runs: list[ConnectorSyncRunRead]


class JobRead(BaseModel):
    id: str
    job_type: Literal["connector_sync", "model_train", "automation_run_due"]
    status: Literal["queued", "running", "succeeded", "failed", "dead_letter"]
    payload: dict[str, str | int | float | bool | None]
    result: dict[str, str | int | float | bool | None] | None = None
    error_message: str | None = None
    attempts: int
    max_attempts: int
    retry_backoff_seconds: int
    available_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
    last_error_at: datetime | None = None
    dead_lettered_at: datetime | None = None
    created_at: datetime
    created_by_email: str | None = None


class JobRunRequest(BaseModel):
    max_jobs: int = Field(default=10, ge=1, le=100)


class JobRunSummary(BaseModel):
    requested: int
    processed: int
    jobs: list[JobRead]


class ProgramCreate(BaseModel):
    name: str = Field(min_length=3, max_length=255)
    program_type: str = Field(min_length=3, max_length=100)
    country: str = Field(min_length=2, max_length=100)
    delivery_modality: str | None = Field(default=None, max_length=100)


class ProgramRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    program_type: str
    country: str
    delivery_modality: str | None
    status: str
    created_at: datetime


class BeneficiaryGovernanceRecord(BaseModel):
    id: str
    full_name: str
    external_id_masked: str
    pii_token: str | None = None
    program_name: str
    region: str
    status: str
    opted_out: bool
    modeling_consent_status: Literal["granted", "pending", "declined", "withdrawn", "waived"]
    consent_captured_at: datetime | None = None
    consent_explained_at: datetime | None = None
    consent_method: str | None = None
    consent_note: str | None = None
    risk_level: Literal["High", "Medium", "Low"]
    risk_score: int = Field(ge=0, le=100)
    last_contact_days: int
    last_intervention_at: datetime | None = None


class BeneficiaryGovernanceUpdate(BaseModel):
    opted_out: bool
    modeling_consent_status: Literal["granted", "pending", "declined", "withdrawn", "waived"] | None = None
    consent_method: str | None = Field(default=None, max_length=80)
    consent_note: str | None = Field(default=None, max_length=1000)
    explained_to_beneficiary: bool | None = None


class GovernanceAlert(BaseModel):
    beneficiary_id: str
    beneficiary_name: str
    program_name: str
    region: str
    alert_level: Literal["warning", "attention"]
    dropout_date: str
    risk_level: Literal["High", "Medium", "Low"]
    note: str


class ExportRequest(BaseModel):
    purpose: str = Field(min_length=5, max_length=250)
    include_pii: bool = False


class RiskQueueExportRequest(ExportRequest):
    program_id: str | None = None
    risk_level: Literal["High", "Medium", "Low"] | None = None
    region: str | None = None
    cohort: str | None = None
    phase: str | None = None
    search: str | None = None


class ModelDriver(BaseModel):
    name: str
    weight: float
    direction: Literal["increases_risk", "reduces_risk"]


class BiasAuditGroup(BaseModel):
    group_name: str
    sample_size: int
    positive_count: int
    predicted_positive_count: int
    flagged_rate: float | None = None
    false_positive_rate: float | None = None
    recall_rate: float | None = None
    severity: Literal["ok", "attention", "insufficient_data"]
    guidance: str | None = None


class BiasAuditDimension(BaseModel):
    dimension: str
    status: Literal["ok", "attention", "insufficient_data"]
    note: str
    max_false_positive_gap: float | None = None
    max_recall_gap: float | None = None
    groups: list[BiasAuditGroup]


class BiasAuditSummary(BaseModel):
    status: Literal["ok", "attention", "insufficient_data"]
    note: str
    dimensions: list[BiasAuditDimension]


class DriftFeatureReport(BaseModel):
    feature_name: str
    psi: float
    status: Literal["ok", "attention"]
    note: str


class ModelDriftReportRead(BaseModel):
    id: str | None = None
    status: Literal["ok", "attention", "insufficient_data"]
    overall_psi: float
    note: str
    monitored_at: str | None = None
    feature_reports: list[DriftFeatureReport]


class FeatureStoreSummary(BaseModel):
    total_snapshots: int
    training_snapshots: int
    scoring_snapshots: int
    latest_snapshot_at: datetime | None = None
    latest_model_version_id: str | None = None


class ModelStatus(BaseModel):
    id: str | None = None
    model_mode: str
    algorithm: str
    status: str
    mlflow_run_id: str | None = None
    trained_at: str | None = None
    training_rows: int
    positive_rows: int
    feature_count: int
    metrics: dict[str, float | int | str]
    top_drivers: list[ModelDriver]
    notes: str | None = None
    fallback_active: bool
    bias_audit: BiasAuditSummary | None = None
    drift_report: ModelDriftReportRead | None = None


class TrainingRequest(BaseModel):
    force: bool = False


class EvaluationRequest(BaseModel):
    temporal_strategy: Literal["holdout", "rolling"] = "rolling"
    horizon_days: int = Field(default=30, ge=7, le=180)
    min_history_days: int = Field(default=60, ge=14, le=365)
    holdout_share: float = Field(default=0.25, ge=0.1, le=0.5)
    rolling_folds: int = Field(default=4, ge=2, le=8)
    program_ids: list[str] = Field(default_factory=list)
    cohorts: list[str] = Field(default_factory=list)
    top_k_share: float = Field(default=0.2, ge=0.01, le=0.5)
    top_k_capacity: int | None = Field(default=None, ge=1, le=100000)
    calibration_bins: int = Field(default=5, ge=3, le=10)
    bootstrap_iterations: int = Field(default=100, ge=20, le=500)


class EvaluationMetricInterval(BaseModel):
    value: float
    lower_ci: float | None = None
    upper_ci: float | None = None


class EvaluationMetrics(BaseModel):
    auc_roc: EvaluationMetricInterval
    pr_auc: EvaluationMetricInterval
    precision: EvaluationMetricInterval
    recall: EvaluationMetricInterval
    f1: EvaluationMetricInterval
    brier_score: EvaluationMetricInterval
    top_k_precision: EvaluationMetricInterval
    top_k_recall: EvaluationMetricInterval
    top_k_lift: EvaluationMetricInterval
    expected_calibration_error: EvaluationMetricInterval


class CalibrationBin(BaseModel):
    bin_index: int
    lower_bound: float
    upper_bound: float
    predicted_rate: float
    observed_rate: float
    count: int


class EvaluationSplitSummary(BaseModel):
    temporal_strategy: Literal["holdout", "rolling", "segment_holdout"]
    train_cases: int
    test_cases: int
    train_positive_rate: float
    test_positive_rate: float
    train_start: str
    train_end: str
    test_start: str
    test_end: str
    folds_considered: int = 1
    folds_used: int = 1
    balanced_folds: int = 1
    aggregation_note: str | None = None


class ModelEvaluationReport(BaseModel):
    status: Literal["ready_for_shadow_mode", "needs_more_data", "not_ready"]
    note: str
    algorithm: str
    horizon_days: int
    min_history_days: int
    top_k_share: float
    top_k_count: int
    samples_evaluated: int
    positive_cases: int
    split: EvaluationSplitSummary
    metrics: EvaluationMetrics
    calibration: list[CalibrationBin]
    fairness_audit: BiasAuditSummary | None = None


class ImportBatchRead(BaseModel):
    id: str
    program_id: str
    program_name: str
    dataset_type: str
    source_format: str
    filename: str
    records_received: int
    records_processed: int
    records_failed: int
    duplicates_detected: int
    resolved_mapping: dict[str, str | None]
    warnings: list[str]
    quality_summary: dict[str, str | int | float | bool | None] | None = None
    created_at: datetime


class TopRiskDriver(BaseModel):
    name: str
    impacted_beneficiaries: int
    insight: str


class RegionAlert(BaseModel):
    region: str
    retention_delta: float
    note: str


class DashboardSummary(BaseModel):
    active_beneficiaries: int
    high_risk_cases: int
    predicted_30_day_dropout: int
    intervention_success_rate: int
    weekly_followups_due: int
    model_mode: str
    last_retrained: str
    quality_note: str
    top_risk_drivers: list[TopRiskDriver]
    region_alerts: list[RegionAlert]
    model_status: ModelStatus


class SoftSignalSnapshot(BaseModel):
    household_stability_signal: int | None = Field(default=None, ge=1, le=5)
    economic_stress_signal: int | None = Field(default=None, ge=1, le=5)
    family_support_signal: int | None = Field(default=None, ge=1, le=5)
    health_change_signal: int | None = Field(default=None, ge=1, le=5)
    motivation_signal: int | None = Field(default=None, ge=1, le=5)


class TracingProtocolState(BaseModel):
    current_step: Literal["sms", "call", "visit"]
    current_channel: Literal["sms", "call", "visit", "whatsapp", "manual"]
    current_due_at: datetime | None = None
    next_step: Literal["sms", "call", "visit"] | None = None
    next_due_at: datetime | None = None
    sms_delay_days: int
    call_delay_days: int
    visit_delay_days: int


class FollowUpWorkflowState(BaseModel):
    intervention_id: str | None = None
    status: Literal["queued", "attempted", "reached", "verified", "dismissed", "closed", "escalated"] | None = None
    verification_status: Literal[
        "pending",
        "still_enrolled",
        "re_engaged",
        "silent_transfer",
        "completed_elsewhere",
        "deceased",
        "unreachable",
        "declined_support",
        "dropped_out_confirmed",
    ] | None = None
    assigned_to: str | None = None
    assigned_site: str | None = None
    due_at: datetime | None = None
    completed_at: datetime | None = None
    verified_at: datetime | None = None
    note: str | None = None
    verification_note: str | None = None
    dismissal_reason: str | None = None
    support_channel: str | None = None
    protocol_step: Literal["sms", "call", "visit"] | None = None
    attempt_count: int = 0
    successful: bool | None = None
    tracing_protocol: TracingProtocolState | None = None


class RiskCase(BaseModel):
    id: str
    name: str
    program: str
    program_type: str
    region: str
    cohort: str | None
    phase: str | None
    risk_level: Literal["High", "Medium", "Low"]
    risk_score: int = Field(ge=0, le=100)
    explanation: str
    recommended_action: str
    flags: list[str]
    last_contact_days: int
    attendance_rate_30d: int
    intervention_status: str
    confidence: Literal["High confidence", "Limited data", "Opted out of modeling", "Consent required"]
    opted_out: bool = False
    assigned_worker: str | None = None
    assigned_site: str | None = None
    queue_rank: int = Field(default=0, ge=0)
    queue_bucket: Literal["Due now", "This week", "Monitor"]
    workflow: FollowUpWorkflowState | None = None
    tracing_protocol: TracingProtocolState | None = None
    soft_signals: SoftSignalSnapshot | None = None


class RetentionSeries(BaseModel):
    key: str
    label: str
    color: str


class RetentionCurves(BaseModel):
    narrative: str
    series: list[RetentionSeries]
    data: list[dict[str, str | float]]


class ProgramOperationalSettingRead(BaseModel):
    id: str
    program_id: str
    weekly_followup_capacity: int
    worker_count: int
    medium_risk_multiplier: float
    high_risk_share_floor: float
    review_window_days: int
    label_definition_preset: Literal["health_28d", "education_10d", "cct_missed_cycle", "custom"]
    dropout_inactivity_days: int
    prediction_window_days: int
    label_noise_strategy: Literal["strict", "operational_soft_labels"]
    soft_label_weight: float
    silent_transfer_detection_enabled: bool
    low_risk_channel: Literal["sms", "call", "visit", "whatsapp", "manual"]
    medium_risk_channel: Literal["sms", "call", "visit", "whatsapp", "manual"]
    high_risk_channel: Literal["sms", "call", "visit", "whatsapp", "manual"]
    tracing_sms_delay_days: int
    tracing_call_delay_days: int
    tracing_visit_delay_days: int
    escalation_window_days: int
    escalation_max_attempts: int
    fairness_reweighting_enabled: bool
    fairness_target_dimensions: list[str]
    fairness_max_gap: float
    fairness_min_group_size: int
    updated_at: datetime


class ProgramOperationalSettingUpdate(BaseModel):
    weekly_followup_capacity: int = Field(default=30, ge=1, le=10000)
    worker_count: int = Field(default=4, ge=1, le=5000)
    medium_risk_multiplier: float = Field(default=2.0, ge=1.0, le=10.0)
    high_risk_share_floor: float = Field(default=0.08, ge=0.01, le=0.8)
    review_window_days: int = Field(default=30, ge=7, le=365)
    label_definition_preset: Literal["health_28d", "education_10d", "cct_missed_cycle", "custom"] = "custom"
    dropout_inactivity_days: int = Field(default=30, ge=7, le=365)
    prediction_window_days: int = Field(default=30, ge=7, le=90)
    label_noise_strategy: Literal["strict", "operational_soft_labels"] = "operational_soft_labels"
    soft_label_weight: float = Field(default=0.35, ge=0.05, le=1.0)
    silent_transfer_detection_enabled: bool = True
    low_risk_channel: Literal["sms", "call", "visit", "whatsapp", "manual"] = "sms"
    medium_risk_channel: Literal["sms", "call", "visit", "whatsapp", "manual"] = "call"
    high_risk_channel: Literal["sms", "call", "visit", "whatsapp", "manual"] = "visit"
    tracing_sms_delay_days: int = Field(default=3, ge=0, le=30)
    tracing_call_delay_days: int = Field(default=7, ge=1, le=45)
    tracing_visit_delay_days: int = Field(default=14, ge=1, le=90)
    escalation_window_days: int = Field(default=7, ge=1, le=60)
    escalation_max_attempts: int = Field(default=2, ge=1, le=10)
    fairness_reweighting_enabled: bool = False
    fairness_target_dimensions: list[str] = Field(default_factory=lambda: ["gender", "region", "household_type"])
    fairness_max_gap: float = Field(default=0.15, ge=0.01, le=0.5)
    fairness_min_group_size: int = Field(default=20, ge=5, le=500)


class ProgramValidationSettingRead(BaseModel):
    id: str
    program_id: str
    shadow_mode_enabled: bool
    shadow_prediction_window_days: int
    minimum_precision_at_capacity: float
    minimum_recall_at_capacity: float
    require_fairness_review: bool
    last_evaluation_status: str | None = None
    last_shadow_run_at: datetime | None = None
    updated_at: datetime


class ProgramValidationSettingUpdate(BaseModel):
    shadow_mode_enabled: bool = False
    shadow_prediction_window_days: int = Field(default=30, ge=7, le=90)
    minimum_precision_at_capacity: float = Field(default=0.7, ge=0.05, le=1.0)
    minimum_recall_at_capacity: float = Field(default=0.5, ge=0.05, le=1.0)
    require_fairness_review: bool = True


class ProgramDataPolicyRead(BaseModel):
    id: str
    program_id: str
    storage_mode: Literal["self_hosted", "managed_region"]
    data_residency_region: str
    cross_border_transfers_allowed: bool
    pii_tokenization_enabled: bool
    consent_required: bool
    federated_learning_enabled: bool
    updated_at: datetime


class ProgramDataPolicyUpdate(BaseModel):
    storage_mode: Literal["self_hosted", "managed_region"] = "self_hosted"
    data_residency_region: str = Field(default="eu-central", min_length=2, max_length=80)
    cross_border_transfers_allowed: bool = False
    pii_tokenization_enabled: bool = True
    consent_required: bool = True
    federated_learning_enabled: bool = True


class RetentionBreakdownRow(BaseModel):
    dimension: str
    group_name: str
    active_beneficiaries: int
    dropped_beneficiaries: int
    retention_rate: float
    recent_dropout_rate: float


class RetentionTrendRow(BaseModel):
    period: str
    program_name: str
    region: str
    retention_rate: float
    dropout_rate: float
    active_beneficiaries: int


class RetentionAnalytics(BaseModel):
    narrative: str
    breakdowns: list[RetentionBreakdownRow]
    trend_rows: list[RetentionTrendRow]
    trend_highlights: list[str]
    retention_curves: RetentionCurves


class InterventionEffectivenessRow(BaseModel):
    action_type: str
    context_label: str
    attempts: int
    successful_interventions: int
    success_rate: float
    avg_risk_score: float
    recommendation_strength: Literal["high", "medium", "low"]


class InterventionEffectivenessSummary(BaseModel):
    narrative: str
    total_logged_interventions: int
    outcome_labeled_interventions: int
    rows: list[InterventionEffectivenessRow]
    top_recommendations: list[str]


class ModelEvaluationRecordRead(BaseModel):
    id: str
    created_by_email: str | None = None
    program_ids: list[str]
    cohorts: list[str]
    temporal_strategy: Literal["holdout", "rolling", "segment_holdout"]
    status: Literal["ready_for_shadow_mode", "needs_more_data", "not_ready"]
    algorithm: str
    horizon_days: int
    samples_evaluated: int
    positive_cases: int
    created_at: datetime
    report: ModelEvaluationReport


class ShadowRunCreateRequest(BaseModel):
    top_k_count: int | None = Field(default=None, ge=1, le=100000)
    note: str | None = Field(default=None, max_length=500)


class ShadowRunRead(BaseModel):
    id: str
    program_id: str
    program_name: str
    status: Literal["captured", "partial_followup", "matured", "insufficient_followup"]
    snapshot_date: str
    horizon_days: int
    top_k_count: int
    cases_captured: int
    high_risk_cases: int
    due_now_cases: int
    matured_cases: int
    observed_positive_cases: int
    actioned_cases: int
    top_k_precision: float | None = None
    top_k_recall: float | None = None
    note: str | None = None
    created_by_email: str | None = None
    created_at: datetime
    completed_at: datetime | None = None


class DonorReportSummary(BaseModel):
    generated_at: str
    narrative: str
    headline_metrics: dict[str, float | int | str]
    retention_analytics: RetentionAnalytics
    intervention_effectiveness: InterventionEffectivenessSummary


class FederatedModelUpdateRead(BaseModel):
    id: str
    round_id: str
    source_program_id: str | None = None
    model_version_id: str | None = None
    deployment_label: str
    source_nonce: str | None = None
    update_fingerprint: str | None = None
    training_rows: int
    positive_rows: int
    payload: dict[str, object]
    created_at: datetime
    verified_at: datetime | None = None


class FederatedLearningRoundRead(BaseModel):
    id: str
    round_name: str
    round_nonce: str
    status: str
    aggregation_note: str | None = None
    aggregated_payload: dict[str, object] | None = None
    created_at: datetime
    completed_at: datetime | None = None
    updates: list[FederatedModelUpdateRead]


class FederatedUpdateRequest(BaseModel):
    round_name: str = Field(min_length=3, max_length=120)
    deployment_label: str = Field(min_length=3, max_length=120)
    source_program_id: str | None = None
    program_type: str | None = None


class FederatedAggregateRequest(BaseModel):
    round_name: str = Field(min_length=3, max_length=120)
    close_round: bool = True


class SSOConfigRead(BaseModel):
    enabled: bool
    mode: Literal["disabled", "header", "oidc"] = "disabled"
    provider_label: str | None = None
    interactive: bool = False
    start_path: str | None = None
    callback_supported: bool = False


class SSOOidcStartRead(BaseModel):
    authorization_url: str
    state: str
    provider_label: str


class SSOOidcExchangeRequest(BaseModel):
    code: str = Field(min_length=3, max_length=4000)
    state: str = Field(min_length=10, max_length=4000)
    redirect_uri: str = Field(min_length=8, max_length=1000)


class BeneficiaryExplanationRead(BaseModel):
    beneficiary_id: str
    beneficiary_label: str
    program_name: str
    risk_level: Literal["High", "Medium", "Low"]
    explanation: str
    beneficiary_facing_summary: str
    confidence: str
    translated_ready_note: str
    data_points_used: list[str]
    support_recommendation: str


class RuntimePolicyIssue(BaseModel):
    program_id: str
    program_name: str
    issue: str


class RuntimeStatusRead(BaseModel):
    status: Literal["ok", "attention"]
    deployment_region: str
    job_backend: str
    enforce_runtime_policy: bool
    violations: list[RuntimePolicyIssue]
    warnings: list[str]


class WorkerHealthRead(BaseModel):
    backend: str
    status: Literal["healthy", "attention"]
    queued: int
    running: int
    failed: int
    dead_letter: int
    worker_status: str
    workers: list[str]
    next_ready_at: datetime | None = None
    oldest_queue_age_seconds: int | None = None
    retry_backoff_seconds: int
    max_attempts: int
    stalled_threshold_seconds: int


class SyntheticProgramBundleSummary(BaseModel):
    program_type: str
    beneficiaries: int
    events: int
    dropout_rate: float
    regions: dict[str, int]


class SyntheticStressScenarioRead(BaseModel):
    name: str
    description: str


class SyntheticStressProgramSummary(BaseModel):
    program_type: str
    scenario: str
    beneficiaries: int
    events: int
    dropout_rate: float


class BeneficiarySoftSignalsUpdate(BaseModel):
    household_stability_signal: int | None = Field(default=None, ge=1, le=5)
    economic_stress_signal: int | None = Field(default=None, ge=1, le=5)
    family_support_signal: int | None = Field(default=None, ge=1, le=5)
    health_change_signal: int | None = Field(default=None, ge=1, le=5)
    motivation_signal: int | None = Field(default=None, ge=1, le=5)


class InterventionRequest(BaseModel):
    beneficiary_id: str
    action_type: str = Field(min_length=3, max_length=120)
    support_channel: Literal["sms", "call", "visit", "whatsapp", "manual"] | None = None
    protocol_step: Literal["sms", "call", "visit"] | None = None
    status: Literal["queued", "attempted", "reached", "verified", "dismissed", "closed", "escalated"] = "queued"
    verification_status: Literal[
        "pending",
        "still_enrolled",
        "re_engaged",
        "silent_transfer",
        "completed_elsewhere",
        "deceased",
        "unreachable",
        "declined_support",
        "dropped_out_confirmed",
    ] | None = None
    assigned_to: str | None = Field(default=None, max_length=120)
    assigned_site: str | None = Field(default=None, max_length=120)
    due_at: datetime | None = None
    verification_note: str | None = Field(default=None, max_length=2000)
    dismissal_reason: str | None = Field(default=None, max_length=255)
    attempt_count: int = Field(default=0, ge=0, le=100)
    source: str = Field(default="risk_queue", max_length=40)
    risk_level: Literal["High", "Medium", "Low"] | None = None
    priority_rank: int | None = Field(default=None, ge=1, le=100000)
    note: str | None = Field(default=None, max_length=1000)
    successful: bool | None = None
    soft_signals: BeneficiarySoftSignalsUpdate | None = None


class InterventionUpdate(BaseModel):
    action_type: str | None = Field(default=None, min_length=3, max_length=120)
    support_channel: Literal["sms", "call", "visit", "whatsapp", "manual"] | None = None
    protocol_step: Literal["sms", "call", "visit"] | None = None
    status: Literal["queued", "attempted", "reached", "verified", "dismissed", "closed", "escalated"] | None = None
    verification_status: Literal[
        "pending",
        "still_enrolled",
        "re_engaged",
        "silent_transfer",
        "completed_elsewhere",
        "deceased",
        "unreachable",
        "declined_support",
        "dropped_out_confirmed",
    ] | None = None
    assigned_to: str | None = Field(default=None, max_length=120)
    assigned_site: str | None = Field(default=None, max_length=120)
    due_at: datetime | None = None
    verification_note: str | None = Field(default=None, max_length=2000)
    dismissal_reason: str | None = Field(default=None, max_length=255)
    attempt_count: int | None = Field(default=None, ge=0, le=100)
    note: str | None = Field(default=None, max_length=1000)
    successful: bool | None = None
    soft_signals: BeneficiarySoftSignalsUpdate | None = None


class InterventionRecord(BaseModel):
    id: str
    beneficiary_id: str
    beneficiary_name: str
    action_type: str
    support_channel: str | None = None
    protocol_step: Literal["sms", "call", "visit"] | None = None
    status: str
    verification_status: str | None = None
    assigned_to: str | None = None
    assigned_site: str | None = None
    due_at: str | None = None
    completed_at: str | None = None
    verified_at: str | None = None
    verification_note: str | None = None
    dismissal_reason: str | None = None
    attempt_count: int = 0
    source: str
    risk_level: str | None = None
    priority_rank: int | None = None
    note: str | None = None
    successful: bool | None = None
    soft_signals: SoftSignalSnapshot | None = None
    logged_at: str


class AuditLogRecord(BaseModel):
    id: str
    actor_email: str | None = None
    actor_role: str | None = None
    action: str
    resource_type: str
    resource_id: str | None = None
    details: dict[str, str | int | float | bool | None] | None = None
    ip_address: str | None = None
    created_at: datetime
