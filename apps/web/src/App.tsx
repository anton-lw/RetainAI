/**
 * Root React application shell for the RetainAI dashboard.
 *
 * This file still acts as the main orchestration layer for the web client even
 * after several UI sections were extracted into dedicated components. It owns:
 *
 * - session bootstrap and login / logout state
 * - top-level application data loading and refresh behavior
 * - cross-section form state that spans operations, governance, validation,
 *   connectors, and exports
 * - the wiring between API helpers and presentational sections
 *
 * Maintainers trying to understand "where does this user action start?" should
 * usually begin here, then follow the relevant extracted section component and
 * finally the API helper in `api.ts`.
 */

import { useDeferredValue, useEffect, useState, useTransition, type FormEvent } from "react";
import {
  analyzeImport,
  ApiError,
  clearAccessToken,
  createConnector,
  createProgram,
  exchangeOidcCode,
  aggregateFederatedRound,
  exportFollowUpList,
  exportDonorPdf,
  exportDonorWorkbook,
  exportInterventions,
  exportRiskCases,
  exportFederatedUpdate,
  fetchSSOConfig,
  fetchBeneficiaryExplanation,
  fetchCurrentUser,
  getStoredAccessToken,
  loadAppData,
  logIntervention,
  login,
  runModelBacktest,
  runDueAutomation,
  runPendingJobs,
  syncConnector,
  testConnector,
  trainModel,
  createShadowRun,
  updateBeneficiaryGovernance,
  updateIntervention,
  updateModelSchedule,
  updateProgramDataPolicy,
  updateProgramSetting,
  updateProgramValidationSetting,
  uploadCsvImport,
  previewConnector,
  dispatchConnectorQueue,
  requeueJob,
  logout,
  startOidcLogin,
} from "./api";
import type {
  AppData,
  AuthScheme,
  ConnectorProbeResult,
  ConnectorType,
  CurrentUser,
  DataConnectorCreatePayload,
  DatasetType,
  ImportAnalysis,
  JobRecord,
  LoginPayload,
  ModelEvaluationRecord,
  ModelCadence,
  ModelScheduleUpdatePayload,
  ProgramDataPolicy,
  ProgramOperationalSetting,
  ProgramValidationSetting,
  ProgramCreatePayload,
  RiskCase,
  RiskLevel,
  SSOConfig,
  ShadowRun,
  SoftSignalSnapshot,
  UserRole,
} from "./types";
import MobileLiteView from "./MobileLiteView";
import AnalyticsOverview from "./components/AnalyticsOverview";
import AuthScreen from "./components/AuthScreen";
import ConnectorAutomationSection from "./components/ConnectorAutomationSection";
import GovernanceSection from "./components/GovernanceSection";
import OperationsSection from "./components/OperationsSection";
import RiskQueueSection from "./components/RiskQueueSection";
import StatusScreen from "./components/StatusScreen";
import ValidationSection from "./components/ValidationSection";

const PROGRAM_TYPE_OPTIONS = ["Cash Transfer", "Education", "Health"];
const CONNECTOR_TYPE_OPTIONS: Array<{ value: ConnectorType; label: string }> = [
  { value: "kobotoolbox", label: "KoboToolbox" },
  { value: "commcare", label: "CommCare" },
  { value: "odk_central", label: "ODK Central" },
  { value: "dhis2", label: "DHIS2" },
  { value: "salesforce_npsp", label: "Salesforce NPSP" },
];
const AUTH_SCHEME_OPTIONS: Array<{ value: AuthScheme; label: string }> = [
  { value: "bearer", label: "Bearer token" },
  { value: "token", label: "Token header" },
  { value: "basic", label: "Basic auth" },
  { value: "none", label: "No auth" },
];
const CADENCE_OPTIONS: Array<{ value: ModelCadence; label: string }> = [
  { value: "manual", label: "Manual only" },
  { value: "weekly", label: "Weekly" },
  { value: "monthly", label: "Monthly" },
];
const SYNC_INTERVAL_OPTIONS = [
  { value: "6", label: "Every 6 hours" },
  { value: "24", label: "Daily" },
  { value: "168", label: "Weekly" },
];
const SHOW_DEVELOPMENT_ACCOUNTS = import.meta.env.DEV;
const APP_BUNDLE_STORAGE_KEY = "retainai.cached_bundle";
const DEVELOPMENT_ACCOUNTS = [
  "admin@retainai.local",
  "me.officer@retainai.local",
  "field.coordinator@retainai.local",
  "country.director@retainai.local",
];

interface ConnectorFormState {
  program_id: string;
  name: string;
  connector_type: ConnectorType;
  dataset_type: DatasetType;
  base_url: string;
  resource_path: string;
  auth_scheme: AuthScheme;
  auth_username: string;
  secret: string;
  record_path: string;
  query_params_text: string;
  schedule_enabled: boolean;
  sync_interval_hours: string;
  writeback_enabled: boolean;
  writeback_mode: "none" | "commcare_case_updates" | "dhis2_working_list" | "generic_webhook";
  writeback_resource_path: string;
  writeback_field_mapping_text: string;
  webhook_enabled: boolean;
  webhook_secret: string;
}

const DATASET_MAPPING_FIELDS: Record<DatasetType, string[]> = {
  beneficiaries: [
    "external_id",
    "full_name",
    "region",
    "enrollment_date",
    "status",
    "cohort",
    "phase",
    "gender",
    "household_type",
    "household_size",
    "pmt_score",
    "food_insecurity_index",
    "distance_to_service_km",
    "preferred_contact_phone",
    "preferred_contact_channel",
    "current_note",
    "opted_out",
  ],
  events: [
    "external_id",
    "event_date",
    "event_type",
    "successful",
    "response_received",
    "source",
    "notes",
  ],
};

function formatDate(value: string): string {
  return new Intl.DateTimeFormat("en-GB", {
    day: "2-digit",
    month: "short",
    year: "numeric",
  }).format(new Date(value));
}

function formatTimestamp(value: string): string {
  return new Intl.DateTimeFormat("en-GB", {
    day: "2-digit",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(value));
}

function formatMetricValue(value: string | number | undefined): string {
  if (value === undefined) {
    return "n/a";
  }
  if (typeof value === "number") {
    return value <= 1 ? `${Math.round(value * 100)}%` : value.toLocaleString();
  }
  return value;
}

function formatRate(value: number | null | undefined): string {
  if (value === null || value === undefined) {
    return "n/a";
  }
  return `${Math.round(value * 100)}%`;
}

function formatRole(role: UserRole): string {
  if (role === "me_officer") {
    return "M&E officer";
  }
  if (role === "field_coordinator") {
    return "Field coordinator";
  }
  if (role === "country_director") {
    return "Country director";
  }
  return "Admin";
}

function formatPaginationMode(value: string): string {
  if (value === "next_url") {
    return "Server next-link";
  }
  if (value === "page_number") {
    return "Page-number";
  }
  return "Single page";
}

function formatBiasDimension(dimension: string): string {
  if (dimension === "household_type") {
    return "Household type";
  }
  if (dimension === "gender") {
    return "Gender";
  }
  if (dimension === "region") {
    return "Geography";
  }
  return dimension.replace(/_/g, " ");
}

function formatJobType(jobType: JobRecord["job_type"]): string {
  if (jobType === "connector_sync") {
    return "Connector sync";
  }
  if (jobType === "model_train") {
    return "Model retrain";
  }
  return "Run due automation";
}

function formatJobStatus(status: JobRecord["status"]): string {
  return status.replace(/_/g, " ");
}

function jobStatusTone(status: JobRecord["status"]): "risk-high" | "risk-medium" | "risk-low" {
  if (status === "failed" || status === "dead_letter") {
    return "risk-high";
  }
  if (status === "succeeded") {
    return "risk-low";
  }
  return "risk-medium";
}

function canManagePrograms(role?: UserRole): boolean {
  return role === "admin" || role === "me_officer";
}

function canTrainModels(role?: UserRole): boolean {
  return role === "admin" || role === "me_officer";
}

function canLogInterventions(role?: UserRole): boolean {
  return role === "admin" || role === "me_officer" || role === "field_coordinator";
}

function canViewAuditLogs(role?: UserRole): boolean {
  return role === "admin" || role === "me_officer" || role === "country_director";
}

function canManageGovernance(role?: UserRole): boolean {
  return role === "admin" || role === "me_officer";
}

function canExportData(role?: UserRole): boolean {
  return role === "admin" || role === "me_officer" || role === "country_director";
}

function canViewGovernanceAlerts(role?: UserRole): boolean {
  return role === "admin" || role === "me_officer" || role === "country_director";
}

function nextActionLabel(riskLevel: RiskLevel): string {
  if (riskLevel === "High") {
    return "Schedule check-in";
  }
  if (riskLevel === "Medium") {
    return "Queue follow-up";
  }
  return "Keep monitoring";
}

type WorkflowStatus = "queued" | "attempted" | "reached" | "verified" | "dismissed" | "closed" | "escalated";
type VerificationStatus =
  | "pending"
  | "still_enrolled"
  | "re_engaged"
  | "silent_transfer"
  | "completed_elsewhere"
  | "deceased"
  | "unreachable"
  | "declined_support"
  | "dropped_out_confirmed";
type SupportChannel = "sms" | "call" | "visit" | "whatsapp" | "manual";

interface WorkflowFormState {
  action_type: string;
  support_channel: SupportChannel;
  protocol_step: "sms" | "call" | "visit";
  status: WorkflowStatus;
  verification_status: VerificationStatus;
  assigned_to: string;
  assigned_site: string;
  due_at: string;
  note: string;
  verification_note: string;
  dismissal_reason: string;
  attempt_count: number;
  successful: boolean | null;
  soft_signals: SoftSignalSnapshot;
}

function toDateTimeLocalValue(value?: string | null): string {
  if (!value) {
    return "";
  }
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return "";
  }
  const offset = parsed.getTimezoneOffset() * 60_000;
  return new Date(parsed.getTime() - offset).toISOString().slice(0, 16);
}

