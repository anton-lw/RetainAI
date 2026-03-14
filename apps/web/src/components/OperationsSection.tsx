/**
 * Program-level operational settings editor.
 *
 * This section owns the "how should the program behave?" controls:
 *
 * - label-definition presets
 * - worker and site capacity assumptions
 * - escalation windows and support-channel defaults
 * - validation and queue-tuning settings surfaced to administrators
 */

import type { FormEventHandler } from "react";

import type {
  AuditLogRecord,
  AuthScheme,
  ConnectorProbeResult,
  ConnectorType,
  DataConnector,
  DataConnectorSyncRun,
  DatasetType,
  ImportAnalysis,
  ImportBatch,
  JobRecord,
  ModelCadence,
  ModelSchedule,
  Program,
  ProgramDataPolicy,
} from "../types";

interface ProgramFormState {
  name: string;
  program_type: string;
  country: string;
  delivery_modality?: string;
}

interface ProgramSettingFormState {
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
}

interface ProgramDataPolicyFormState {
  storage_mode: ProgramDataPolicy["storage_mode"];
  data_residency_region: string;
  cross_border_transfers_allowed: boolean;
  pii_tokenization_enabled: boolean;
  consent_required: boolean;
  federated_learning_enabled: boolean;
}

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
  webhook_enabled: boolean;
  webhook_secret: string;
}

interface OperationsSectionProps {
  allowProgramAdmin: boolean;
  allowModelTraining: boolean;
  showAuditLogs: boolean;
  isSubmitting: boolean;
  isAnalyzingImport: boolean;
  isPreviewingConnector: boolean;
  activeConnectorId: string | null;
  programs: Program[];
  imports: ImportBatch[];
  auditLogs: AuditLogRecord[];
  connectors: DataConnector[];
  connectorSyncRuns: DataConnectorSyncRun[];
  recentJobs: JobRecord[];
  modelSchedule: ModelSchedule;
  programForm: ProgramFormState;
  datasetType: DatasetType;
  selectedProgramId: string;
  selectedFileName: string | null;
  importAnalysis: ImportAnalysis | null;
  importMappingDraft: Record<string, string | null>;
  connectorPreview: ConnectorProbeResult | null;
  connectorMappingDraft: Record<string, string | null>;
  connectorForm: ConnectorFormState;
  modelScheduleForm: {
    cadence: ModelCadence;
    enabled: boolean;
    auto_retrain_after_sync: boolean;
  };
  programSettingForm: ProgramSettingFormState;
  programDataPolicyForm: ProgramDataPolicyFormState;
  selectedProgramSettingUpdatedAt?: string | null;
  selectedProgramDataPolicy?: ProgramDataPolicy | null;
  datasetMappingFields: Record<DatasetType, string[]>;
  connectorTypeOptions: Array<{ value: ConnectorType; label: string }>;
  authSchemeOptions: Array<{ value: AuthScheme; label: string }>;
  cadenceOptions: Array<{ value: ModelCadence; label: string }>;
  syncIntervalOptions: Array<{ value: string; label: string }>;
  onCreateProgram: FormEventHandler<HTMLFormElement>;
  onProgramFormChange: (field: keyof ProgramFormState, value: string) => void;
  onDatasetTypeChange: (value: DatasetType) => void;
  onSelectedProgramIdChange: (value: string) => void;
  onFileChange: (file: File | null) => void;
  onAnalyzeImport: () => void;
  onImportMappingChange: (field: string, value: string | null) => void;
  onSubmitImport: FormEventHandler<HTMLFormElement>;
  onUpdateProgramSetting: FormEventHandler<HTMLFormElement>;
  onProgramSettingFormChange: (field: keyof ProgramSettingFormState, value: string | number | boolean | string[]) => void;
  onUpdateProgramDataPolicy: FormEventHandler<HTMLFormElement>;
  onProgramDataPolicyFormChange: (field: keyof ProgramDataPolicyFormState, value: string | boolean) => void;
  onCreateConnector: FormEventHandler<HTMLFormElement>;
  onConnectorFormChange: (field: keyof ConnectorFormState, value: string | boolean) => void;
  onPreviewConnector: () => void;
  onConnectorMappingChange: (field: string, value: string | null) => void;
  onTestConnector: (connectorId: string, connectorName: string) => void;
  onSyncConnector: (connectorId: string, connectorName: string) => void;
  onUpdateModelSchedule: FormEventHandler<HTMLFormElement>;
  onModelScheduleFormChange: (field: "cadence" | "enabled" | "auto_retrain_after_sync", value: string | boolean) => void;
  onRunDueAutomation: () => void;
  onRunPendingJobs: () => void;
  onRequeueJob: (jobId: string) => void;
  formatTimestamp: (value: string) => string;
  formatMappingField: (field: string) => string;
  formatPaginationMode: (value: string) => string;
  formatJobType: (jobType: JobRecord["job_type"]) => string;
  formatJobStatus: (status: JobRecord["status"]) => string;
  jobStatusTone: (status: JobRecord["status"]) => "risk-high" | "risk-medium" | "risk-low";
}

