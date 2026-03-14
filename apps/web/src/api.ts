/**
 * Typed HTTP client helpers for the RetainAI web application.
 *
 * The frontend keeps network logic centralized here so that UI components can
 * stay focused on state transitions and rendering. This file is responsible
 * for:
 *
 * - bearer-token persistence and request attachment
 * - consistent error decoding into `ApiError`
 * - the one-to-one mapping between frontend actions and backend endpoints
 * - bundling large bootstrap calls like `loadAppData`
 *
 * When an API contract changes, this is the first frontend file that should be
 * updated alongside the backend schema layer.
 */

import type {
  AppData,
  AuditLogRecord,
  AuthSession,
  BeneficiaryExplanation,
  BeneficiaryGovernanceRecord,
  BeneficiaryGovernanceUpdatePayload,
  ConnectorProbeResult,
  ConnectorDispatchRun,
  CurrentUser,
  DataConnector,
  DataConnectorCreatePayload,
  DataConnectorSyncRun,
  DatasetType,
  GovernanceAlert,
  DonorReportSummary,
  FederatedLearningRound,
  ImportAnalysis,
  ImportBatch,
  InterventionEffectivenessSummary,
  InterventionRecord,
  JobRecord,
  JobRunSummary,
  LoginPayload,
  ModelEvaluationReport,
  ModelEvaluationRecord,
  ModelSchedule,
  ModelScheduleUpdatePayload,
  ProgramDataPolicy,
  ProgramOperationalSetting,
  ProgramValidationSetting,
  Program,
  ProgramCreatePayload,
  RetentionAnalytics,
  SSOConfig,
  SSOOidcStart,
  ShadowRun,
  SyntheticProgramBundleSummary,
  RuntimeStatus,
  SessionRecord,
  WorkerHealth,
} from "./types";

const API_ORIGIN = import.meta.env.VITE_API_ORIGIN ?? (import.meta.env.DEV ? "http://localhost:8000" : "");
const API_PREFIX = `${API_ORIGIN}/api/v1`;
const TOKEN_STORAGE_KEY = "retainai.access_token";

let accessToken = typeof window !== "undefined" ? window.localStorage.getItem(TOKEN_STORAGE_KEY) : null;

/**
 * Frontend-facing error wrapper used throughout the dashboard.
 *
 * The backend returns structured `detail` fields in many failure cases; this
 * wrapper turns those into a predictable exception shape that components can
 * display without having to inspect `Response` objects directly.
 */
export class ApiError extends Error {
  status: number;

  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

function setToken(token: string | null) {
  accessToken = token;

  if (typeof window === "undefined") {
    return;
  }

  if (token) {
    window.localStorage.setItem(TOKEN_STORAGE_KEY, token);
  } else {
    window.localStorage.removeItem(TOKEN_STORAGE_KEY);
  }
}

async function readErrorDetail(response: Response): Promise<string> {
  const text = await response.text();
  if (!text) {
    return `Request failed with status ${response.status}`;
  }

  try {
    const parsed = JSON.parse(text) as { detail?: string };
    return parsed.detail ?? text;
  } catch {
    return text;
  }
}

async function readJson<T>(url: string, init?: RequestInit): Promise<T> {
  const headers = new Headers(init?.headers);

  if (accessToken) {
    headers.set("Authorization", `Bearer ${accessToken}`);
  }

  const response = await fetch(url, {
    ...init,
    headers,
  });

  if (!response.ok) {
    throw new ApiError(response.status, await readErrorDetail(response));
  }

  return (await response.json()) as T;
}

async function readBlob(url: string, init?: RequestInit): Promise<Blob> {
  const headers = new Headers(init?.headers);

  if (accessToken) {
    headers.set("Authorization", `Bearer ${accessToken}`);
  }

  const response = await fetch(url, {
    ...init,
    headers,
  });

  if (!response.ok) {
    throw new ApiError(response.status, await readErrorDetail(response));
  }

  return await response.blob();
}

export function getStoredAccessToken(): string | null {
  return accessToken;
}

export function clearAccessToken(): void {
  setToken(null);
}

export async function logout(): Promise<void> {
  try {
    await readJson<{ status: string; session_id: string }>(`${API_PREFIX}/auth/logout`, {
      method: "POST",
    });
  } finally {
    setToken(null);
  }
}

export async function fetchSessions(): Promise<SessionRecord[]> {
  return readJson<SessionRecord[]>(`${API_PREFIX}/auth/sessions`);
}

export async function requeueJob(jobId: string): Promise<JobRecord> {
  return readJson<JobRecord>(`${API_PREFIX}/jobs/${jobId}/requeue`, {
    method: "POST",
  });
}

export async function login(payload: LoginPayload): Promise<AuthSession> {
  const session = await readJson<AuthSession>(`${API_PREFIX}/auth/login`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });

