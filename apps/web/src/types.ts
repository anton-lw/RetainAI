/**
 * Shared TypeScript models for the RetainAI frontend.
 *
 * These interfaces intentionally mirror the FastAPI schema layer closely. They
 * are not domain models invented just for the UI; they are the typed contract
 * used by sections throughout the dashboard and by the browser-based tests.
 *
 * Maintainers should update this file whenever backend response models change
 * so that type errors surface quickly during frontend builds.
 */

export type RiskLevel = "High" | "Medium" | "Low";
export type DatasetType = "beneficiaries" | "events";
export type UserRole = "admin" | "me_officer" | "field_coordinator" | "country_director";
export type ConnectorType = "kobotoolbox" | "commcare" | "odk_central" | "dhis2" | "salesforce_npsp";
export type AuthScheme = "none" | "bearer" | "token" | "basic";
export type ModelCadence = "manual" | "weekly" | "monthly";

export interface HealthStatus {
  status: string;
  environment: string;
  database_configured: boolean;
  programs: number;
}

export interface LoginPayload {
  email: string;
  password: string;
}

export interface CurrentUser {
  id: string;
  full_name: string;
  email: string;
  role: UserRole;
  is_active: boolean;
  last_login_at?: string | null;
  created_at: string;
}

export interface AuthSession {
  access_token: string;
  token_type: string;
  expires_in_seconds: number;
  session_id?: string | null;
  user: CurrentUser;
}

export interface SessionRecord {
  id: string;
  auth_method: string;
  token_key_id: string;
  source_ip?: string | null;
  user_agent?: string | null;
  issued_at: string;
  expires_at: string;
  last_seen_at: string;
  revoked_at?: string | null;
  revoked_reason?: string | null;
}

export interface Program {
  id: string;
  name: string;
  program_type: string;
  country: string;
  delivery_modality?: string | null;
  status: string;
  created_at: string;
}

export interface ProgramCreatePayload {
  name: string;
  program_type: string;
  country: string;
  delivery_modality?: string;
}

export interface BeneficiaryGovernanceRecord {
  id: string;
  full_name: string;
  external_id_masked: string;
  pii_token?: string | null;
  program_name: string;
  region: string;
  status: string;
  opted_out: boolean;
  modeling_consent_status: "granted" | "pending" | "declined" | "withdrawn" | "waived";
  consent_captured_at?: string | null;
  consent_explained_at?: string | null;
  consent_method?: string | null;
  consent_note?: string | null;
  risk_level: RiskLevel;
  risk_score: number;
  last_contact_days: number;
  last_intervention_at?: string | null;
}

export interface BeneficiaryGovernanceUpdatePayload {
  opted_out: boolean;
  modeling_consent_status?: "granted" | "pending" | "declined" | "withdrawn" | "waived";
  consent_method?: string;
  consent_note?: string;
  explained_to_beneficiary?: boolean;
}

export interface GovernanceAlert {
  beneficiary_id: string;
  beneficiary_name: string;
  program_name: string;
  region: string;
  alert_level: "warning" | "attention";
  dropout_date: string;
  risk_level: RiskLevel;
  note: string;
}

export interface DataConnector {
  id: string;
  program_id: string;
  program_name: string;
  name: string;
  connector_type: ConnectorType | string;
  connector_label: string;
  dataset_type: DatasetType;
  status: string;
  base_url: string;
  resource_path: string;
  auth_scheme: AuthScheme;
  auth_username?: string | null;
  has_secret: boolean;
  masked_secret?: string | null;
  record_path?: string | null;
  effective_record_path?: string | null;
  pagination_mode: string;
  supports_incremental_sync: boolean;
  sync_state: Record<string, string | number | boolean | null>;
  query_params: Record<string, string | number | boolean | null>;
  field_mapping: Record<string, string | null>;
  schedule_enabled: boolean;
  sync_interval_hours?: number | null;
  writeback_enabled: boolean;
  writeback_mode: "none" | "commcare_case_updates" | "dhis2_working_list" | "generic_webhook";
  writeback_resource_path?: string | null;
  writeback_field_mapping: Record<string, string | number | boolean | null>;
  webhook_enabled: boolean;
  has_webhook_secret: boolean;
  masked_webhook_secret?: string | null;
  webhook_endpoint?: string | null;
  last_webhook_at?: string | null;
  last_synced_at?: string | null;
  last_dispatched_at?: string | null;
  next_sync_at?: string | null;
  last_error?: string | null;
  created_at: string;
}