function workflowDefaultsFor(riskCase: RiskCase): WorkflowFormState {
  return {
    action_type: nextActionLabel(riskCase.risk_level),
    support_channel: (riskCase.workflow?.support_channel as SupportChannel | undefined) ?? (riskCase.tracing_protocol?.current_channel as SupportChannel | undefined) ?? (riskCase.risk_level === "High" ? "visit" : riskCase.program_type === "Cash Transfer" ? "whatsapp" : "call"),
    protocol_step: riskCase.workflow?.protocol_step ?? riskCase.tracing_protocol?.current_step ?? (riskCase.risk_level === "High" ? "visit" : "call"),
    status: (riskCase.workflow?.status as WorkflowStatus | undefined) ?? "queued",
    verification_status: (riskCase.workflow?.verification_status as VerificationStatus | undefined) ?? "pending",
    assigned_to: riskCase.workflow?.assigned_to ?? riskCase.assigned_worker ?? "",
    assigned_site: riskCase.workflow?.assigned_site ?? riskCase.assigned_site ?? riskCase.region,
    due_at: toDateTimeLocalValue(riskCase.workflow?.due_at),
    note: riskCase.workflow?.note ?? `Supportive follow-up opened from the risk queue for ${riskCase.program}.`,
    verification_note: riskCase.workflow?.verification_note ?? "",
    dismissal_reason: riskCase.workflow?.dismissal_reason ?? "",
    attempt_count: riskCase.workflow?.attempt_count ?? 0,
    successful: riskCase.workflow?.successful ?? null,
    soft_signals: {
      household_stability_signal: riskCase.soft_signals?.household_stability_signal ?? null,
      economic_stress_signal: riskCase.soft_signals?.economic_stress_signal ?? null,
      family_support_signal: riskCase.soft_signals?.family_support_signal ?? null,
      health_change_signal: riskCase.soft_signals?.health_change_signal ?? null,
      motivation_signal: riskCase.soft_signals?.motivation_signal ?? null,
    },
  };
}

function formatMappingField(field: string): string {
  return field
    .replace(/_/g, " ")
    .replace(/\b\w/g, (value) => value.toUpperCase());
}

function parseKeyValueJson(raw: string, label: string): Record<string, string | number | boolean | null> {
  if (!raw.trim()) {
    return {};
  }

  let parsed: unknown;
  try {
    parsed = JSON.parse(raw);
  } catch {
    throw new Error(`${label} must be valid JSON.`);
  }

  if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
    throw new Error(`${label} must be a JSON object.`);
  }

  return parsed as Record<string, string | number | boolean | null>;
}

function downloadBlob(blob: Blob, filename: string) {
  const url = window.URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  anchor.click();
  window.URL.revokeObjectURL(url);
}