  setToken(session.access_token);
  return session;
}

export async function fetchCurrentUser(): Promise<CurrentUser> {
  return readJson<CurrentUser>(`${API_PREFIX}/auth/me`);
}

export async function fetchSSOConfig(): Promise<SSOConfig> {
  return readJson<SSOConfig>(`${API_PREFIX}/auth/sso/config`);
}

export async function startOidcLogin(redirectUri: string): Promise<SSOOidcStart> {
  const encoded = encodeURIComponent(redirectUri);
  return readJson<SSOOidcStart>(`${API_PREFIX}/auth/sso/oidc/start?redirect_uri=${encoded}`);
}

export async function exchangeOidcCode(payload: {
  code: string;
  state: string;
  redirect_uri: string;
}): Promise<AuthSession> {
  const session = await readJson<AuthSession>(`${API_PREFIX}/auth/sso/oidc/exchange`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });
  setToken(session.access_token);
  return session;
}

export async function loadAuditLogs(limit = 20): Promise<AuditLogRecord[]> {
  return readJson<AuditLogRecord[]>(`${API_PREFIX}/audit-logs?limit=${limit}`);
}

export async function loadAppData(includeAuditLogs = false, includeGovernanceAlerts = false): Promise<AppData> {
  const [health, programs, program_settings, program_validation_settings, program_data_policies, governance_beneficiaries, governance_alerts, connectors, connector_sync_runs, connector_dispatch_runs, model_evaluations, shadow_runs, federated_rounds, jobs, model_schedule, imports, summary, risk_cases, retention_curves, retention_analytics, interventions, intervention_effectiveness, donor_report_summary, synthetic_portfolio, sso_config, runtime_status, worker_health, audit_logs] = await Promise.all([
    readJson<AppData["health"]>(`${API_ORIGIN}/health`),
    readJson<AppData["programs"]>(`${API_PREFIX}/programs`),
    readJson<ProgramOperationalSetting[]>(`${API_PREFIX}/program-settings`),
    readJson<ProgramValidationSetting[]>(`${API_PREFIX}/program-validation`),
    readJson<ProgramDataPolicy[]>(`${API_PREFIX}/program-data-policies`),
    readJson<AppData["governance_beneficiaries"]>(`${API_PREFIX}/beneficiaries/governance?limit=20`),
    includeGovernanceAlerts
      ? readJson<AppData["governance_alerts"]>(`${API_PREFIX}/governance/alerts?limit=8`)
      : Promise.resolve([]),
    readJson<AppData["connectors"]>(`${API_PREFIX}/connectors`),
    readJson<AppData["connector_sync_runs"]>(`${API_PREFIX}/connectors/sync-runs?limit=12`),
    readJson<AppData["connector_dispatch_runs"]>(`${API_PREFIX}/connectors/dispatch-runs?limit=12`),
    readJson<ModelEvaluationRecord[]>(`${API_PREFIX}/model/evaluations?limit=12`),
    readJson<ShadowRun[]>(`${API_PREFIX}/program-validation/shadow-runs?limit=12`),
    readJson<FederatedLearningRound[]>(`${API_PREFIX}/federated/rounds?limit=6`),
    readJson<AppData["jobs"]>(`${API_PREFIX}/jobs?limit=12`),
    readJson<AppData["model_schedule"]>(`${API_PREFIX}/model/schedule`),
    readJson<AppData["imports"]>(`${API_PREFIX}/imports`),
    readJson<AppData["summary"]>(`${API_PREFIX}/dashboard/summary`),
    readJson<AppData["risk_cases"]>(`${API_PREFIX}/risk-cases`),
    readJson<AppData["retention_curves"]>(`${API_PREFIX}/retention/curves`),
    readJson<RetentionAnalytics>(`${API_PREFIX}/retention/analytics`),
    readJson<AppData["interventions"]>(`${API_PREFIX}/interventions`),
    readJson<InterventionEffectivenessSummary>(`${API_PREFIX}/interventions/effectiveness`),
    readJson<DonorReportSummary>(`${API_PREFIX}/reports/donor-summary`),
    readJson<SyntheticProgramBundleSummary[]>(`${API_PREFIX}/synthetic/portfolio?rows_per_program=180`),
    readJson<SSOConfig>(`${API_PREFIX}/auth/sso/config`),
    readJson<RuntimeStatus>(`${API_PREFIX}/ops/runtime-status`),
    readJson<WorkerHealth>(`${API_PREFIX}/ops/worker-health`),
    includeAuditLogs ? loadAuditLogs(12) : Promise.resolve([]),
  ]);

  return {
    health,
    programs,
    program_settings,
    program_validation_settings,
    program_data_policies,
    governance_beneficiaries,
    governance_alerts,
    connectors,
    connector_sync_runs,
    connector_dispatch_runs,
    model_evaluations,
    shadow_runs,
    federated_rounds,
    jobs,
    model_schedule,
    imports,
    summary,
    risk_cases,
    retention_curves,
    retention_analytics,
    interventions,
    intervention_effectiveness,
    donor_report_summary,
    synthetic_portfolio,
    sso_config,
    runtime_status,
    worker_health,
    audit_logs,
  };
}