export interface DataConnectorCreatePayload {
  program_id: string;
  name: string;
  connector_type: ConnectorType;
  dataset_type: DatasetType;
  base_url: string;
  resource_path: string;
  auth_scheme: AuthScheme;
  auth_username?: string;
  secret?: string;
  record_path?: string;
  query_params: Record<string, string | number | boolean | null>;
  field_mapping: Record<string, string | null>;
  schedule_enabled: boolean;
  sync_interval_hours?: number | null;
  writeback_enabled?: boolean;
  writeback_mode?: "none" | "commcare_case_updates" | "dhis2_working_list" | "generic_webhook";
  writeback_resource_path?: string;
  writeback_field_mapping?: Record<string, string | number | boolean | null>;
  webhook_enabled?: boolean;
  webhook_secret?: string;
}

export interface DataConnectorSyncRun {
  id: string;
  connector_id: string;
  connector_name: string;
  program_name: string;
  trigger_mode: string;
  status: string;
  records_fetched: number;
  records_processed: number;
  records_failed: number;
  warnings: string[];
  model_retrained: boolean;
  started_at: string;
  completed_at?: string | null;
  triggered_by_email?: string | null;
  import_batch_id?: string | null;
}

export interface ConnectorDispatchRun {
  id: string;
  connector_id: string;
  connector_name: string;
  program_name: string;
  status: string;
  target_mode: string;
  records_sent: number;
  cases_included: number;
  cases_skipped: number;
  warnings: string[];
  payload_preview?: Record<string, unknown> | null;
  started_at: string;
  completed_at?: string | null;
  triggered_by_email?: string | null;
}

export interface ConnectorProbeResult {
  success: boolean;
  http_status?: number | null;
  record_count: number;
  pages_fetched: number;
  sample_headers: string[];
  inferred_mapping: Record<string, string | null>;
  warnings: string[];
  message: string;
}

export interface DataQualityIssueRecord {
  id?: string | null;
  severity: "info" | "warning" | "error";
  issue_type: string;
  field_name?: string | null;
  row_number?: number | null;
  message: string;
  sample_value?: string | null;
  created_at?: string | null;
}

export interface ImportAnalysis {
  dataset_type: DatasetType;
  source_format: "csv" | "xlsx";
  records_received: number;
  duplicate_rows: number;
  inferred_types: Record<string, string>;
  suggested_mapping: Record<string, string | null>;
  quality_score: number;
  warnings: string[];
  issues: DataQualityIssueRecord[];
  available_columns: string[];
  sample_rows: Array<Record<string, string>>;
}

export interface ModelSchedule {
  id: string;
  enabled: boolean;
  cadence: ModelCadence;
  auto_retrain_after_sync: boolean;
  last_run_at?: string | null;
  next_run_at?: string | null;
  updated_at: string;
}

export interface ModelScheduleUpdatePayload {
  cadence: ModelCadence;
  enabled: boolean;
  auto_retrain_after_sync: boolean;
}

export interface AutomationRunSummary {
  connectors_considered: number;
  connector_runs_triggered: number;
  connector_runs_failed: number;
  model_retrained: boolean;
  model_status?: ModelStatus | null;
  sync_runs: DataConnectorSyncRun[];
}

export interface JobRecord {
  id: string;
  job_type: "connector_sync" | "model_train" | "automation_run_due";
  status: "queued" | "running" | "succeeded" | "failed" | "dead_letter";
  payload: Record<string, string | number | boolean | null>;
  result?: Record<string, string | number | boolean | null> | null;
  error_message?: string | null;
  attempts: number;
  max_attempts: number;
  retry_backoff_seconds: number;
  available_at: string;
  started_at?: string | null;
  completed_at?: string | null;
  last_error_at?: string | null;
  dead_lettered_at?: string | null;
  created_at: string;
  created_by_email?: string | null;
}