const SUPPORT_CHANNEL_OPTIONS: Array<{ value: ProgramSettingFormState["low_risk_channel"]; label: string }> = [
  { value: "sms", label: "SMS" },
  { value: "call", label: "Call" },
  { value: "visit", label: "Visit" },
  { value: "whatsapp", label: "WhatsApp" },
  { value: "manual", label: "Manual task" },
];

function OperationsSection({
  allowProgramAdmin,
  allowModelTraining,
  showAuditLogs,
  isSubmitting,
  isAnalyzingImport,
  isPreviewingConnector,
  activeConnectorId,
  programs,
  imports,
  auditLogs,
  connectors,
  connectorSyncRuns,
  recentJobs,
  modelSchedule,
  programForm,
  datasetType,
  selectedProgramId,
  selectedFileName,
  importAnalysis,
  importMappingDraft,
  connectorPreview,
  connectorMappingDraft,
  connectorForm,
  modelScheduleForm,
  programSettingForm,
  programDataPolicyForm,
  selectedProgramSettingUpdatedAt,
  selectedProgramDataPolicy,
  datasetMappingFields,
  connectorTypeOptions,
  authSchemeOptions,
  cadenceOptions,
  syncIntervalOptions,
  onCreateProgram,
  onProgramFormChange,
  onDatasetTypeChange,
  onSelectedProgramIdChange,
  onFileChange,
  onAnalyzeImport,
  onImportMappingChange,
  onSubmitImport,
  onUpdateProgramSetting,
  onProgramSettingFormChange,
  onUpdateProgramDataPolicy,
  onProgramDataPolicyFormChange,
  onCreateConnector,
  onConnectorFormChange,
  onPreviewConnector,
  onConnectorMappingChange,
  onTestConnector,
  onSyncConnector,
  onUpdateModelSchedule,
  onModelScheduleFormChange,
  onRunDueAutomation,
  onRunPendingJobs,
  onRequeueJob,
  formatTimestamp,
  formatMappingField,
  formatPaginationMode,
  formatJobType,
  formatJobStatus,
  jobStatusTone,
}: OperationsSectionProps) {
  return (
    <>
      <section className="ops-grid">
        <article className="panel">
          <div className="section-heading">
            <div>
              <span className="eyebrow">Program operations</span>
              <h2>Create a program workspace</h2>
            </div>
          </div>
          {allowProgramAdmin ? (
            <>
              <form className="stacked-form" onSubmit={onCreateProgram}>
                <input type="text" placeholder="Program name" value={programForm.name} onChange={(event) => onProgramFormChange("name", event.target.value)} required />
                <select value={programForm.program_type} onChange={(event) => onProgramFormChange("program_type", event.target.value)}>
                  <option value="Cash Transfer">Cash Transfer</option>
                  <option value="Education">Education</option>
                  <option value="Health">Health</option>
                </select>
                <input type="text" placeholder="Country" value={programForm.country} onChange={(event) => onProgramFormChange("country", event.target.value)} required />
                <input type="text" placeholder="Delivery modality" value={programForm.delivery_modality ?? ""} onChange={(event) => onProgramFormChange("delivery_modality", event.target.value)} />
                <button className="primary-button" type="submit" disabled={isSubmitting}>
                  {isSubmitting ? "Saving..." : "Create program"}
                </button>
              </form>

              <div className="divider" />

              <div className="section-heading compact-heading">
                <div>
                  <span className="eyebrow">Staff capacity and fairness</span>
                  <h2>Operational queue settings</h2>
                </div>
              </div>
              <form className="stacked-form" onSubmit={onUpdateProgramSetting}>
                <select value={selectedProgramId} onChange={(event) => onSelectedProgramIdChange(event.target.value)} required>
                  <option value="">Select a program</option>
                  {programs.map((program) => (
                    <option value={program.id} key={program.id}>
                      {program.name}
                    </option>
                  ))}
                </select>
                <input type="number" min={1} value={programSettingForm.weekly_followup_capacity} onChange={(event) => onProgramSettingFormChange("weekly_followup_capacity", Number(event.target.value))} />
                <input type="number" min={1} value={programSettingForm.worker_count} onChange={(event) => onProgramSettingFormChange("worker_count", Number(event.target.value))} />
                <input type="number" step="0.1" min={1} value={programSettingForm.medium_risk_multiplier} onChange={(event) => onProgramSettingFormChange("medium_risk_multiplier", Number(event.target.value))} />
                <input type="number" step="0.01" min={0.01} max={0.8} value={programSettingForm.high_risk_share_floor} onChange={(event) => onProgramSettingFormChange("high_risk_share_floor", Number(event.target.value))} />
                <input type="number" min={7} value={programSettingForm.review_window_days} onChange={(event) => onProgramSettingFormChange("review_window_days", Number(event.target.value))} />
                <select value={programSettingForm.label_definition_preset} onChange={(event) => onProgramSettingFormChange("label_definition_preset", event.target.value)}>
                  <option value="custom">Custom label definition</option>
                  <option value="health_28d">Health: 28-day no-contact</option>
                  <option value="education_10d">Education: 10-day absence</option>
                  <option value="cct_missed_cycle">Cash transfer: missed cycle</option>
                </select>
                <input type="number" min={7} value={programSettingForm.dropout_inactivity_days} onChange={(event) => onProgramSettingFormChange("dropout_inactivity_days", Number(event.target.value))} />
                <input type="number" min={7} max={90} value={programSettingForm.prediction_window_days} onChange={(event) => onProgramSettingFormChange("prediction_window_days", Number(event.target.value))} />
                <select value={programSettingForm.label_noise_strategy} onChange={(event) => onProgramSettingFormChange("label_noise_strategy", event.target.value)}>
                  <option value="operational_soft_labels">Operational soft labels</option>
                  <option value="strict">Strict hard labels only</option>
                </select>
                <input type="number" min={0.05} max={1} step={0.05} value={programSettingForm.soft_label_weight} onChange={(event) => onProgramSettingFormChange("soft_label_weight", Number(event.target.value))} />
                <label className="stacked-check">
                  <span>Exclude suspected silent transfers from training labels</span>
                  <input
                    type="checkbox"
                    checked={programSettingForm.silent_transfer_detection_enabled}
                    onChange={(event) => onProgramSettingFormChange("silent_transfer_detection_enabled", event.target.checked)}
                  />
                </label>
                <div className="inline-grid">
                  <label className="stacked-check">
                    <span>Low-risk default channel</span>
                    <select value={programSettingForm.low_risk_channel} onChange={(event) => onProgramSettingFormChange("low_risk_channel", event.target.value)}>
                      {SUPPORT_CHANNEL_OPTIONS.map((option) => (
                        <option value={option.value} key={`low-${option.value}`}>
                          {option.label}
                        </option>
                      ))}
                    </select>
                  </label>
                  <label className="stacked-check">
                    <span>Medium-risk default channel</span>
                    <select value={programSettingForm.medium_risk_channel} onChange={(event) => onProgramSettingFormChange("medium_risk_channel", event.target.value)}>
                      {SUPPORT_CHANNEL_OPTIONS.map((option) => (
                        <option value={option.value} key={`medium-${option.value}`}>
                          {option.label}
                        </option>
                      ))}
                    </select>
                  </label>
                </div>
                <div className="inline-grid">
                  <label className="stacked-check">
                    <span>High-risk default channel</span>
                    <select value={programSettingForm.high_risk_channel} onChange={(event) => onProgramSettingFormChange("high_risk_channel", event.target.value)}>
                      {SUPPORT_CHANNEL_OPTIONS.map((option) => (
                        <option value={option.value} key={`high-${option.value}`}>
                          {option.label}
                        </option>
                      ))}
                    </select>
                  </label>
                  <label className="stacked-check">
                    <span>Escalate after inactivity (days)</span>
                    <input type="number" min={1} max={60} value={programSettingForm.escalation_window_days} onChange={(event) => onProgramSettingFormChange("escalation_window_days", Number(event.target.value))} />
                  </label>
                </div>
                <div className="inline-grid">
                  <label className="stacked-check">
                    <span>SMS step delay (days)</span>
                    <input type="number" min={0} max={30} value={programSettingForm.tracing_sms_delay_days} onChange={(event) => onProgramSettingFormChange("tracing_sms_delay_days", Number(event.target.value))} />
                  </label>
                  <label className="stacked-check">
                    <span>Call step delay (days)</span>
                    <input type="number" min={1} max={45} value={programSettingForm.tracing_call_delay_days} onChange={(event) => onProgramSettingFormChange("tracing_call_delay_days", Number(event.target.value))} />
                  </label>
                </div>
                <label className="stacked-check">
                  <span>Visit step delay (days)</span>
                  <input type="number" min={1} max={90} value={programSettingForm.tracing_visit_delay_days} onChange={(event) => onProgramSettingFormChange("tracing_visit_delay_days", Number(event.target.value))} />
                </label>
                <label className="stacked-check">
                  <span>Escalate after attempts</span>
                  <input type="number" min={1} max={10} value={programSettingForm.escalation_max_attempts} onChange={(event) => onProgramSettingFormChange("escalation_max_attempts", Number(event.target.value))} />
                </label>
                <span className="helper-copy compact-copy">
                  These rules drive embedded write-back queues for CommCare, DHIS2, and webhook dispatch targets.
                </span>
                <label className="checkbox-row">
                  <input type="checkbox" checked={programSettingForm.fairness_reweighting_enabled} onChange={(event) => onProgramSettingFormChange("fairness_reweighting_enabled", event.target.checked)} />
                  <span>Enable fairness-aware reweighting</span>
                </label>
                <label className="stacked-check">
                  <span>Fairness target dimensions</span>
                  <input
                    type="text"
                    value={programSettingForm.fairness_target_dimensions.join(", ")}
                    onChange={(event) =>
                      onProgramSettingFormChange(
                        "fairness_target_dimensions",
                        event.target.value.split(",").map((item) => item.trim()).filter(Boolean),
                      )
                    }
                  />
                </label>
                <input type="number" step="0.01" min={0.01} max={0.5} value={programSettingForm.fairness_max_gap} onChange={(event) => onProgramSettingFormChange("fairness_max_gap", Number(event.target.value))} />
                <input type="number" min={5} value={programSettingForm.fairness_min_group_size} onChange={(event) => onProgramSettingFormChange("fairness_min_group_size", Number(event.target.value))} />
                <button className="primary-button" type="submit" disabled={isSubmitting}>
                  {isSubmitting ? "Saving..." : "Save queue settings"}
                </button>
                {selectedProgramSettingUpdatedAt ? (
                  <span className="helper-copy compact-copy">
                    Last updated {formatTimestamp(selectedProgramSettingUpdatedAt)}. Queue size, worker distribution, and label rules all flow from this program profile.
                  </span>
                ) : null}
              </form>

              <div className="divider" />

              <div className="section-heading compact-heading">
                <div>
                  <span className="eyebrow">Privacy and residency</span>
                  <h2>Program data policy</h2>
                </div>
              </div>
              <form className="stacked-form" onSubmit={onUpdateProgramDataPolicy}>
                <select value={programDataPolicyForm.storage_mode} onChange={(event) => onProgramDataPolicyFormChange("storage_mode", event.target.value)}>
                  <option value="self_hosted">Self-hosted</option>
                  <option value="managed_region">Managed region</option>
                </select>
                <input type="text" placeholder="Residency region" value={programDataPolicyForm.data_residency_region} onChange={(event) => onProgramDataPolicyFormChange("data_residency_region", event.target.value)} />
                <label className="checkbox-row">
                  <input type="checkbox" checked={programDataPolicyForm.cross_border_transfers_allowed} onChange={(event) => onProgramDataPolicyFormChange("cross_border_transfers_allowed", event.target.checked)} />
                  <span>Allow cross-border transfers</span>
                </label>
                <label className="checkbox-row">
                  <input type="checkbox" checked={programDataPolicyForm.pii_tokenization_enabled} onChange={(event) => onProgramDataPolicyFormChange("pii_tokenization_enabled", event.target.checked)} />
                  <span>Enable PII tokenization</span>
                </label>
                <label className="checkbox-row">
                  <input type="checkbox" checked={programDataPolicyForm.consent_required} onChange={(event) => onProgramDataPolicyFormChange("consent_required", event.target.checked)} />
                  <span>Require explicit modeling consent</span>
                </label>
                <label className="checkbox-row">
                  <input type="checkbox" checked={programDataPolicyForm.federated_learning_enabled} onChange={(event) => onProgramDataPolicyFormChange("federated_learning_enabled", event.target.checked)} />
                  <span>Allow federated learning participation</span>
                </label>
                <button className="primary-button" type="submit" disabled={isSubmitting}>
                  {isSubmitting ? "Saving..." : "Save data policy"}
                </button>
                {selectedProgramDataPolicy ? (
                  <span className="helper-copy compact-copy">
                    Residency {selectedProgramDataPolicy.data_residency_region}. Tokenization {selectedProgramDataPolicy.pii_tokenization_enabled ? "on" : "off"}.
                  </span>
                ) : null}
              </form>

              <div className="divider" />

              <div className="section-heading compact-heading">
                <div>
                  <span className="eyebrow">Manual ingestion</span>
                  <h2>Analyze then import NGO data files</h2>
                </div>
              </div>
              <form className="stacked-form" onSubmit={onSubmitImport}>
                <select value={datasetType} onChange={(event) => onDatasetTypeChange(event.target.value as DatasetType)}>
                  <option value="beneficiaries">Beneficiaries</option>
                  <option value="events">Monitoring events</option>
                </select>
                <select value={selectedProgramId} onChange={(event) => onSelectedProgramIdChange(event.target.value)} required>
                  <option value="">Select a program</option>
                  {programs.map((program) => (
                    <option value={program.id} key={program.id}>
                      {program.name}
                    </option>
                  ))}
                </select>
                <label className="file-input">
                  <span>{selectedFileName ?? "Choose a CSV or Excel file"}</span>
                  <input type="file" accept=".csv,.xlsx,text/csv,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" onChange={(event) => onFileChange(event.target.files?.[0] ?? null)} />
                </label>
                <div className="connector-actions">
                  <button className="secondary-button" type="button" onClick={onAnalyzeImport} disabled={!selectedFileName || isAnalyzingImport}>
                    {isAnalyzingImport ? "Analyzing..." : "Analyze file"}
                  </button>
                  <span className="helper-copy compact-copy">
                    RetainAI will infer types, suggest mappings, flag duplicates, and show anomalies before import.
                  </span>
                </div>
                {importAnalysis ? (
                  <div className="analysis-card">
                    <div className="flag-row">
                      <span className="badge badge-outline">{importAnalysis.records_received} rows</span>
                      <span className="badge badge-outline">Quality {importAnalysis.quality_score}/100</span>
                      <span className="badge badge-outline">{importAnalysis.source_format.toUpperCase()}</span>
                    </div>
                    <div className="mapping-grid">
                      {datasetMappingFields[datasetType].map((field) => (
                        <label className="mapping-row" key={field}>
                          <span>{formatMappingField(field)}</span>
                          <select value={importMappingDraft[field] ?? ""} onChange={(event) => onImportMappingChange(field, event.target.value || null)}>
                            <option value="">Not mapped</option>
                            {importAnalysis.available_columns.map((column) => (
                              <option value={column} key={`${field}-${column}`}>
                                {column}
                              </option>
                            ))}
                          </select>
                        </label>
                      ))}
                    </div>
                    {importAnalysis.warnings.length > 0 ? (
                      <div className="warning-list">
                        {importAnalysis.warnings.map((warning) => (
                          <span className="flag-chip" key={warning}>
                            {warning}
                          </span>
                        ))}
                      </div>
                    ) : null}
                    {importAnalysis.issues.length > 0 ? (
                      <div className="issue-list">
                        {importAnalysis.issues.slice(0, 6).map((issue) => (
                          <div className="issue-row" key={`${issue.issue_type}-${issue.row_number ?? issue.field_name ?? issue.message}`}>
                            <strong>{issue.severity}</strong>
                            <span>{issue.message}</span>
                          </div>
                        ))}
                      </div>
                    ) : null}
                  </div>
                ) : null}
                <button className="primary-button" type="submit" disabled={isSubmitting}>
                  {isSubmitting ? "Importing..." : "Run import"}
                </button>
              </form>
            </>
          ) : (
            <div className="ops-note readonly-note">
              <span className="eyebrow">Configuration access</span>
              <p>
                Your role can review retention operations, but program creation, imports, and model retraining are limited to admins and M&amp;E officers.
              </p>
            </div>
          )}

          <p className="helper-copy">
            Beneficiary imports auto-detect columns like `external_id`, `name`, `region`, and `enrollment_date`. Event imports expect `external_id`, `event_date`, and `event_type`, and can also map attendance or response fields automatically.
          </p>
          <p className="helper-copy">
            After loading new historical data, retrain the model so risk scoring reflects the latest program context rather than the previous deployment snapshot.
          </p>
        </article>
        <article className="panel">
          <div className="section-heading">
            <div>
              <span className="eyebrow">Automation</span>
              <h2>Queue, cadence, and sync history</h2>
            </div>
          </div>
          <form className="stacked-form" onSubmit={onUpdateModelSchedule}>
            <select value={modelScheduleForm.cadence} onChange={(event) => onModelScheduleFormChange("cadence", event.target.value)} disabled={!allowProgramAdmin}>
              {cadenceOptions.map((option) => (
                <option value={option.value} key={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
            <label className="checkbox-row">
              <input
                type="checkbox"
                checked={modelScheduleForm.enabled}
                onChange={(event) => onModelScheduleFormChange("enabled", event.target.checked)}
                disabled={!allowProgramAdmin || modelScheduleForm.cadence === "manual"}
              />
              <span>Enable cadence-based retraining</span>
            </label>
            <label className="checkbox-row">
              <input
                type="checkbox"
                checked={modelScheduleForm.auto_retrain_after_sync}
                onChange={(event) => onModelScheduleFormChange("auto_retrain_after_sync", event.target.checked)}
                disabled={!allowProgramAdmin}
              />
              <span>Retrain automatically after connector syncs</span>
            </label>
            <div className="meta-stack">
              <span>Last run: {modelSchedule.last_run_at ? formatTimestamp(modelSchedule.last_run_at) : "Not yet run"}</span>
              <span>Next run: {modelSchedule.next_run_at ? formatTimestamp(modelSchedule.next_run_at) : "Manual"}</span>
            </div>
            {allowProgramAdmin ? (
              <div className="connector-actions">
                <button className="primary-button" type="submit" disabled={isSubmitting}>
                  {isSubmitting ? "Saving..." : "Save schedule"}
                </button>
                <button className="secondary-button" type="button" onClick={onRunDueAutomation} disabled={isSubmitting}>
                  {isSubmitting ? "Working..." : "Run due jobs"}
                </button>
                <button className="secondary-button" type="button" onClick={onRunPendingJobs} disabled={isSubmitting}>
                  {isSubmitting ? "Working..." : "Run queue now"}
                </button>
              </div>
            ) : null}
          </form>

          <div className="divider" />

          <div className="section-heading compact-heading">
            <div>
              <span className="eyebrow">Background queue</span>
              <h2>Recent jobs</h2>
            </div>
          </div>
          <div className="intervention-list">
            {recentJobs.length === 0 ? (
              <div className="empty-state">No queued jobs yet.</div>
            ) : (
              recentJobs.map((job) => (
                <div className="intervention-card" key={job.id}>
                  <div>
                    <strong>{formatJobType(job.job_type)}</strong>
                    <span>{job.created_by_email ?? "system"}</span>
                  </div>
                  <p>
                    <span className={`risk-pill ${jobStatusTone(job.status)}`}>{formatJobStatus(job.status)}</span>
                    {" | "}
                    queued {formatTimestamp(job.created_at)}
                  </p>
                  <span>
                    Attempts {job.attempts}/{job.max_attempts}
                    {job.status === "queued" && job.attempts > 0 ? ` | retry after ${job.retry_backoff_seconds}s` : ""}
                    {job.dead_lettered_at ? ` | dead-lettered ${formatTimestamp(job.dead_lettered_at)}` : ""}
                    {job.completed_at ? ` | finished ${formatTimestamp(job.completed_at)}` : ""}
                  </span>
                  {job.error_message ? <p className="inline-helper">{job.error_message}</p> : null}
                  {job.result ? (
                    <div className="warning-list">
                      {Object.entries(job.result)
                        .slice(0, 3)
                        .map(([key, value]) => (
                          <span className="flag-chip" key={`${job.id}-${key}`}>
                            {key.replace(/_/g, " ")}: {String(value)}
                          </span>
                        ))}
                    </div>
                  ) : null}
                  {(job.status === "failed" || job.status === "dead_letter") && allowModelTraining ? (
                    <div className="connector-actions">
                      <button className="secondary-button" type="button" onClick={() => onRequeueJob(job.id)} disabled={isSubmitting}>
                        {isSubmitting ? "Working..." : "Re-queue job"}
                      </button>
                    </div>
                  ) : null}
                </div>
              ))
            )}
          </div>

          <div className="divider" />

          <div className="section-heading compact-heading">
            <div>
              <span className="eyebrow">Connector runs</span>
              <h2>Completed sync history</h2>
            </div>
          </div>
          <div className="intervention-list">
            {connectorSyncRuns.length === 0 ? (
              <div className="empty-state">No connector syncs have run yet.</div>
            ) : (
              connectorSyncRuns.map((run) => (
                <div className="intervention-card" key={run.id}>
                  <div>
                    <strong>{run.connector_name}</strong>
                    <span>{run.status}</span>
                  </div>
                  <p>
                    {run.program_name} | {run.records_processed} processed | {run.records_failed} failed
                  </p>
                  <span>
                    {run.trigger_mode}
                    {run.model_retrained ? " | model retrained" : ""}
                  </span>
                  <time>{formatTimestamp(run.started_at)}</time>
                  {run.warnings.length > 0 ? (
                    <div className="warning-list">
                      {run.warnings.map((warning) => (
                        <span className="flag-chip" key={warning}>
                          {warning}
                        </span>
                      ))}
                    </div>
                  ) : null}
                </div>
              ))
            )}
          </div>
        </article>
      </section>
    </>
  );
}

export default OperationsSection;