export async function createProgram(payload: ProgramCreatePayload): Promise<Program> {
  return readJson<Program>(`${API_PREFIX}/programs`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });
}

export async function updateBeneficiaryGovernance(
  beneficiaryId: string,
  payload: BeneficiaryGovernanceUpdatePayload,
): Promise<BeneficiaryGovernanceRecord> {
  return readJson<BeneficiaryGovernanceRecord>(`${API_PREFIX}/beneficiaries/${beneficiaryId}/governance`, {
    method: "PATCH",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });
}

export async function fetchBeneficiaryExplanation(beneficiaryId: string): Promise<BeneficiaryExplanation> {
  return readJson<BeneficiaryExplanation>(`${API_PREFIX}/beneficiaries/${beneficiaryId}/explanation`);
}

export async function createConnector(payload: DataConnectorCreatePayload): Promise<DataConnector> {
  return readJson<DataConnector>(`${API_PREFIX}/connectors`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });
}

export async function previewConnector(payload: DataConnectorCreatePayload): Promise<ConnectorProbeResult> {
  return readJson<ConnectorProbeResult>(`${API_PREFIX}/connectors/preview`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });
}

export async function testConnector(connectorId: string): Promise<ConnectorProbeResult> {
  return readJson<ConnectorProbeResult>(`${API_PREFIX}/connectors/${connectorId}/test`, {
    method: "POST",
  });
}

export async function syncConnector(connectorId: string): Promise<JobRecord> {
  return readJson<JobRecord>(`${API_PREFIX}/connectors/${connectorId}/sync`, {
    method: "POST",
  });
}

export async function dispatchConnectorQueue(
  connectorId: string,
  payload: {
    only_due?: boolean;
    include_this_week?: boolean;
    limit?: number;
    preview_only?: boolean;
  },
): Promise<ConnectorDispatchRun> {
  return readJson<ConnectorDispatchRun>(`${API_PREFIX}/connectors/${connectorId}/dispatch`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });
}