export interface JobRunSummary {
  requested: number;
  processed: number;
  jobs: JobRecord[];
}

export interface ModelDriver {
  name: string;
  weight: number;
  direction: "increases_risk" | "reduces_risk";
}

export interface BiasAuditGroup {
  group_name: string;
  sample_size: number;
  positive_count: number;
  predicted_positive_count: number;
  flagged_rate?: number | null;
  false_positive_rate?: number | null;
  recall_rate?: number | null;
  severity: "ok" | "attention" | "insufficient_data";
  guidance?: string | null;
}

export interface BiasAuditDimension {
  dimension: string;
  status: "ok" | "attention" | "insufficient_data";
  note: string;
  max_false_positive_gap?: number | null;
  max_recall_gap?: number | null;
  groups: BiasAuditGroup[];
}

export interface BiasAuditSummary {
  status: "ok" | "attention" | "insufficient_data";
  note: string;
  dimensions: BiasAuditDimension[];
}

export interface ModelStatus {
  id?: string | null;
  model_mode: string;
  algorithm: string;
  status: string;
  mlflow_run_id?: string | null;
  trained_at?: string | null;
  training_rows: number;
  positive_rows: number;
  feature_count: number;
  metrics: Record<string, string | number>;
  top_drivers: ModelDriver[];
  notes?: string | null;
  fallback_active: boolean;
  bias_audit?: BiasAuditSummary | null;
  drift_report?: {
    id?: string | null;
    status: "ok" | "attention" | "insufficient_data";
    overall_psi: number;
    note: string;
    monitored_at?: string | null;
    feature_reports: Array<{
      feature_name: string;
      psi: number;
      status: "ok" | "attention";
      note: string;
    }>;
  } | null;
}

export interface ImportBatch {
  id: string;
  program_id: string;
  program_name: string;
  dataset_type: string;
  source_format: string;
  filename: string;
  records_received: number;
  records_processed: number;
  records_failed: number;
  duplicates_detected: number;
  resolved_mapping: Record<string, string | null>;
  warnings: string[];
  quality_summary?: Record<string, string | number | boolean | null> | null;
  created_at: string;
}

export interface TopRiskDriver {
  name: string;
  impacted_beneficiaries: number;
  insight: string;
}

export interface RegionAlert {
  region: string;
  retention_delta: number;
  note: string;
}

export interface DashboardSummary {
  active_beneficiaries: number;
  high_risk_cases: number;
  predicted_30_day_dropout: number;
  intervention_success_rate: number;
  weekly_followups_due: number;
  model_mode: string;
  last_retrained: string;
  quality_note: string;
  top_risk_drivers: TopRiskDriver[];
  region_alerts: RegionAlert[];
  model_status: ModelStatus;
}

export interface SoftSignalSnapshot {
  household_stability_signal?: number | null;
  economic_stress_signal?: number | null;
  family_support_signal?: number | null;
  health_change_signal?: number | null;
  motivation_signal?: number | null;
}

export interface FollowUpWorkflowState {
  intervention_id?: string | null;
  status?: "queued" | "attempted" | "reached" | "verified" | "dismissed" | "closed" | "escalated" | null;
  verification_status?:
    | "pending"
    | "still_enrolled"
    | "re_engaged"
    | "silent_transfer"
    | "completed_elsewhere"
    | "deceased"
    | "unreachable"
    | "declined_support"
    | "dropped_out_confirmed"
    | null;
  assigned_to?: string | null;
  assigned_site?: string | null;
  due_at?: string | null;
  completed_at?: string | null;
  verified_at?: string | null;
  note?: string | null;
  verification_note?: string | null;
  dismissal_reason?: string | null;
  support_channel?: "sms" | "call" | "visit" | "whatsapp" | "manual" | null;
  protocol_step?: "sms" | "call" | "visit" | null;
  attempt_count: number;
  successful?: boolean | null;
  tracing_protocol?: TracingProtocolState | null;
}