function App() {
  const [bundle, setBundle] = useState<AppData | null>(null);
  const [currentUser, setCurrentUser] = useState<CurrentUser | null>(null);
  const [publicSsoConfig, setPublicSsoConfig] = useState<SSOConfig | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [riskFilter, setRiskFilter] = useState<"All" | RiskLevel>("All");
  const [regionFilter, setRegionFilter] = useState("All");
  const [programFilter, setProgramFilter] = useState("All");
  const [cohortFilter, setCohortFilter] = useState("All");
  const [phaseFilter, setPhaseFilter] = useState("All");
  const [datasetType, setDatasetType] = useState<DatasetType>("beneficiaries");
  const [selectedProgramId, setSelectedProgramId] = useState("");
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [importAnalysis, setImportAnalysis] = useState<ImportAnalysis | null>(null);
  const [importMappingDraft, setImportMappingDraft] = useState<Record<string, string | null>>({});
  const [isAnalyzingImport, setIsAnalyzingImport] = useState(false);
  const [connectorPreview, setConnectorPreview] = useState<ConnectorProbeResult | null>(null);
  const [connectorMappingDraft, setConnectorMappingDraft] = useState<Record<string, string | null>>({});
  const [isPreviewingConnector, setIsPreviewingConnector] = useState(false);
  const [programForm, setProgramForm] = useState<ProgramCreatePayload>({
    name: "",
    program_type: "Cash Transfer",
    country: "",
    delivery_modality: "",
  });
  const [connectorForm, setConnectorForm] = useState<ConnectorFormState>({
    program_id: "",
    name: "",
    connector_type: "kobotoolbox",
    dataset_type: "beneficiaries",
    base_url: "",
    resource_path: "",
    auth_scheme: "bearer",
    auth_username: "",
    secret: "",
    record_path: "",
    query_params_text: "{}",
    schedule_enabled: true,
    sync_interval_hours: "24",
    writeback_enabled: false,
    writeback_mode: "commcare_case_updates",
    writeback_resource_path: "",
    writeback_field_mapping_text: "{}",
    webhook_enabled: false,
    webhook_secret: "",
  });
  const [modelScheduleForm, setModelScheduleForm] = useState<ModelScheduleUpdatePayload>({
    cadence: "manual",
    enabled: false,
    auto_retrain_after_sync: false,
  });
  const [programSettingForm, setProgramSettingForm] = useState({
    weekly_followup_capacity: 30,
    worker_count: 4,
    medium_risk_multiplier: 2,
    high_risk_share_floor: 0.08,
    review_window_days: 30,
    label_definition_preset: "custom" as "health_28d" | "education_10d" | "cct_missed_cycle" | "custom",
    dropout_inactivity_days: 30,
    prediction_window_days: 30,
    label_noise_strategy: "operational_soft_labels" as "strict" | "operational_soft_labels",
    soft_label_weight: 0.35,
    silent_transfer_detection_enabled: true,
    low_risk_channel: "sms" as "sms" | "call" | "visit" | "whatsapp" | "manual",
    medium_risk_channel: "call" as "sms" | "call" | "visit" | "whatsapp" | "manual",
    high_risk_channel: "visit" as "sms" | "call" | "visit" | "whatsapp" | "manual",
    tracing_sms_delay_days: 3,
    tracing_call_delay_days: 7,
    tracing_visit_delay_days: 14,
    escalation_window_days: 7,
    escalation_max_attempts: 2,
    fairness_reweighting_enabled: false,
    fairness_target_dimensions: ["gender", "region", "household_type"],
    fairness_max_gap: 0.15,
    fairness_min_group_size: 20,
  });
  const [programDataPolicyForm, setProgramDataPolicyForm] = useState({
    storage_mode: "self_hosted" as ProgramDataPolicy["storage_mode"],
    data_residency_region: "eu-central",
    cross_border_transfers_allowed: false,
    pii_tokenization_enabled: true,
    consent_required: true,
    federated_learning_enabled: true,
  });
  const [programValidationForm, setProgramValidationForm] = useState({
    shadow_mode_enabled: false,
    shadow_prediction_window_days: 30,
    minimum_precision_at_capacity: 0.7,
    minimum_recall_at_capacity: 0.5,
    require_fairness_review: true,
  });
  const [evaluationForm, setEvaluationForm] = useState({
    temporal_strategy: "rolling" as "holdout" | "rolling",
    min_history_days: 60,
    holdout_share: 0.25,
    rolling_folds: 4,
    top_k_share: 0.2,
    top_k_capacity_text: "",
    calibration_bins: 5,
    bootstrap_iterations: 50,
  });
  const [federatedRoundName, setFederatedRoundName] = useState("retainai-round-001");
  const [selectedExplanation, setSelectedExplanation] = useState<string | null>(null);
  const [selectedWorkflowCaseId, setSelectedWorkflowCaseId] = useState<string | null>(null);
  const [workflowForm, setWorkflowForm] = useState<WorkflowFormState>({
    action_type: "Queue follow-up",
    support_channel: "call",
    protocol_step: "call",
    status: "queued",
    verification_status: "pending",
    assigned_to: "",
    assigned_site: "",
    due_at: "",
    note: "",
    verification_note: "",
    dismissal_reason: "",
    attempt_count: 0,
    successful: null,
    soft_signals: {
      household_stability_signal: null,
      economic_stress_signal: null,
      family_support_signal: null,
      health_change_signal: null,
      motivation_signal: null,
    },
  });
  const [mobileLiteEnabled, setMobileLiteEnabled] = useState(
    typeof window !== "undefined" ? window.innerWidth <= 760 : false,
  );
  const [loginForm, setLoginForm] = useState<LoginPayload>({
    email: "",
    password: "",
  });
  const [isBooting, setIsBooting] = useState(true);
  const [isRefreshing, startTransition] = useTransition();
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isAuthenticating, setIsAuthenticating] = useState(false);
  const [isStartingSso, setIsStartingSso] = useState(false);
  const [activeConnectorId, setActiveConnectorId] = useState<string | null>(null);
  const deferredSearch = useDeferredValue(search);

  const currentRole = currentUser?.role;
  const showAuditLogs = canViewAuditLogs(currentRole);
  const allowProgramAdmin = canManagePrograms(currentRole);
  const allowModelTraining = canTrainModels(currentRole);
  const allowInterventionLogging = canLogInterventions(currentRole);
  const allowGovernanceManagement = canManageGovernance(currentRole);
  const allowExports = canExportData(currentRole);
  const effectiveSsoConfig = publicSsoConfig ?? bundle?.sso_config ?? null;

  function resolveOidcRedirectUri(): string {
    return `${window.location.origin}${window.location.pathname}`;
  }

  function resetSession(message?: string) {
    clearAccessToken();
    setCurrentUser(null);
    setBundle(null);
    setSelectedProgramId("");
    setSelectedFile(null);
    setImportAnalysis(null);
    setImportMappingDraft({});
    setConnectorPreview(null);
    setConnectorMappingDraft({});
    setSearch("");
    setRiskFilter("All");
    setRegionFilter("All");
    setProgramFilter("All");
    setCohortFilter("All");
    setPhaseFilter("All");
    if (message) {
      setError(message);
    }
  }

  function handleApiFailure(caughtError: unknown, fallbackMessage: string) {
    if (caughtError instanceof ApiError && caughtError.status === 401) {
      resetSession("Your session has expired. Sign in again.");
      return;
    }

    const message = caughtError instanceof Error ? caughtError.message : fallbackMessage;
    setError(message);
  }

  async function refreshData(roleOverride?: UserRole) {
    try {
      const effectiveRole = roleOverride ?? currentRole;
      const result = await loadAppData(
        canViewAuditLogs(effectiveRole),
        canViewGovernanceAlerts(effectiveRole),
      );
      if (typeof window !== "undefined") {
        window.localStorage.setItem(APP_BUNDLE_STORAGE_KEY, JSON.stringify(result));
      }
      startTransition(() => {
        setBundle(result);
        setPublicSsoConfig(result.sso_config);
        setError(null);
        setSelectedProgramId((current) => current || result.programs[0]?.id || "");
        setConnectorForm((current) => ({
          ...current,
          program_id: current.program_id || result.programs[0]?.id || "",
        }));
        setModelScheduleForm({
          cadence: result.model_schedule.cadence,
          enabled: result.model_schedule.enabled,
          auto_retrain_after_sync: result.model_schedule.auto_retrain_after_sync,
        });
        const initialProgramId = selectedProgramId || result.programs[0]?.id || "";
        const selectedSetting = result.program_settings.find((item) => item.program_id === initialProgramId) ?? result.program_settings[0];
        const selectedValidation = result.program_validation_settings.find((item) => item.program_id === initialProgramId) ?? result.program_validation_settings[0];
        const selectedPolicy = (result.program_data_policies ?? []).find((item) => item.program_id === initialProgramId) ?? result.program_data_policies?.[0];
        if (selectedSetting) {
          setProgramSettingForm({
            weekly_followup_capacity: selectedSetting.weekly_followup_capacity,
            worker_count: selectedSetting.worker_count,
            medium_risk_multiplier: selectedSetting.medium_risk_multiplier,
            high_risk_share_floor: selectedSetting.high_risk_share_floor,
            review_window_days: selectedSetting.review_window_days,
            label_definition_preset: selectedSetting.label_definition_preset,
            dropout_inactivity_days: selectedSetting.dropout_inactivity_days,
            prediction_window_days: selectedSetting.prediction_window_days,
            label_noise_strategy: selectedSetting.label_noise_strategy,
            soft_label_weight: selectedSetting.soft_label_weight,
            silent_transfer_detection_enabled: selectedSetting.silent_transfer_detection_enabled,
            low_risk_channel: selectedSetting.low_risk_channel,
            medium_risk_channel: selectedSetting.medium_risk_channel,
            high_risk_channel: selectedSetting.high_risk_channel,
            tracing_sms_delay_days: selectedSetting.tracing_sms_delay_days,
            tracing_call_delay_days: selectedSetting.tracing_call_delay_days,
            tracing_visit_delay_days: selectedSetting.tracing_visit_delay_days,
            escalation_window_days: selectedSetting.escalation_window_days,
            escalation_max_attempts: selectedSetting.escalation_max_attempts,
            fairness_reweighting_enabled: selectedSetting.fairness_reweighting_enabled,
            fairness_target_dimensions: selectedSetting.fairness_target_dimensions,
            fairness_max_gap: selectedSetting.fairness_max_gap,
            fairness_min_group_size: selectedSetting.fairness_min_group_size,
          });
        }
        if (selectedValidation) {
          setProgramValidationForm({
            shadow_mode_enabled: selectedValidation.shadow_mode_enabled,
            shadow_prediction_window_days: selectedValidation.shadow_prediction_window_days,
            minimum_precision_at_capacity: selectedValidation.minimum_precision_at_capacity,
            minimum_recall_at_capacity: selectedValidation.minimum_recall_at_capacity,
            require_fairness_review: selectedValidation.require_fairness_review,
          });
        }
        if (selectedPolicy) {
          setProgramDataPolicyForm({
            storage_mode: selectedPolicy.storage_mode,
            data_residency_region: selectedPolicy.data_residency_region,
            cross_border_transfers_allowed: selectedPolicy.cross_border_transfers_allowed,
            pii_tokenization_enabled: selectedPolicy.pii_tokenization_enabled,
            consent_required: selectedPolicy.consent_required,
            federated_learning_enabled: selectedPolicy.federated_learning_enabled,
          });
        }
      });
    } catch (caughtError) {
      if (!bundle && typeof window !== "undefined") {
        const cached = window.localStorage.getItem(APP_BUNDLE_STORAGE_KEY);
        if (cached) {
          try {
            const parsed = JSON.parse(cached) as AppData;
            setBundle(parsed);
            setNotice("Using the last cached workspace snapshot while the API is unreachable.");
            return;
          } catch {
            window.localStorage.removeItem(APP_BUNDLE_STORAGE_KEY);
          }
        }
      }
      handleApiFailure(caughtError, "Unable to reach the RetainAI API.");
    }
  }

  useEffect(() => {
    async function bootstrapSession() {
      try {
        setPublicSsoConfig(await fetchSSOConfig());
      } catch {
        // Public SSO config is advisory for the login screen only.
      }

      const searchParams = typeof window !== "undefined" ? new URLSearchParams(window.location.search) : null;
      const oidcCode = searchParams?.get("code");
      const oidcState = searchParams?.get("state");
      if (oidcCode && oidcState) {
        try {
          const session = await exchangeOidcCode({
            code: oidcCode,
            state: oidcState,
            redirect_uri: resolveOidcRedirectUri(),
          });
          setCurrentUser(session.user);
          if (typeof window !== "undefined") {
            window.history.replaceState({}, document.title, window.location.pathname);
          }
          await refreshData(session.user.role);
          setNotice(`Signed in with ${session.user.full_name}.`);
        } catch (caughtError) {
          handleApiFailure(caughtError, "Single sign-on exchange failed.");
        } finally {
          setIsBooting(false);
        }
        return;
      }

      if (!getStoredAccessToken()) {
        setIsBooting(false);
        return;
      }

      try {
        const user = await fetchCurrentUser();
        setCurrentUser(user);
        await refreshData(user.role);
      } catch (caughtError) {
        handleApiFailure(caughtError, "Unable to restore the saved session.");
      } finally {
        setIsBooting(false);
      }
    }

    void bootstrapSession();
  }, []);

  useEffect(() => {
    function handleResize() {
      setMobileLiteEnabled(window.innerWidth <= 760);
    }

    window.addEventListener("resize", handleResize);
    return () => window.removeEventListener("resize", handleResize);
  }, []);

  useEffect(() => {
    setImportAnalysis(null);
    setImportMappingDraft({});
  }, [datasetType]);

  useEffect(() => {
    if (!bundle || !selectedProgramId) {
      return;
    }
    const selectedSetting = bundle.program_settings.find((item) => item.program_id === selectedProgramId);
    if (!selectedSetting) {
      return;
    }
    setProgramSettingForm({
      weekly_followup_capacity: selectedSetting.weekly_followup_capacity,
      worker_count: selectedSetting.worker_count,
      medium_risk_multiplier: selectedSetting.medium_risk_multiplier,
      high_risk_share_floor: selectedSetting.high_risk_share_floor,
      review_window_days: selectedSetting.review_window_days,
      label_definition_preset: selectedSetting.label_definition_preset,
      dropout_inactivity_days: selectedSetting.dropout_inactivity_days,
      prediction_window_days: selectedSetting.prediction_window_days,
      label_noise_strategy: selectedSetting.label_noise_strategy,
      soft_label_weight: selectedSetting.soft_label_weight,
      silent_transfer_detection_enabled: selectedSetting.silent_transfer_detection_enabled,
      low_risk_channel: selectedSetting.low_risk_channel,
      medium_risk_channel: selectedSetting.medium_risk_channel,
      high_risk_channel: selectedSetting.high_risk_channel,
      tracing_sms_delay_days: selectedSetting.tracing_sms_delay_days,
      tracing_call_delay_days: selectedSetting.tracing_call_delay_days,
      tracing_visit_delay_days: selectedSetting.tracing_visit_delay_days,
      escalation_window_days: selectedSetting.escalation_window_days,
      escalation_max_attempts: selectedSetting.escalation_max_attempts,
      fairness_reweighting_enabled: selectedSetting.fairness_reweighting_enabled,
      fairness_target_dimensions: selectedSetting.fairness_target_dimensions,
      fairness_max_gap: selectedSetting.fairness_max_gap,
      fairness_min_group_size: selectedSetting.fairness_min_group_size,
    });
    const selectedValidation = bundle.program_validation_settings.find((item) => item.program_id === selectedProgramId) ?? bundle.program_validation_settings[0];
    if (selectedValidation) {
      setProgramValidationForm({
        shadow_mode_enabled: selectedValidation.shadow_mode_enabled,
        shadow_prediction_window_days: selectedValidation.shadow_prediction_window_days,
        minimum_precision_at_capacity: selectedValidation.minimum_precision_at_capacity,
        minimum_recall_at_capacity: selectedValidation.minimum_recall_at_capacity,
        require_fairness_review: selectedValidation.require_fairness_review,
      });
    }
    const selectedPolicy = (bundle.program_data_policies ?? []).find((item) => item.program_id === selectedProgramId) ?? bundle.program_data_policies?.[0];
    if (selectedPolicy) {
      setProgramDataPolicyForm({
        storage_mode: selectedPolicy.storage_mode,
        data_residency_region: selectedPolicy.data_residency_region,
        cross_border_transfers_allowed: selectedPolicy.cross_border_transfers_allowed,
        pii_tokenization_enabled: selectedPolicy.pii_tokenization_enabled,
        consent_required: selectedPolicy.consent_required,
        federated_learning_enabled: selectedPolicy.federated_learning_enabled,
      });
    }
  }, [bundle, selectedProgramId]);

  const regions = ["All", ...new Set((bundle?.risk_cases ?? []).map((item) => item.region))];
  const programs = ["All", ...new Set((bundle?.risk_cases ?? []).map((item) => item.program))];
  const cohorts = [
    "All",
    ...new Set((bundle?.risk_cases ?? []).map((item) => item.cohort).filter((value): value is string => Boolean(value))),
  ];
  const phases = [
    "All",
    ...new Set((bundle?.risk_cases ?? []).map((item) => item.phase).filter((value): value is string => Boolean(value))),
  ];
  const filteredCases = !bundle
    ? []
    : bundle.risk_cases.filter((item) => {
        const matchesProgram = programFilter === "All" || item.program === programFilter;
        const matchesRisk = riskFilter === "All" || item.risk_level === riskFilter;
        const matchesRegion = regionFilter === "All" || item.region === regionFilter;
        const matchesCohort = cohortFilter === "All" || item.cohort === cohortFilter;
        const matchesPhase = phaseFilter === "All" || item.phase === phaseFilter;
        const query = deferredSearch.trim().toLowerCase();
        const matchesSearch =
          query.length === 0 ||
          item.name.toLowerCase().includes(query) ||
          item.program.toLowerCase().includes(query) ||
          item.region.toLowerCase().includes(query) ||
          (item.cohort ?? "").toLowerCase().includes(query) ||
          (item.phase ?? "").toLowerCase().includes(query);

        return matchesProgram && matchesRisk && matchesRegion && matchesCohort && matchesPhase && matchesSearch;
      });
  const selectedWorkflowCase =
    filteredCases.find((item) => item.id === selectedWorkflowCaseId) ??
    bundle?.risk_cases.find((item) => item.id === selectedWorkflowCaseId) ??
    null;

  async function handleLogin(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setIsAuthenticating(true);
    setNotice(null);
    setError(null);

    try {
      const session = await login(loginForm);
      setCurrentUser(session.user);
      setLoginForm({ email: "", password: "" });
      setNotice(`Signed in as ${session.user.full_name}.`);
      await refreshData(session.user.role);
    } catch (caughtError) {
      handleApiFailure(caughtError, "Sign-in failed.");
    } finally {
      setIsAuthenticating(false);
      setIsBooting(false);
    }
  }

  async function handleOidcSignIn() {
    setIsStartingSso(true);
    setNotice(null);
    setError(null);
    try {
      const start = await startOidcLogin(resolveOidcRedirectUri());
      window.location.assign(start.authorization_url);
    } catch (caughtError) {
      handleApiFailure(caughtError, "Single sign-on could not be started.");
      setIsStartingSso(false);
    }
  }

  async function handleCreateProgram(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setIsSubmitting(true);
    setNotice(null);
    setError(null);

    try {
      const createdProgram = await createProgram(programForm);
      setProgramForm({
        name: "",
        program_type: programForm.program_type,
        country: "",
        delivery_modality: "",
      });
      setSelectedProgramId(createdProgram.id);
      setNotice(`Program created: ${createdProgram.name}`);
      await refreshData();
    } catch (caughtError) {
      handleApiFailure(caughtError, "Program creation failed.");
    } finally {
      setIsSubmitting(false);
    }
  }

  function buildConnectorPayload(): DataConnectorCreatePayload {
    return {
      program_id: connectorForm.program_id,
      name: connectorForm.name,
      connector_type: connectorForm.connector_type,
      dataset_type: connectorForm.dataset_type,
      base_url: connectorForm.base_url,
      resource_path: connectorForm.resource_path,
      auth_scheme: connectorForm.auth_scheme,
      auth_username: connectorForm.auth_username || undefined,
      secret: connectorForm.secret || undefined,
      record_path: connectorForm.record_path || undefined,
      query_params: parseKeyValueJson(connectorForm.query_params_text, "Query params"),
      field_mapping: connectorMappingDraft,
      schedule_enabled: connectorForm.schedule_enabled,
      sync_interval_hours: connectorForm.schedule_enabled ? Number(connectorForm.sync_interval_hours) : null,
      writeback_enabled: connectorForm.writeback_enabled,
      writeback_mode: connectorForm.writeback_enabled ? connectorForm.writeback_mode : "none",
      writeback_resource_path: connectorForm.writeback_resource_path || undefined,
      writeback_field_mapping: parseKeyValueJson(connectorForm.writeback_field_mapping_text, "Write-back mapping"),
      webhook_enabled: connectorForm.webhook_enabled,
      webhook_secret: connectorForm.webhook_secret || undefined,
    };
  }

  async function handleAnalyzeImport() {
    if (!selectedFile) {
      setError("Choose a CSV or Excel file before running import analysis.");
      return;
    }

    setIsAnalyzingImport(true);
    setNotice(null);
    setError(null);

    try {
      const analysis = await analyzeImport(datasetType, selectedFile, importMappingDraft);
      setImportAnalysis(analysis);
      setImportMappingDraft((current) => ({
        ...analysis.suggested_mapping,
        ...current,
      }));
      setNotice(`Import analysis complete: quality score ${analysis.quality_score}/100 across ${analysis.records_received} rows.`);
    } catch (caughtError) {
      handleApiFailure(caughtError, "Import analysis failed.");
    } finally {
      setIsAnalyzingImport(false);
    }
  }

  async function handleCreateConnector(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setIsSubmitting(true);
    setNotice(null);
    setError(null);

    try {
      const payload = buildConnectorPayload();
      const connector = await createConnector(payload);
      setConnectorForm((current) => ({
        ...current,
        name: "",
        base_url: "",
        resource_path: "",
        auth_username: "",
        secret: "",
        record_path: "",
        query_params_text: "{}",
        program_id: connector.program_id,
        writeback_enabled: false,
        writeback_mode: "commcare_case_updates",
        writeback_resource_path: "",
        writeback_field_mapping_text: "{}",
        webhook_enabled: false,
        webhook_secret: "",
      }));
      setConnectorPreview(null);
      setConnectorMappingDraft({});
      setNotice(`Connector created: ${connector.name}`);
      await refreshData();
    } catch (caughtError) {
      handleApiFailure(caughtError, "Connector creation failed.");
    } finally {
      setIsSubmitting(false);
    }
  }

  async function handlePreviewConnector() {
    setIsPreviewingConnector(true);
    setNotice(null);
    setError(null);

    try {
      const payload = buildConnectorPayload();
      const preview = await previewConnector(payload);
      setConnectorPreview(preview);
      setConnectorMappingDraft((current) => ({
        ...preview.inferred_mapping,
        ...current,
      }));
      setNotice(`Connector preview complete: ${preview.message}`);
    } catch (caughtError) {
      handleApiFailure(caughtError, "Connector preview failed.");
    } finally {
      setIsPreviewingConnector(false);
    }
  }

  async function handleImport(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedProgramId || !selectedFile) {
      setError("Select a program and choose a CSV file before importing.");
      return;
    }

    setIsSubmitting(true);
    setNotice(null);
    setError(null);

    try {
      const mapping = Object.fromEntries(
        Object.entries(importMappingDraft).filter(([, value]) => value),
      ) as Record<string, string | null>;
      const batch = await uploadCsvImport(datasetType, selectedProgramId, selectedFile, mapping);
      setSelectedFile(null);
      setImportAnalysis(null);
      setImportMappingDraft({});
      setNotice(`Imported ${batch.records_processed} ${datasetType} records from ${batch.filename}.`);
      await refreshData();
    } catch (caughtError) {
      handleApiFailure(caughtError, "CSV import failed.");
    } finally {
      setIsSubmitting(false);
    }
  }

  async function handleTestConnector(connectorId: string, connectorName: string) {
    setActiveConnectorId(connectorId);
    setNotice(null);
    setError(null);

    try {
      const result = await testConnector(connectorId);
      setNotice(`${connectorName}: ${result.message}`);
      await refreshData();
    } catch (caughtError) {
      handleApiFailure(caughtError, "Connector test failed.");
    } finally {
      setActiveConnectorId(null);
    }
  }

  async function handleSyncConnector(connectorId: string, connectorName: string) {
    setActiveConnectorId(connectorId);
    setNotice(null);
    setError(null);

    try {
      const result = await syncConnector(connectorId);
      setNotice(`${connectorName} sync queued as job ${result.id}.`);
      await refreshData();
    } catch (caughtError) {
      handleApiFailure(caughtError, "Connector sync failed.");
    } finally {
      setActiveConnectorId(null);
    }
  }

  async function handleDispatchConnector(connectorId: string, connectorName: string, previewOnly: boolean) {
    setActiveConnectorId(connectorId);
    setNotice(null);
    setError(null);

    try {
      const run = await dispatchConnectorQueue(connectorId, {
        only_due: true,
        include_this_week: true,
        limit: 250,
        preview_only: previewOnly,
      });
      if (previewOnly) {
        setNotice(
          `Dispatch preview ready for ${connectorName}: ${run.cases_included} cases in scope, ${run.cases_skipped} skipped.`,
        );
      } else {
        setNotice(
          `Dispatched ${run.records_sent || run.cases_included} queue items from ${connectorName} to ${run.target_mode.replace(/_/g, " ")}.`,
        );
      }
      await refreshData();
    } catch (caughtError) {
      handleApiFailure(caughtError, `Connector dispatch failed for ${connectorName}.`);
    } finally {
      setActiveConnectorId(null);
    }
  }

  function handleOpenWorkflow(riskCase: RiskCase) {
    setSelectedWorkflowCaseId(riskCase.id);
    setWorkflowForm(workflowDefaultsFor(riskCase));
    setNotice(`Opened follow-up workflow for ${riskCase.name}.`);
    setError(null);
  }

  function handleWorkflowFieldChange<K extends keyof WorkflowFormState>(field: K, value: WorkflowFormState[K]) {
    setWorkflowForm((current) => ({
      ...current,
      [field]: value,
    }));
  }

  function handleWorkflowSoftSignalChange(field: keyof SoftSignalSnapshot, value: number | null) {
    setWorkflowForm((current) => ({
      ...current,
      soft_signals: {
        ...current.soft_signals,
        [field]: value,
      },
    }));
  }

  async function handleSubmitWorkflow(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedWorkflowCase) {
      setError("Select a beneficiary from the queue before saving a workflow.");
      return;
    }

    setIsSubmitting(true);
    setNotice(null);
    setError(null);

    const payload = {
      action_type: workflowForm.action_type,
      support_channel: workflowForm.support_channel,
      protocol_step: workflowForm.protocol_step,
      status: workflowForm.status,
      verification_status: workflowForm.verification_status,
      assigned_to: workflowForm.assigned_to || null,
      assigned_site: workflowForm.assigned_site || null,
      due_at: workflowForm.due_at ? new Date(workflowForm.due_at).toISOString() : null,
      note: workflowForm.note || null,
      verification_note: workflowForm.verification_note || null,
      dismissal_reason: workflowForm.dismissal_reason || null,
      attempt_count: workflowForm.attempt_count,
      successful: workflowForm.successful,
      source: "risk_queue",
      risk_level: selectedWorkflowCase.risk_level,
      priority_rank: selectedWorkflowCase.queue_rank || null,
      soft_signals: workflowForm.soft_signals,
    };

    try {
      if (selectedWorkflowCase.workflow?.intervention_id) {
        await updateIntervention(selectedWorkflowCase.workflow.intervention_id, payload);
      } else {
        await logIntervention({
          beneficiary_id: selectedWorkflowCase.id,
          ...payload,
        });
      }
      setNotice(`Workflow saved for ${selectedWorkflowCase.name}.`);
      await refreshData();
    } catch (caughtError) {
      handleApiFailure(caughtError, "Workflow update failed.");
    } finally {
      setIsSubmitting(false);
    }
  }

  async function handleQuickLogAction(beneficiaryId: string, riskLevel: RiskLevel) {
    const riskCase = bundle?.risk_cases.find((item) => item.id === beneficiaryId);
    if (!riskCase) {
      setError("Risk case not found in the current bundle.");
      return;
    }
    setIsSubmitting(true);
    setNotice(null);
    setError(null);
    try {
      await logIntervention({
        beneficiary_id: riskCase.id,
        action_type: nextActionLabel(riskLevel),
        support_channel: riskLevel === "High" ? "visit" : "call",
        status: "queued",
        verification_status: "pending",
        assigned_to: riskCase.assigned_worker ?? null,
        assigned_site: riskCase.assigned_site ?? riskCase.region,
        due_at: new Date(Date.now() + (riskLevel === "High" ? 2 : 5) * 24 * 60 * 60 * 1000).toISOString(),
        note: `Queued from mobile-lite mode for ${riskCase.program}.`,
        source: "mobile_lite",
        risk_level: riskLevel,
        priority_rank: riskCase.queue_rank,
        soft_signals: riskCase.soft_signals ?? undefined,
      });
      setNotice(`Follow-up queued for ${riskCase.name}.`);
      await refreshData();
    } catch (caughtError) {
      handleApiFailure(caughtError, "Intervention logging failed.");
    } finally {
      setIsSubmitting(false);
    }
  }

  async function handleTrainModel(force = true) {
    setIsSubmitting(true);
    setNotice(null);
    setError(null);

    try {
      const job = await trainModel(force);
      setNotice(`Model retraining queued as job ${job.id}.`);
      await refreshData();
    } catch (caughtError) {
      handleApiFailure(caughtError, "Model training failed.");
    } finally {
      setIsSubmitting(false);
    }
  }

  async function handleUpdateModelSchedule(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setIsSubmitting(true);
    setNotice(null);
    setError(null);

    try {
      const schedule = await updateModelSchedule(modelScheduleForm);
      setModelScheduleForm({
        cadence: schedule.cadence,
        enabled: schedule.enabled,
        auto_retrain_after_sync: schedule.auto_retrain_after_sync,
      });
      setNotice("Model schedule updated.");
      await refreshData();
    } catch (caughtError) {
      handleApiFailure(caughtError, "Updating model schedule failed.");
    } finally {
      setIsSubmitting(false);
    }
  }

  async function handleUpdateProgramSetting(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedProgramId) {
      setError("Select a program before updating staff-capacity settings.");
      return;
    }

    setIsSubmitting(true);
    setNotice(null);
    setError(null);
    try {
      await updateProgramSetting(selectedProgramId, programSettingForm);
      setNotice("Program capacity settings updated.");
      await refreshData();
    } catch (caughtError) {
      handleApiFailure(caughtError, "Updating program capacity settings failed.");
    } finally {
      setIsSubmitting(false);
    }
  }

  async function handleUpdateProgramValidation(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedProgramId) {
      setError("Select a program before updating validation settings.");
      return;
    }

    setIsSubmitting(true);
    setNotice(null);
    setError(null);
    try {
      await updateProgramValidationSetting(selectedProgramId, programValidationForm);
      setNotice("Program validation settings updated.");
      await refreshData();
    } catch (caughtError) {
      handleApiFailure(caughtError, "Updating validation settings failed.");
    } finally {
      setIsSubmitting(false);
    }
  }

  async function handleUpdateProgramDataPolicy(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedProgramId) {
      setError("Select a program before updating data policy.");
      return;
    }

    setIsSubmitting(true);
    setNotice(null);
    setError(null);

    try {
      await updateProgramDataPolicy(selectedProgramId, programDataPolicyForm);
      setNotice("Program data policy updated.");
      await refreshData();
    } catch (caughtError) {
      handleApiFailure(caughtError, "Updating program data policy failed.");
    } finally {
      setIsSubmitting(false);
    }
  }

  async function handleRunBacktest() {
    if (!selectedProgramId) {
      setError("Select a program before running a backtest.");
      return;
    }

    setIsSubmitting(true);
    setNotice(null);
    setError(null);
    try {
      const topKCapacity = evaluationForm.top_k_capacity_text.trim()
        ? Number(evaluationForm.top_k_capacity_text.trim())
        : null;
      const report = await runModelBacktest({
        temporal_strategy: evaluationForm.temporal_strategy,
        horizon_days: programValidationForm.shadow_prediction_window_days,
        min_history_days: evaluationForm.min_history_days,
        holdout_share: evaluationForm.holdout_share,
        rolling_folds: evaluationForm.rolling_folds,
        program_ids: [selectedProgramId],
        cohorts: [],
        top_k_share: evaluationForm.top_k_share,
        top_k_capacity: Number.isFinite(topKCapacity ?? NaN) ? topKCapacity : null,
        calibration_bins: evaluationForm.calibration_bins,
        bootstrap_iterations: evaluationForm.bootstrap_iterations,
      });
      setNotice(
        `Backtest complete: ${report.status.replace(/_/g, " ")} with precision@K ${Math.round(report.metrics.top_k_precision.value * 100)}%.`,
      );
      await refreshData();
    } catch (caughtError) {
      handleApiFailure(caughtError, "Backtest evaluation failed.");
    } finally {
      setIsSubmitting(false);
    }
  }

  async function handleCreateShadowRun() {
    if (!selectedProgramId) {
      setError("Select a program before capturing a shadow run.");
      return;
    }

    setIsSubmitting(true);
    setNotice(null);
    setError(null);
    try {
      const topKCapacity = evaluationForm.top_k_capacity_text.trim()
        ? Number(evaluationForm.top_k_capacity_text.trim())
        : null;
      const run = await createShadowRun(selectedProgramId, {
        top_k_count: Number.isFinite(topKCapacity ?? NaN) ? topKCapacity : null,
        note: "Captured from the validation panel.",
      });
      setNotice(`Shadow run captured for ${run.program_name}: ${run.cases_captured} cases with top-K ${run.top_k_count}.`);
      await refreshData();
    } catch (caughtError) {
      handleApiFailure(caughtError, "Shadow-run capture failed.");
    } finally {
      setIsSubmitting(false);
    }
  }

  async function handleRunDueAutomation() {
    setIsSubmitting(true);
    setNotice(null);
    setError(null);

    try {
      const job = await runDueAutomation();
      setNotice(`Scheduled automation queued as job ${job.id}.`);
      await refreshData();
    } catch (caughtError) {
      handleApiFailure(caughtError, "Running scheduled automation failed.");
    } finally {
      setIsSubmitting(false);
    }
  }

  async function handleRunPendingJobs() {
    setIsSubmitting(true);
    setNotice(null);
    setError(null);

    try {
      const summary = await runPendingJobs(10);
      setNotice(
        summary.processed === 0
          ? "No queued jobs were ready to run."
          : `Executed ${summary.processed} queued job${summary.processed === 1 ? "" : "s"}.`,
      );
      await refreshData();
    } catch (caughtError) {
      handleApiFailure(caughtError, "Running queued jobs failed.");
    } finally {
      setIsSubmitting(false);
    }
  }

  async function handleRequeueJob(jobId: string) {
    setIsSubmitting(true);
    setNotice(null);
    setError(null);

    try {
      const job = await requeueJob(jobId);
      setNotice(`${formatJobType(job.job_type)} was re-queued for another execution attempt.`);
      await refreshData();
    } catch (caughtError) {
      handleApiFailure(caughtError, "Re-queueing the job failed.");
    } finally {
      setIsSubmitting(false);
    }
  }

  async function handleToggleOptOut(beneficiaryId: string, optedOut: boolean) {
    setIsSubmitting(true);
    setNotice(null);
    setError(null);

    try {
      const updated = await updateBeneficiaryGovernance(beneficiaryId, { opted_out: optedOut });
      setNotice(
        updated.opted_out
          ? `${updated.full_name} will be excluded from model training and scored heuristically only.`
          : `${updated.full_name} has been returned to model training eligibility.`,
      );
      await refreshData();
    } catch (caughtError) {
      handleApiFailure(caughtError, "Updating beneficiary governance failed.");
    } finally {
      setIsSubmitting(false);
    }
  }

  async function handleConsentUpdate(
    beneficiaryId: string,
    status: "granted" | "pending" | "declined" | "withdrawn" | "waived",
  ) {
    setIsSubmitting(true);
    setNotice(null);
    setError(null);

    try {
      const updated = await updateBeneficiaryGovernance(beneficiaryId, {
        opted_out: status === "declined" || status === "withdrawn",
        modeling_consent_status: status,
        explained_to_beneficiary: true,
        consent_method: "dashboard_update",
      });
      setNotice(`Consent status for ${updated.full_name} updated to ${updated.modeling_consent_status}.`);
      await refreshData();
    } catch (caughtError) {
      handleApiFailure(caughtError, "Updating beneficiary consent failed.");
    } finally {
      setIsSubmitting(false);
    }
  }

  async function handleShowExplanation(beneficiaryId: string) {
    setIsSubmitting(true);
    setNotice(null);
    setError(null);

    try {
      const explanation = await fetchBeneficiaryExplanation(beneficiaryId);
      setSelectedExplanation(
        `${explanation.beneficiary_label}: ${explanation.explanation}\n\n${explanation.beneficiary_facing_summary}\n\n${explanation.data_points_used.join("\n")}`,
      );
    } catch (caughtError) {
      handleApiFailure(caughtError, "Loading beneficiary explanation failed.");
    } finally {
      setIsSubmitting(false);
    }
  }

  async function handleExport(dataset: "risk_cases" | "interventions") {
    setIsSubmitting(true);
    setNotice(null);
    setError(null);

    try {
      const blob =
        dataset === "risk_cases"
          ? await exportRiskCases("weekly_retention_review", false)
          : await exportInterventions("weekly_retention_review", false);
      downloadBlob(blob, dataset === "risk_cases" ? "risk-cases.csv" : "interventions.csv");
      setNotice(
        dataset === "risk_cases"
          ? "Pseudonymized risk queue export generated."
          : "Pseudonymized intervention export generated.",
      );
      await refreshData();
    } catch (caughtError) {
      handleApiFailure(caughtError, "Export failed.");
    } finally {
      setIsSubmitting(false);
    }
  }

  async function handleFollowUpExport(mode: "whatsapp" | "sms" | "field_visit") {
    setIsSubmitting(true);
    setNotice(null);
    setError(null);

    try {
      const blob = await exportFollowUpList(mode, {
        purpose: "weekly_retention_review",
        include_pii: false,
        program_id: programFilter === "All" ? null : bundle?.programs.find((item) => item.name === programFilter)?.id ?? null,
        risk_level: riskFilter === "All" ? null : riskFilter,
        region: regionFilter === "All" ? null : regionFilter,
        cohort: cohortFilter === "All" ? null : cohortFilter,
        phase: phaseFilter === "All" ? null : phaseFilter,
        search: deferredSearch.trim() || null,
      });
      const filename =
        mode === "whatsapp"
          ? "whatsapp-follow-up-list.csv"
          : mode === "sms"
            ? "sms-follow-up-list.csv"
            : "field-visit-schedule.csv";
      downloadBlob(blob, filename);
      setNotice(
        mode === "field_visit"
          ? "Field visit schedule exported."
          : `${mode.toUpperCase()} follow-up list exported.`,
      );
      await refreshData();
    } catch (caughtError) {
      handleApiFailure(caughtError, "Follow-up export failed.");
    } finally {
      setIsSubmitting(false);
    }
  }

  async function handleDonorExport(format: "xlsx" | "pdf") {
    setIsSubmitting(true);
    setNotice(null);
    setError(null);
    try {
      const blob = format === "xlsx" ? await exportDonorWorkbook() : await exportDonorPdf();
      downloadBlob(blob, format === "xlsx" ? "retainai-donor-summary.xlsx" : "retainai-donor-summary.pdf");
      setNotice(format === "xlsx" ? "Donor workbook exported." : "Donor PDF summary exported.");
      await refreshData();
    } catch (caughtError) {
      handleApiFailure(caughtError, "Donor export failed.");
    } finally {
      setIsSubmitting(false);
    }
  }

  async function handleExportFederatedUpdate() {
    setIsSubmitting(true);
    setNotice(null);
    setError(null);
    try {
      await exportFederatedUpdate(federatedRoundName, "web-dashboard", selectedProgramId || undefined);
      setNotice(`Federated update exported into ${federatedRoundName}.`);
      await refreshData();
    } catch (caughtError) {
      handleApiFailure(caughtError, "Exporting federated update failed.");
    } finally {
      setIsSubmitting(false);
    }
  }

  async function handleAggregateFederatedRound() {
    setIsSubmitting(true);
    setNotice(null);
    setError(null);
    try {
      const round = await aggregateFederatedRound(federatedRoundName);
      setNotice(`Federated round ${round.round_name} aggregated.`);
      await refreshData();
    } catch (caughtError) {
      handleApiFailure(caughtError, "Aggregating federated round failed.");
    } finally {
      setIsSubmitting(false);
    }
  }

  async function handleSignOut() {
    try {
      await logout();
    } catch {
      clearAccessToken();
    } finally {
      setCurrentUser(null);
      setBundle(null);
      setNotice(null);
      setError(null);
      setIsBooting(false);
    }
  }

  if (isBooting) {
    return (
      <StatusScreen
        eyebrow="RetainAI"
        title="Checking secure session state"
        message="Loading the authenticated workspace, role entitlements, and latest retention analytics."
      />
    );
  }

  if (!currentUser) {
    return (
      <AuthScreen
        error={error}
        effectiveSsoConfig={effectiveSsoConfig}
        loginForm={loginForm}
        isAuthenticating={isAuthenticating}
        isStartingSso={isStartingSso}
        showDevelopmentAccounts={SHOW_DEVELOPMENT_ACCOUNTS}
        developmentAccounts={DEVELOPMENT_ACCOUNTS}
        onEmailChange={(value) => setLoginForm((current) => ({ ...current, email: value }))}
        onPasswordChange={(value) => setLoginForm((current) => ({ ...current, password: value }))}
        onSubmit={handleLogin}
        onStartSso={() => void handleOidcSignIn()}
      />
    );
  }

  if (!bundle && !error) {
    return (
      <StatusScreen
        eyebrow="RetainAI"
        title="Booting the operations workspace"
        message="Checking service health, loading programs, and calculating live retention analytics."
      />
    );
  }

  if (!bundle) {
    return (
      <StatusScreen eyebrow="RetainAI" title="API connection required" message={error ?? "The API is unavailable."}>
        <div className="session-actions">
          <button className="primary-button" type="button" onClick={() => void refreshData(currentRole)}>
            Retry connection
          </button>
          <button className="secondary-button" type="button" onClick={handleSignOut}>
            Sign out
          </button>
        </div>
      </StatusScreen>
    );
  }

  const driverMax = Math.max(
    1,
    ...bundle.summary.top_risk_drivers.map((driver) => driver.impacted_beneficiaries),
  );
  const latestImport = bundle.imports[0];
  const modelStatus = bundle.summary.model_status;
  const modelSchedule = bundle.model_schedule;
  const biasAudit = modelStatus.bias_audit;
  const recentJobs = bundle.jobs;
  const governanceBeneficiaries = bundle.governance_beneficiaries;
  const governanceAlerts = bundle.governance_alerts;
  const selectedProgramSetting = bundle.program_settings.find((item) => item.program_id === selectedProgramId) ?? bundle.program_settings[0];
  const selectedProgramValidation =
    bundle.program_validation_settings.find((item) => item.program_id === selectedProgramId) ??
    bundle.program_validation_settings[0];
  const selectedProgramDataPolicy = (bundle.program_data_policies ?? []).find((item) => item.program_id === selectedProgramId) ?? bundle.program_data_policies?.[0];
  const selectedProgramEvaluations = selectedProgramId
    ? bundle.model_evaluations.filter((item) => item.program_ids.includes(selectedProgramId))
    : bundle.model_evaluations;
  const selectedProgramShadowRuns = selectedProgramId
    ? bundle.shadow_runs.filter((item) => item.program_id === selectedProgramId)
    : bundle.shadow_runs;
  const donorSummary = bundle.donor_report_summary;
  const interventionEffectiveness = bundle.intervention_effectiveness;
  const retentionAnalytics = bundle.retention_analytics;

  if (mobileLiteEnabled) {
    return (
      <div className="app-shell">
        <div className="background-orb orb-one" />
        <div className="background-orb orb-two" />
        <main className="layout">
          {notice ? <div className="callout success-callout">{notice}</div> : null}
          {error ? <div className="callout error-callout">{error}</div> : null}
          {selectedExplanation ? (
            <div className="callout info-callout">
              <strong>Beneficiary explanation</strong>
              <pre className="inline-pre">{selectedExplanation}</pre>
            </div>
          ) : null}
          <MobileLiteView
            bundle={bundle}
            currentUser={currentUser}
            isSubmitting={isSubmitting}
            allowInterventionLogging={allowInterventionLogging}
            onLogIntervention={(beneficiaryId, riskLevel) => void handleQuickLogAction(beneficiaryId, riskLevel)}
            onExplain={(beneficiaryId) => void handleShowExplanation(beneficiaryId)}
          />
        </main>
      </div>
    );
  }

  return (
    <div className="app-shell">
      <div className="background-orb orb-one" />
      <div className="background-orb orb-two" />
      <main className="layout">
        {notice ? <div className="callout success-callout">{notice}</div> : null}
        {error ? <div className="callout error-callout">{error}</div> : null}
        {selectedExplanation ? (
          <div className="callout info-callout">
            <strong>Beneficiary explanation</strong>
            <pre className="inline-pre">{selectedExplanation}</pre>
          </div>
        ) : null}
        <section className="hero panel">
          <div>
            <span className="eyebrow">Operational Dropout Prediction For NGO Teams</span>
            <h1>Run retention operations off secure, role-aware program data.</h1>
            <p className="hero-copy">
              RetainAI now enforces authenticated access, audit logging, and role-specific controls
              on top of live retention analytics and intervention queues.
            </p>
            <div className="hero-badges">
              <span className="badge badge-cool">{bundle.health.environment}</span>
              <span className="badge badge-outline">{bundle.programs.length} programs live</span>
              <span className="badge badge-outline">{formatRole(currentUser.role)}</span>
              {bundle.sso_config.enabled ? (
                <span className="badge badge-outline">
                  {bundle.sso_config.provider_label ?? "SSO enabled"} {bundle.sso_config.mode.toUpperCase()}
                </span>
              ) : null}
              <span className={`badge ${bundle.runtime_status.status === "ok" ? "badge-cool" : "badge-warm"}`}>
                Runtime {bundle.runtime_status.status}
              </span>
              <span className={`badge ${bundle.worker_health.status === "healthy" ? "badge-cool" : "badge-warm"}`}>
                Queue {bundle.worker_health.status}
              </span>
              {bundle.worker_health.dead_letter > 0 ? (
                <span className="badge badge-warm">{bundle.worker_health.dead_letter} dead-letter</span>
              ) : null}
              <span className="badge badge-outline">
                {latestImport ? `Last import ${formatDate(latestImport.created_at)}` : "No CSV imports yet"}
              </span>
            </div>
          </div>

          <aside className="hero-sidebar">
            <div className="model-card">
              <span className="meta-label">Signed in</span>
              <strong>{currentUser.full_name}</strong>
              <p>{currentUser.email}</p>
              <div className="meta-stack">
                <span>Role: {formatRole(currentUser.role)}</span>
                <span>
                  Last login: {currentUser.last_login_at ? formatTimestamp(currentUser.last_login_at) : "First session"}
                </span>
              </div>
              <button className="secondary-button" type="button" onClick={handleSignOut}>
                Sign out
              </button>
            </div>
            <div className="model-card">
              <span className="meta-label">Operations health</span>
              <strong>Runtime {bundle.runtime_status.status}</strong>
              <p>
                Region {bundle.runtime_status.deployment_region} | Backend {bundle.worker_health.backend}
              </p>
              <div className="meta-stack">
                <span>
                  Queue: {bundle.worker_health.queued} queued / {bundle.worker_health.running} running
                </span>
                <span>
                  Retries: {bundle.worker_health.max_attempts} max / {bundle.worker_health.retry_backoff_seconds}s backoff
                </span>
                <span>
                  Workers: {bundle.worker_health.workers.length > 0 ? bundle.worker_health.workers.join(", ") : bundle.worker_health.worker_status}
                </span>
              </div>
              {bundle.runtime_status.violations.length > 0 ? (
                <p className="inline-helper">{bundle.runtime_status.violations[0]?.issue}</p>
              ) : bundle.runtime_status.warnings.length > 0 ? (
                <p className="inline-helper">{bundle.runtime_status.warnings[0]}</p>
              ) : bundle.worker_health.dead_letter > 0 ? (
                <p className="inline-helper">One or more jobs have dead-lettered and need operator review.</p>
              ) : (
                <p className="inline-helper">Residency, queue, and worker checks are currently clear.</p>
              )}
            </div>

            <div className="model-card">
              <span className="meta-label">Scoring engine</span>
              <strong>{modelStatus.model_mode}</strong>
              <p>{bundle.summary.quality_note}</p>
              <div className="meta-stack">
                <span>Algorithm: {modelStatus.algorithm}</span>
                {modelStatus.mlflow_run_id ? <span>MLflow run: {modelStatus.mlflow_run_id}</span> : null}
                <span>Status: {modelStatus.status}</span>
                <span>
                  Trained: {modelStatus.trained_at ? formatTimestamp(modelStatus.trained_at) : "Not yet trained"}
                </span>
              </div>
              {allowModelTraining ? (
                <button
                  className="secondary-button"
                  type="button"
                  onClick={() => void handleTrainModel(true)}
                  disabled={isSubmitting}
                >
                  {isSubmitting ? "Working..." : "Retrain model"}
                </button>
              ) : (
                <p className="inline-helper">Model retraining is restricted to admins and M&E officers.</p>
              )}
            </div>
            <div className="model-card">
              <span className="meta-label">Model card snapshot</span>
              <strong>{formatMetricValue(modelStatus.metrics.auc_roc)}</strong>
              <p>
                AUC-ROC. Precision {formatMetricValue(modelStatus.metrics.precision)}. Recall{" "}
                {formatMetricValue(modelStatus.metrics.recall)}.
              </p>
              <div className="flag-row">
                {modelStatus.top_drivers.slice(0, 3).map((driver) => (
                  <span className="flag-chip" key={driver.name}>
                    {driver.name}
                  </span>
                ))}
              </div>
            </div>
          </aside>
        </section>

        <section className="metrics-grid">
          <article className="metric-card neutral">
            <span>Active beneficiaries</span>
            <strong>{bundle.summary.active_beneficiaries.toLocaleString()}</strong>
          </article>
          <article className="metric-card urgent">
            <span>High-risk cases</span>
            <strong>{bundle.summary.high_risk_cases.toLocaleString()}</strong>
          </article>
          <article className="metric-card warning">
            <span>Predicted 30-day dropout</span>
            <strong>{bundle.summary.predicted_30_day_dropout.toLocaleString()}</strong>
          </article>
          <article className="metric-card positive">
            <span>Re-engagement rate</span>
            <strong>{bundle.summary.intervention_success_rate}%</strong>
          </article>
        </section>

        <AnalyticsOverview
          summary={bundle.summary}
          retentionCurves={bundle.retention_curves}
          modelStatus={modelStatus}
          biasAudit={biasAudit}
          retentionAnalytics={retentionAnalytics}
          interventionEffectiveness={interventionEffectiveness}
          donorSummary={donorSummary}
          federatedRounds={bundle.federated_rounds}
          federatedRoundName={federatedRoundName}
          driverMax={driverMax}
          allowExports={allowExports}
          allowModelTraining={allowModelTraining}
          isRefreshing={isRefreshing}
          isSubmitting={isSubmitting}
          onRefresh={() => void refreshData(currentRole)}
          onDonorExport={(format) => void handleDonorExport(format)}
          onFederatedRoundNameChange={setFederatedRoundName}
          onExportFederatedUpdate={() => void handleExportFederatedUpdate()}
          onAggregateFederatedRound={() => void handleAggregateFederatedRound()}
          formatMetricValue={formatMetricValue}
          formatRate={formatRate}
          formatBiasDimension={formatBiasDimension}
        />

        <ValidationSection
          allowProgramAdmin={allowProgramAdmin}
          isSubmitting={isSubmitting}
          programs={bundle.programs}
          selectedProgramId={selectedProgramId}
          selectedProgramValidation={selectedProgramValidation}
          validationForm={programValidationForm}
          evaluationForm={evaluationForm}
          evaluations={selectedProgramEvaluations}
          shadowRuns={selectedProgramShadowRuns}
          onSelectedProgramIdChange={setSelectedProgramId}
          onValidationFormChange={(field, value) =>
            setProgramValidationForm((current) => ({
              ...current,
              [field]: value,
            }))
          }
          onEvaluationFormChange={(field, value) =>
            setEvaluationForm((current) => ({
              ...current,
              [field]: value,
            }))
          }
          onUpdateProgramValidation={handleUpdateProgramValidation}
          onRunBacktest={() => void handleRunBacktest()}
          onCreateShadowRun={() => void handleCreateShadowRun()}
          formatTimestamp={formatTimestamp}
          formatRate={formatRate}
        />

        <RiskQueueSection
          allowExports={allowExports}
          allowInterventionLogging={allowInterventionLogging}
          isSubmitting={isSubmitting}
          filteredCases={filteredCases}
          interventions={bundle.interventions}
          selectedWorkflowCase={selectedWorkflowCase}
          workflowForm={workflowForm}
          search={search}
          riskFilter={riskFilter}
          programFilter={programFilter}
          regionFilter={regionFilter}
          cohortFilter={cohortFilter}
          phaseFilter={phaseFilter}
          programs={programs}
          regions={regions}
          cohorts={cohorts}
          phases={phases}
          onSearchChange={setSearch}
          onRiskFilterChange={setRiskFilter}
          onProgramFilterChange={setProgramFilter}
          onRegionFilterChange={setRegionFilter}
          onCohortFilterChange={setCohortFilter}
          onPhaseFilterChange={setPhaseFilter}
          onExport={(dataset) => void handleExport(dataset)}
          onFollowUpExport={(mode) => void handleFollowUpExport(mode)}
          onLogAction={handleOpenWorkflow}
          onWorkflowFieldChange={handleWorkflowFieldChange}
          onWorkflowSoftSignalChange={handleWorkflowSoftSignalChange}
          onSubmitWorkflow={(event) => void handleSubmitWorkflow(event)}
          onCloseWorkflow={() => setSelectedWorkflowCaseId(null)}
          nextActionLabel={nextActionLabel}
          formatTimestamp={formatTimestamp}
        />

        <GovernanceSection
          governanceAlerts={governanceAlerts}
          governanceBeneficiaries={governanceBeneficiaries}
          allowGovernanceManagement={allowGovernanceManagement}
          isSubmitting={isSubmitting}
          onShowExplanation={(beneficiaryId) => void handleShowExplanation(beneficiaryId)}
          onToggleOptOut={(beneficiaryId, optedOut) => void handleToggleOptOut(beneficiaryId, optedOut)}
          onConsentUpdate={(beneficiaryId, consentStatus) => void handleConsentUpdate(beneficiaryId, consentStatus)}
        />
        <OperationsSection
          allowProgramAdmin={allowProgramAdmin}
          allowModelTraining={allowModelTraining}
          showAuditLogs={showAuditLogs}
          isSubmitting={isSubmitting}
          isAnalyzingImport={isAnalyzingImport}
          isPreviewingConnector={isPreviewingConnector}
          activeConnectorId={activeConnectorId}
          programs={bundle.programs}
          imports={bundle.imports}
          auditLogs={bundle.audit_logs}
          connectors={bundle.connectors}
          connectorSyncRuns={bundle.connector_sync_runs}
          recentJobs={recentJobs}
          modelSchedule={bundle.model_schedule}
          programForm={programForm}
          datasetType={datasetType}
          selectedProgramId={selectedProgramId}
          selectedFileName={selectedFile?.name ?? null}
          importAnalysis={importAnalysis}
          importMappingDraft={importMappingDraft}
          connectorPreview={connectorPreview}
          connectorMappingDraft={connectorMappingDraft}
          connectorForm={connectorForm}
          modelScheduleForm={modelScheduleForm}
          programSettingForm={programSettingForm}
          programDataPolicyForm={programDataPolicyForm}
          selectedProgramSettingUpdatedAt={selectedProgramSetting?.updated_at ?? null}
          selectedProgramDataPolicy={selectedProgramDataPolicy}
          datasetMappingFields={DATASET_MAPPING_FIELDS}
          connectorTypeOptions={CONNECTOR_TYPE_OPTIONS}
          authSchemeOptions={AUTH_SCHEME_OPTIONS}
          cadenceOptions={CADENCE_OPTIONS}
          syncIntervalOptions={SYNC_INTERVAL_OPTIONS}
          onCreateProgram={handleCreateProgram}
          onProgramFormChange={(field, value) => setProgramForm((current) => ({ ...current, [field]: value }))}
          onDatasetTypeChange={setDatasetType}
          onSelectedProgramIdChange={setSelectedProgramId}
          onFileChange={(file) => {
            setSelectedFile(file);
            setImportAnalysis(null);
            setImportMappingDraft({});
          }}
          onAnalyzeImport={() => void handleAnalyzeImport()}
          onImportMappingChange={(field, value) =>
            setImportMappingDraft((current) => ({
              ...current,
              [field]: value,
            }))
          }
          onSubmitImport={handleImport}
          onUpdateProgramSetting={handleUpdateProgramSetting}
          onProgramSettingFormChange={(field, value) =>
            setProgramSettingForm((current) => ({
              ...current,
              [field]: value,
            }))
          }
          onUpdateProgramDataPolicy={handleUpdateProgramDataPolicy}
          onProgramDataPolicyFormChange={(field, value) =>
            setProgramDataPolicyForm((current) => ({
              ...current,
              [field]: value,
            }))
          }
          onCreateConnector={handleCreateConnector}
          onConnectorFormChange={(field, value) =>
            setConnectorForm((current) => ({
              ...current,
              [field]: value,
            }))
          }
          onPreviewConnector={() => void handlePreviewConnector()}
          onConnectorMappingChange={(field, value) =>
            setConnectorMappingDraft((current) => ({
              ...current,
              [field]: value,
            }))
          }
          onTestConnector={(connectorId, connectorName) => void handleTestConnector(connectorId, connectorName)}
          onSyncConnector={(connectorId, connectorName) => void handleSyncConnector(connectorId, connectorName)}
          onUpdateModelSchedule={handleUpdateModelSchedule}
          onModelScheduleFormChange={(field, value) =>
            setModelScheduleForm((current) => ({
              ...current,
              [field]: value,
            }))
          }
          onRunDueAutomation={() => void handleRunDueAutomation()}
          onRunPendingJobs={() => void handleRunPendingJobs()}
          onRequeueJob={(jobId) => void handleRequeueJob(jobId)}
          formatTimestamp={formatTimestamp}
          formatMappingField={formatMappingField}
          formatPaginationMode={formatPaginationMode}
          formatJobType={formatJobType}
          formatJobStatus={formatJobStatus}
          jobStatusTone={jobStatusTone}
        />
        <ConnectorAutomationSection
          allowProgramAdmin={allowProgramAdmin}
          allowModelTraining={allowModelTraining}
          isSubmitting={isSubmitting}
          isPreviewingConnector={isPreviewingConnector}
          activeConnectorId={activeConnectorId}
          programs={bundle.programs}
          connectors={bundle.connectors}
          connectorSyncRuns={bundle.connector_sync_runs}
          connectorDispatchRuns={bundle.connector_dispatch_runs}
          connectorPreview={connectorPreview}
          connectorMappingDraft={connectorMappingDraft}
          connectorForm={connectorForm}
          modelSchedule={modelSchedule}
          modelScheduleForm={modelScheduleForm}
          recentJobs={recentJobs}
          datasetMappingFields={DATASET_MAPPING_FIELDS}
          connectorTypeOptions={CONNECTOR_TYPE_OPTIONS}
          authSchemeOptions={AUTH_SCHEME_OPTIONS}
          cadenceOptions={CADENCE_OPTIONS}
          syncIntervalOptions={SYNC_INTERVAL_OPTIONS}
          onCreateConnector={handleCreateConnector}
          onConnectorFormChange={(field, value) =>
            setConnectorForm((current) => ({
              ...current,
              [field]: value,
            }))
          }
          onPreviewConnector={() => void handlePreviewConnector()}
          onConnectorMappingChange={(field, value) =>
            setConnectorMappingDraft((current) => ({
              ...current,
              [field]: value,
            }))
          }
          onTestConnector={(connectorId, connectorName) => void handleTestConnector(connectorId, connectorName)}
          onSyncConnector={(connectorId, connectorName) => void handleSyncConnector(connectorId, connectorName)}
          onDispatchConnector={(connectorId, connectorName, previewOnly) =>
            void handleDispatchConnector(connectorId, connectorName, previewOnly)
          }
          onUpdateModelSchedule={handleUpdateModelSchedule}
          onModelScheduleFormChange={(field, value) =>
            setModelScheduleForm((current) => ({
              ...current,
              [field]: value,
            }))
          }
          onRunDueAutomation={() => void handleRunDueAutomation()}
          onRunPendingJobs={() => void handleRunPendingJobs()}
          onRequeueJob={(jobId) => void handleRequeueJob(jobId)}
          formatTimestamp={formatTimestamp}
          formatMappingField={formatMappingField}
          formatPaginationMode={formatPaginationMode}
          formatJobType={formatJobType}
          formatJobStatus={formatJobStatus}
          jobStatusTone={jobStatusTone}
        />
      </main>
    </div>
  );
}

export default App;