export async function updateModelSchedule(payload: ModelScheduleUpdatePayload): Promise<ModelSchedule> {
  return readJson<ModelSchedule>(`${API_PREFIX}/model/schedule`, {
    method: "PUT",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });
}

export async function runDueAutomation(): Promise<JobRecord> {
  return readJson<JobRecord>(`${API_PREFIX}/automation/run-due`, {
    method: "POST",
  });
}

export async function exportRiskCases(purpose: string, includePii = false): Promise<Blob> {
  return readBlob(`${API_PREFIX}/exports/risk-cases`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ purpose, include_pii: includePii }),
  });
}

export async function exportInterventions(purpose: string, includePii = false): Promise<Blob> {
  return readBlob(`${API_PREFIX}/exports/interventions`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ purpose, include_pii: includePii }),
  });
}

export async function updateProgramSetting(
  programId: string,
  payload: {
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
  },
): Promise<ProgramOperationalSetting> {
  return readJson<ProgramOperationalSetting>(`${API_PREFIX}/program-settings/${programId}`, {
    method: "PUT",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });
}

export async function updateProgramValidationSetting(
  programId: string,
  payload: {
    shadow_mode_enabled: boolean;
    shadow_prediction_window_days: number;
    minimum_precision_at_capacity: number;
    minimum_recall_at_capacity: number;
    require_fairness_review: boolean;
  },
): Promise<ProgramValidationSetting> {
  return readJson<ProgramValidationSetting>(`${API_PREFIX}/program-validation/${programId}`, {
    method: "PUT",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });
}

export async function runModelBacktest(
  payload: {
    temporal_strategy: "holdout" | "rolling";
    horizon_days: number;
    min_history_days: number;
    holdout_share: number;
    rolling_folds: number;
    program_ids: string[];
    cohorts: string[];
    top_k_share: number;
    top_k_capacity?: number | null;
    calibration_bins: number;
    bootstrap_iterations: number;
  },
): Promise<ModelEvaluationReport> {
  return readJson<ModelEvaluationReport>(`${API_PREFIX}/model/evaluate/backtest`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });
}

export async function createShadowRun(
  programId: string,
  payload: {
    top_k_count?: number | null;
    note?: string | null;
  } = {},
): Promise<ShadowRun> {
  return readJson<ShadowRun>(`${API_PREFIX}/program-validation/${programId}/shadow-runs`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });
}

export async function updateProgramDataPolicy(
  programId: string,
  payload: {
    storage_mode: "self_hosted" | "managed_region";
    data_residency_region: string;
    cross_border_transfers_allowed: boolean;
    pii_tokenization_enabled: boolean;
    consent_required: boolean;
    federated_learning_enabled: boolean;
  },
): Promise<ProgramDataPolicy> {
  return readJson<ProgramDataPolicy>(`${API_PREFIX}/program-data-policies/${programId}`, {
    method: "PUT",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });
}

export async function exportDonorWorkbook(): Promise<Blob> {
  return readBlob(`${API_PREFIX}/reports/donor-summary.xlsx`);
}

export async function exportDonorPdf(): Promise<Blob> {
  return readBlob(`${API_PREFIX}/reports/donor-summary.pdf`);
}

export async function exportFederatedUpdate(roundName: string, deploymentLabel: string, sourceProgramId?: string): Promise<void> {
  await readJson(`${API_PREFIX}/federated/export-update`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      round_name: roundName,
      deployment_label: deploymentLabel,
      source_program_id: sourceProgramId ?? null,
    }),
  });
}

export async function aggregateFederatedRound(roundName: string): Promise<FederatedLearningRound> {
  return readJson<FederatedLearningRound>(`${API_PREFIX}/federated/aggregate`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ round_name: roundName, close_round: true }),
  });
}