export interface TracingProtocolState {
  current_step: "sms" | "call" | "visit";
  current_channel: "sms" | "call" | "visit" | "whatsapp" | "manual";
  current_due_at?: string | null;
  next_step?: "sms" | "call" | "visit" | null;
  next_due_at?: string | null;
  sms_delay_days: number;
  call_delay_days: number;
  visit_delay_days: number;
}

export interface RiskCase {
  id: string;
  name: string;
  program: string;
  program_type: string;
  region: string;
  cohort?: string | null;
  phase?: string | null;
  risk_level: RiskLevel;
  risk_score: number;
  explanation: string;
  recommended_action: string;
  flags: string[];
  last_contact_days: number;
  attendance_rate_30d: number;
  intervention_status: string;
  confidence: "High confidence" | "Limited data" | "Opted out of modeling" | "Consent required";
  opted_out: boolean;
  assigned_worker?: string | null;
  assigned_site?: string | null;
  queue_rank: number;
  queue_bucket: "Due now" | "This week" | "Monitor";
  workflow?: FollowUpWorkflowState | null;
  tracing_protocol?: TracingProtocolState | null;
  soft_signals?: SoftSignalSnapshot | null;
}

export interface RetentionSeries {
  key: string;
  label: string;
  color: string;
}

export interface RetentionCurves {
  narrative: string;
  series: RetentionSeries[];
  data: Array<Record<string, string | number>>;
}

export interface ProgramOperationalSetting {
  id: string;
  program_id: string;
  weekly_followup_capacity: number;
  worker_count: number;
  medium_risk_multiplier: number;
  high_risk_share_floor: number;
  review_window_days: number;
  label_definition_preset: "health_28d" | "education_10d" | "cct_missed_cycle" | "custom";
  dropout_inactivity_days: number;
  prediction_window_days: number;
  label_noise_strategy: "strict" | "operational_soft_labels";
  soft_label_weight: number;
  silent_transfer_detection_enabled: boolean;
  low_risk_channel: "sms" | "call" | "visit" | "whatsapp" | "manual";
  medium_risk_channel: "sms" | "call" | "visit" | "whatsapp" | "manual";
  high_risk_channel: "sms" | "call" | "visit" | "whatsapp" | "manual";
  tracing_sms_delay_days: number;
  tracing_call_delay_days: number;
  tracing_visit_delay_days: number;
  escalation_window_days: number;
  escalation_max_attempts: number;
  fairness_reweighting_enabled: boolean;
  fairness_target_dimensions: string[];
  fairness_max_gap: number;
  fairness_min_group_size: number;
  updated_at: string;
}

export interface ProgramValidationSetting {
  id: string;
  program_id: string;
  shadow_mode_enabled: boolean;
  shadow_prediction_window_days: number;
  minimum_precision_at_capacity: number;
  minimum_recall_at_capacity: number;
  require_fairness_review: boolean;
  last_evaluation_status?: string | null;
  last_shadow_run_at?: string | null;
  updated_at: string;
}

export interface ProgramDataPolicy {
  id: string;
  program_id: string;
  storage_mode: "self_hosted" | "managed_region";
  data_residency_region: string;
  cross_border_transfers_allowed: boolean;
  pii_tokenization_enabled: boolean;
  consent_required: boolean;
  federated_learning_enabled: boolean;
  updated_at: string;
}

export interface BeneficiaryExplanation {
  beneficiary_id: string;
  beneficiary_label: string;
  program_name: string;
  risk_level: RiskLevel;
  explanation: string;
  beneficiary_facing_summary: string;
  confidence: string;
  translated_ready_note: string;
  data_points_used: string[];
  support_recommendation: string;
}

export interface SyntheticProgramBundleSummary {
  program_type: string;
  beneficiaries: number;
  events: number;
  dropout_rate: number;
  regions: Record<string, number>;
}

export interface RetentionBreakdownRow {
  dimension: string;
  group_name: string;
  active_beneficiaries: number;
  dropped_beneficiaries: number;
  retention_rate: number;
  recent_dropout_rate: number;
}

export interface RetentionTrendRow {
  period: string;
  program_name: string;
  region: string;
  retention_rate: number;
  dropout_rate: number;
  active_beneficiaries: number;
}

export interface RetentionAnalytics {
  narrative: string;
  breakdowns: RetentionBreakdownRow[];
  trend_rows: RetentionTrendRow[];
  trend_highlights: string[];
  retention_curves: RetentionCurves;
}

export interface InterventionEffectivenessRow {
  action_type: string;
  context_label: string;
  attempts: number;
  successful_interventions: number;
  success_rate: number;
  avg_risk_score: number;
  recommendation_strength: "high" | "medium" | "low";
}

export interface InterventionEffectivenessSummary {
  narrative: string;
  total_logged_interventions: number;
  outcome_labeled_interventions: number;
  rows: InterventionEffectivenessRow[];
  top_recommendations: string[];
}

export interface EvaluationMetricInterval {
  value: number;
  lower_ci?: number | null;
  upper_ci?: number | null;
}

export interface EvaluationMetrics {
  auc_roc: EvaluationMetricInterval;
  pr_auc: EvaluationMetricInterval;
  precision: EvaluationMetricInterval;
  recall: EvaluationMetricInterval;
  f1: EvaluationMetricInterval;
  brier_score: EvaluationMetricInterval;
  top_k_precision: EvaluationMetricInterval;
  top_k_recall: EvaluationMetricInterval;
  top_k_lift: EvaluationMetricInterval;
  expected_calibration_error: EvaluationMetricInterval;
}

export interface CalibrationBin {
  bin_index: number;
  lower_bound: number;
  upper_bound: number;
  predicted_rate: number;
  observed_rate: number;
  count: number;
}

export interface EvaluationSplitSummary {
  temporal_strategy: "holdout" | "rolling" | "segment_holdout";
  train_cases: number;
  test_cases: number;
  train_positive_rate: number;
  test_positive_rate: number;
  train_start: string;
  train_end: string;
  test_start: string;
  test_end: string;
  folds_considered: number;
  folds_used: number;
  balanced_folds: number;
  aggregation_note?: string | null;
}

export interface ModelEvaluationReport {
  status: "ready_for_shadow_mode" | "needs_more_data" | "not_ready";
  note: string;
  algorithm: string;
  horizon_days: number;
  min_history_days: number;
  top_k_share: number;
  top_k_count: number;
  samples_evaluated: number;
  positive_cases: number;
  split: EvaluationSplitSummary;
  metrics: EvaluationMetrics;
  calibration: CalibrationBin[];
  fairness_audit?: BiasAuditSummary | null;
}

export interface ModelEvaluationRecord {
  id: string;
  created_by_email?: string | null;
  program_ids: string[];
  cohorts: string[];
  temporal_strategy: "holdout" | "rolling" | "segment_holdout";
  status: "ready_for_shadow_mode" | "needs_more_data" | "not_ready";
  algorithm: string;
  horizon_days: number;
  samples_evaluated: number;
  positive_cases: number;
  created_at: string;
  report: ModelEvaluationReport;
}

export interface ShadowRun {
  id: string;
  program_id: string;
  program_name: string;
  status: "captured" | "partial_followup" | "matured" | "insufficient_followup";
  snapshot_date: string;
  horizon_days: number;
  top_k_count: number;
  cases_captured: number;
  high_risk_cases: number;
  due_now_cases: number;
  matured_cases: number;
  observed_positive_cases: number;
  actioned_cases: number;
  top_k_precision?: number | null;
  top_k_recall?: number | null;
  note?: string | null;
  created_by_email?: string | null;
  created_at: string;
  completed_at?: string | null;
}

export interface DonorReportSummary {
  generated_at: string;
  narrative: string;
  headline_metrics: Record<string, string | number>;
  retention_analytics: RetentionAnalytics;
  intervention_effectiveness: InterventionEffectivenessSummary;
}