export async function runPendingJobs(maxJobs = 10): Promise<JobRunSummary> {
  return readJson<JobRunSummary>(`${API_PREFIX}/jobs/run-pending`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ max_jobs: maxJobs }),
  });
}

export async function uploadCsvImport(
  datasetType: DatasetType,
  programId: string,
  file: File,
  mapping?: Record<string, string | null>,
): Promise<ImportBatch> {
  const formData = new FormData();
  formData.append("dataset_type", datasetType);
  formData.append("program_id", programId);
  formData.append("file", file);
  if (mapping && Object.keys(mapping).length > 0) {
    formData.append("mapping_json", JSON.stringify(mapping));
  }

  return readJson<ImportBatch>(`${API_PREFIX}/imports/csv`, {
    method: "POST",
    body: formData,
  });
}

export async function analyzeImport(
  datasetType: DatasetType,
  file: File,
  mapping?: Record<string, string | null>,
): Promise<ImportAnalysis> {
  const formData = new FormData();
  formData.append("dataset_type", datasetType);
  formData.append("file", file);
  if (mapping && Object.keys(mapping).length > 0) {
    formData.append("mapping_json", JSON.stringify(mapping));
  }

  return readJson<ImportAnalysis>(`${API_PREFIX}/imports/analyze`, {
    method: "POST",
    body: formData,
  });
}

export async function logIntervention(
  payload: {
    beneficiary_id: string;
    action_type: string;
    support_channel?: "sms" | "call" | "visit" | "whatsapp" | "manual" | null;
    protocol_step?: "sms" | "call" | "visit" | null;
    status?: "queued" | "attempted" | "reached" | "verified" | "dismissed" | "closed" | "escalated";
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
    verification_note?: string | null;
    dismissal_reason?: string | null;
    attempt_count?: number;
    source?: string;
    risk_level?: "High" | "Medium" | "Low" | null;
    priority_rank?: number | null;
    note?: string | null;
    successful?: boolean | null;
    soft_signals?: {
      household_stability_signal?: number | null;
      economic_stress_signal?: number | null;
      family_support_signal?: number | null;
      health_change_signal?: number | null;
      motivation_signal?: number | null;
    } | null;
  },
): Promise<InterventionRecord> {
  return readJson<InterventionRecord>(`${API_PREFIX}/interventions`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });
}

export async function updateIntervention(
  interventionId: string,
  payload: {
    action_type?: string;
    support_channel?: "sms" | "call" | "visit" | "whatsapp" | "manual" | null;
    protocol_step?: "sms" | "call" | "visit" | null;
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
    verification_note?: string | null;
    dismissal_reason?: string | null;
    attempt_count?: number | null;
    note?: string | null;
    successful?: boolean | null;
    soft_signals?: {
      household_stability_signal?: number | null;
      economic_stress_signal?: number | null;
      family_support_signal?: number | null;
      health_change_signal?: number | null;
      motivation_signal?: number | null;
    } | null;
  },
): Promise<InterventionRecord> {
  return readJson<InterventionRecord>(`${API_PREFIX}/interventions/${interventionId}`, {
    method: "PATCH",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });
}

export async function trainModel(force = false): Promise<JobRecord> {
  return readJson<JobRecord>(`${API_PREFIX}/model/train`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ force }),
  });
}

export async function exportFollowUpList(
  mode: "whatsapp" | "sms" | "field_visit",
  payload: {
    purpose: string;
    include_pii?: boolean;
    program_id?: string | null;
    risk_level?: "High" | "Medium" | "Low" | null;
    region?: string | null;
    cohort?: string | null;
    phase?: string | null;
    search?: string | null;
  },
): Promise<Blob> {
  const endpoint =
    mode === "whatsapp"
      ? `${API_PREFIX}/exports/followup/whatsapp`
      : mode === "sms"
        ? `${API_PREFIX}/exports/followup/sms`
        : `${API_PREFIX}/exports/followup/field-visits`;

  return readBlob(endpoint, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });
}