export interface FederatedModelUpdate {
  id: string;
  round_id: string;
  source_program_id?: string | null;
  model_version_id?: string | null;
  deployment_label: string;
  source_nonce?: string | null;
  update_fingerprint?: string | null;
  training_rows: number;
  positive_rows: number;
  payload: Record<string, unknown>;
  created_at: string;
  verified_at?: string | null;
}

export interface FederatedLearningRound {
  id: string;
  round_name: string;
  round_nonce: string;
  status: string;
  aggregation_note?: string | null;
  aggregated_payload?: Record<string, unknown> | null;
  created_at: string;
  completed_at?: string | null;
  updates: FederatedModelUpdate[];
}

export interface SSOConfig {
  enabled: boolean;
  mode: "disabled" | "header" | "oidc";
  provider_label?: string | null;
  interactive: boolean;
  start_path?: string | null;
  callback_supported: boolean;
}

export interface SSOOidcStart {
  authorization_url: string;
  state: string;
  provider_label: string;
}

export interface InterventionRecord {
  id: string;
  beneficiary_id: string;
  beneficiary_name: string;
  action_type: string;
  support_channel?: string | null;
  protocol_step?: "sms" | "call" | "visit" | null;
  status: string;
  verification_status?: string | null;
  assigned_to?: string | null;
  assigned_site?: string | null;
  due_at?: string | null;
  completed_at?: string | null;
  verified_at?: string | null;
  verification_note?: string | null;
  dismissal_reason?: string | null;
  attempt_count: number;
  source: string;
  risk_level?: string | null;
  priority_rank?: number | null;
  note?: string | null;
  successful?: boolean | null;
  soft_signals?: SoftSignalSnapshot | null;
  logged_at: string;
}

export interface AuditLogRecord {
  id: string;
  actor_email?: string | null;
  actor_role?: string | null;
  action: string;
  resource_type: string;
  resource_id?: string | null;
  details?: Record<string, string | number | boolean | null> | null;
  ip_address?: string | null;
  created_at: string;
}

export interface RuntimePolicyIssue {
  program_id: string;
  program_name: string;
  issue: string;
}

export interface RuntimeStatus {
  status: "ok" | "attention";
  deployment_region: string;
  job_backend: string;
  enforce_runtime_policy: boolean;
  violations: RuntimePolicyIssue[];
  warnings: string[];
}

export interface WorkerHealth {
  backend: string;
  status: "healthy" | "attention";
  queued: number;
  running: number;
  failed: number;
  dead_letter: number;
  worker_status: string;
  workers: string[];
  next_ready_at?: string | null;
  oldest_queue_age_seconds?: number | null;
  retry_backoff_seconds: number;
  max_attempts: number;
  stalled_threshold_seconds: number;
}

export interface AppData {
  health: HealthStatus;
  programs: Program[];
  program_settings: ProgramOperationalSetting[];
  program_validation_settings: ProgramValidationSetting[];
  program_data_policies: ProgramDataPolicy[];
  governance_beneficiaries: BeneficiaryGovernanceRecord[];
  governance_alerts: GovernanceAlert[];
  connectors: DataConnector[];
  connector_sync_runs: DataConnectorSyncRun[];
  connector_dispatch_runs: ConnectorDispatchRun[];
  model_evaluations: ModelEvaluationRecord[];
  shadow_runs: ShadowRun[];
  federated_rounds: FederatedLearningRound[];
  jobs: JobRecord[];
  model_schedule: ModelSchedule;
  imports: ImportBatch[];
  summary: DashboardSummary;
  risk_cases: RiskCase[];
  retention_curves: RetentionCurves;
  retention_analytics: RetentionAnalytics;
  interventions: InterventionRecord[];
  intervention_effectiveness: InterventionEffectivenessSummary;
  donor_report_summary: DonorReportSummary;
  synthetic_portfolio: SyntheticProgramBundleSummary[];
  sso_config: SSOConfig;
  runtime_status: RuntimeStatus;
  worker_health: WorkerHealth;
  audit_logs: AuditLogRecord[];
}
