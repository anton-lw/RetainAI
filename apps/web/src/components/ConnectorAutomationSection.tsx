/**
 * Connector and automation administration surface.
 *
 * This is where operators manage external data-system integrations, run tests
 * or syncs, inspect dispatch history, and configure the write-back / embedded
 * operations side of the platform.
 */

import type { FormEventHandler } from "react";

import type {
  AuthScheme,
  ConnectorDispatchRun,
  ConnectorProbeResult,
  ConnectorType,
  DataConnector,
  DataConnectorSyncRun,
  DatasetType,
  JobRecord,
  ModelCadence,
  ModelSchedule,
  Program,
} from "../types";

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

interface ConnectorAutomationSectionProps {
  allowProgramAdmin: boolean;
  allowModelTraining: boolean;
  isSubmitting: boolean;
  isPreviewingConnector: boolean;
  activeConnectorId: string | null;
  programs: Program[];
  connectors: DataConnector[];
  connectorSyncRuns: DataConnectorSyncRun[];
  connectorDispatchRuns: ConnectorDispatchRun[];
  connectorPreview: ConnectorProbeResult | null;
  connectorMappingDraft: Record<string, string | null>;
  connectorForm: ConnectorFormState;
  modelSchedule: ModelSchedule;
  modelScheduleForm: {
    cadence: ModelCadence;
    enabled: boolean;
    auto_retrain_after_sync: boolean;
  };
  recentJobs: JobRecord[];
  datasetMappingFields: Record<DatasetType, string[]>;
  connectorTypeOptions: Array<{ value: ConnectorType; label: string }>;
  authSchemeOptions: Array<{ value: AuthScheme; label: string }>;
  cadenceOptions: Array<{ value: ModelCadence; label: string }>;
  syncIntervalOptions: Array<{ value: string; label: string }>;
  onCreateConnector: FormEventHandler<HTMLFormElement>;
  onConnectorFormChange: (field: keyof ConnectorFormState, value: string | boolean) => void;
  onPreviewConnector: () => void;
  onConnectorMappingChange: (field: string, value: string | null) => void;
  onTestConnector: (connectorId: string, connectorName: string) => void;
  onSyncConnector: (connectorId: string, connectorName: string) => void;
  onDispatchConnector: (connectorId: string, connectorName: string, previewOnly: boolean) => void;
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

function ConnectorAutomationSection({
  allowProgramAdmin,
  allowModelTraining,
  isSubmitting,
  isPreviewingConnector,
  activeConnectorId,
  programs,
  connectors,
  connectorSyncRuns,
  connectorDispatchRuns,
  connectorPreview,
  connectorMappingDraft,
  connectorForm,
  modelSchedule,
  modelScheduleForm,
  recentJobs,
  datasetMappingFields,
  connectorTypeOptions,
  authSchemeOptions,
  cadenceOptions,
  syncIntervalOptions,
  onCreateConnector,
  onConnectorFormChange,
  onPreviewConnector,
  onConnectorMappingChange,
  onTestConnector,
  onSyncConnector,
  onDispatchConnector,
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
}: ConnectorAutomationSectionProps) {
  return (
    <section className="two-column-grid">
      <article className="panel">
        <div className="section-heading">
          <div>
            <span className="eyebrow">Source connectors</span>
            <h2>Automated data pipelines</h2>
          </div>
        </div>

        {allowProgramAdmin ? (
          <>
            <form className="stacked-form" onSubmit={onCreateConnector}>
              <select value={connectorForm.program_id} onChange={(event) => onConnectorFormChange("program_id", event.target.value)} required>
                <option value="">Select a program</option>
                {programs.map((program) => (
                  <option value={program.id} key={program.id}>
                    {program.name}
                  </option>
                ))}
              </select>
              <input type="text" placeholder="Connector name" value={connectorForm.name} onChange={(event) => onConnectorFormChange("name", event.target.value)} required />
              <div className="inline-grid">
                <select value={connectorForm.connector_type} onChange={(event) => onConnectorFormChange("connector_type", event.target.value)}>
                  {connectorTypeOptions.map((option) => (
                    <option value={option.value} key={option.value}>
                      {option.label}
                    </option>
                  ))}
                </select>
                <select value={connectorForm.dataset_type} onChange={(event) => onConnectorFormChange("dataset_type", event.target.value)}>
                  <option value="beneficiaries">Beneficiary records</option>
                  <option value="events">Monitoring events</option>
                </select>
              </div>
              <input type="url" placeholder="Base URL" value={connectorForm.base_url} onChange={(event) => onConnectorFormChange("base_url", event.target.value)} required />
              <input type="text" placeholder="Resource path" value={connectorForm.resource_path} onChange={(event) => onConnectorFormChange("resource_path", event.target.value)} required />
              <div className="inline-grid">
                <select value={connectorForm.auth_scheme} onChange={(event) => onConnectorFormChange("auth_scheme", event.target.value)}>
                  {authSchemeOptions.map((option) => (
                    <option value={option.value} key={option.value}>
                      {option.label}
                    </option>
                  ))}
                </select>
                <input type="text" placeholder="Auth username" value={connectorForm.auth_username} onChange={(event) => onConnectorFormChange("auth_username", event.target.value)} />
              </div>
              <input type="password" placeholder="Secret or token" value={connectorForm.secret} onChange={(event) => onConnectorFormChange("secret", event.target.value)} />
              <input type="text" placeholder="JSON record path (optional)" value={connectorForm.record_path} onChange={(event) => onConnectorFormChange("record_path", event.target.value)} />
              <label className="checkbox-row">
                <input type="checkbox" checked={connectorForm.webhook_enabled} onChange={(event) => onConnectorFormChange("webhook_enabled", event.target.checked)} />
                <span>Enable webhook-triggered sync</span>
              </label>
              {connectorForm.webhook_enabled ? (
                <input type="password" placeholder="Webhook shared secret" value={connectorForm.webhook_secret} onChange={(event) => onConnectorFormChange("webhook_secret", event.target.value)} />
              ) : null}
              <label className="stacked-check">
                <span>Query params JSON</span>
                <textarea rows={3} value={connectorForm.query_params_text} onChange={(event) => onConnectorFormChange("query_params_text", event.target.value)} />
              </label>
              <div className="analysis-card">
                <div className="section-heading compact-heading">
                  <div>
                    <span className="eyebrow">Field mapping</span>
                    <h2>Preview then map connector columns</h2>
                  </div>
                </div>
                <div className="connector-actions">
                  <button className="secondary-button" type="button" onClick={onPreviewConnector} disabled={isPreviewingConnector || isSubmitting}>
                    {isPreviewingConnector ? "Previewing..." : "Preview connector"}
                  </button>
                  <span className="helper-copy compact-copy">
                    Preview fetches sample records, infers mappings, and fills the guided mapping grid below.
                  </span>
                </div>
                <div className="mapping-grid">
                  {datasetMappingFields[connectorForm.dataset_type].map((field) => (
                    <label className="mapping-row" key={`connector-${field}`}>
                      <span>{formatMappingField(field)}</span>
                      <select value={connectorMappingDraft[field] ?? ""} onChange={(event) => onConnectorMappingChange(field, event.target.value || null)}>
                        <option value="">Not mapped</option>
                        {(connectorPreview?.sample_headers ?? []).map((column) => (
                          <option value={column} key={`${field}-${column}`}>
                            {column}
                          </option>
                        ))}
                      </select>
                    </label>
                  ))}
                </div>
                {connectorPreview ? (
                  <div className="issue-list">
                    <div className="issue-row">
                      <strong>Preview</strong>
                      <span>
                        {connectorPreview.record_count} records across {connectorPreview.pages_fetched} page(s)
                      </span>
                    </div>
                    {connectorPreview.warnings.map((warning) => (
                      <div className="issue-row" key={warning}>
                        <strong>Warning</strong>
                        <span>{warning}</span>
                      </div>
                    ))}
                  </div>
                ) : null}
              </div>
              <label className="checkbox-row">
                <input type="checkbox" checked={connectorForm.schedule_enabled} onChange={(event) => onConnectorFormChange("schedule_enabled", event.target.checked)} />
                <span>Enable scheduled sync</span>
              </label>
              <select value={connectorForm.sync_interval_hours} onChange={(event) => onConnectorFormChange("sync_interval_hours", event.target.value)} disabled={!connectorForm.schedule_enabled}>
                {syncIntervalOptions.map((option) => (
                  <option value={option.value} key={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
              <label className="checkbox-row">
                <input type="checkbox" checked={connectorForm.writeback_enabled} onChange={(event) => onConnectorFormChange("writeback_enabled", event.target.checked)} />
                <span>Enable workflow write-back</span>
              </label>
              {connectorForm.writeback_enabled ? (
                <>
                  <select value={connectorForm.writeback_mode} onChange={(event) => onConnectorFormChange("writeback_mode", event.target.value)}>
                    <option value="commcare_case_updates">CommCare case updates</option>
                    <option value="dhis2_working_list">DHIS2 working list</option>
                    <option value="generic_webhook">Generic webhook</option>
                    <option value="none">Disabled</option>
                  </select>
                  <input type="text" placeholder="Write-back resource path (optional)" value={connectorForm.writeback_resource_path} onChange={(event) => onConnectorFormChange("writeback_resource_path", event.target.value)} />
                  <label className="stacked-check">
                    <span>Write-back mapping JSON</span>
                    <textarea rows={3} value={connectorForm.writeback_field_mapping_text} onChange={(event) => onConnectorFormChange("writeback_field_mapping_text", event.target.value)} />
                  </label>
                </>
              ) : null}
              <button className="primary-button" type="submit" disabled={isSubmitting || Object.keys(connectorMappingDraft).length === 0}>
                {isSubmitting ? "Saving..." : "Create connector"}
              </button>
            </form>
            <p className="helper-copy">
              Connector syncs reuse the same beneficiary and event ingestion pipeline as CSV imports, with idempotent event updates for repeat pulls.
            </p>
          </>
        ) : (
          <div className="ops-note readonly-note">
            <span className="eyebrow">Connector management</span>
            <p>Your role can monitor connector health and sync outcomes, but connector setup is limited to admins and M&amp;E officers.</p>
          </div>
        )}

        <div className="connector-list">
          {connectors.length === 0 ? (
            <div className="empty-state">No source connectors configured yet.</div>
          ) : (
            connectors.map((connector) => (
              <div className="connector-card" key={connector.id}>
                <div className="connector-header">
                  <div>
                    <strong>{connector.name}</strong>
                    <p>
                      {connector.connector_label} | {connector.program_name} | {connector.dataset_type}
                    </p>
                  </div>
                  <span className={`risk-pill risk-${connector.status === "error" ? "high" : "low"}`}>{connector.status}</span>
                </div>
                <p className="mini-metric">
                  {connector.base_url}/{connector.resource_path}
                </p>
                <div className="meta-stack">
                  <span>Last sync: {connector.last_synced_at ? formatTimestamp(connector.last_synced_at) : "Never"}</span>
                  <span>Next due: {connector.next_sync_at ? formatTimestamp(connector.next_sync_at) : "Manual"}</span>
                  <span>
                    Adapter: {formatPaginationMode(connector.pagination_mode)}
                    {connector.supports_incremental_sync ? " | incremental-ready" : ""}
                  </span>
                  <span>
                    Write-back: {connector.writeback_enabled ? connector.writeback_mode.replace(/_/g, " ") : "disabled"}
                    {connector.last_dispatched_at ? ` | last dispatch ${formatTimestamp(connector.last_dispatched_at)}` : ""}
                  </span>
                  {connector.writeback_resource_path ? <span>Dispatch path: {connector.writeback_resource_path}</span> : null}
                  <span>Record path: {connector.effective_record_path ?? "top-level response"}</span>
                  <span>
                    Auth: {connector.auth_scheme}
                    {connector.masked_secret ? ` | ${connector.masked_secret}` : ""}
                  </span>
                  <span>
                    Webhook: {connector.webhook_enabled ? "enabled" : "disabled"}
                    {connector.webhook_enabled && connector.webhook_endpoint ? ` | ${connector.webhook_endpoint}` : ""}
                  </span>
                  {connector.last_webhook_at ? <span>Last webhook: {formatTimestamp(connector.last_webhook_at)}</span> : null}
                  {Object.keys(connector.sync_state ?? {}).length > 0 ? <span>Sync state: {JSON.stringify(connector.sync_state)}</span> : null}
                </div>
                {connector.last_error ? <p className="inline-helper">{connector.last_error}</p> : null}
                {allowProgramAdmin ? (
                  <div className="connector-actions">
                    <button className="secondary-button" type="button" onClick={() => onTestConnector(connector.id, connector.name)} disabled={activeConnectorId === connector.id}>
                      {activeConnectorId === connector.id ? "Working..." : "Test"}
                    </button>
                    <button className="primary-button" type="button" onClick={() => onSyncConnector(connector.id, connector.name)} disabled={activeConnectorId === connector.id}>
                      {activeConnectorId === connector.id ? "Working..." : "Sync now"}
                    </button>
                    {connector.writeback_enabled ? (
                      <>
                        <button className="secondary-button" type="button" onClick={() => onDispatchConnector(connector.id, connector.name, true)} disabled={activeConnectorId === connector.id}>
                          {activeConnectorId === connector.id ? "Working..." : "Preview dispatch"}
                        </button>
                        <button className="primary-button" type="button" onClick={() => onDispatchConnector(connector.id, connector.name, false)} disabled={activeConnectorId === connector.id}>
                          {activeConnectorId === connector.id ? "Working..." : "Dispatch queue"}
                        </button>
                      </>
                    ) : null}
                  </div>
                ) : null}
              </div>
            ))
          )}
        </div>
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
                  {" | "}queued {formatTimestamp(job.created_at)}
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

        <div className="divider" />

        <div className="section-heading compact-heading">
          <div>
            <span className="eyebrow">Embedded operations</span>
            <h2>Dispatch history</h2>
          </div>
        </div>

        <div className="intervention-list">
          {connectorDispatchRuns.length === 0 ? (
            <div className="empty-state">No dispatch runs yet.</div>
          ) : (
            connectorDispatchRuns.map((run) => (
              <div className="intervention-card" key={run.id}>
                <div>
                  <strong>{run.connector_name}</strong>
                  <span>{run.target_mode.replace(/_/g, " ")}</span>
                </div>
                <p>
                  {run.status} | {run.records_sent} sent | {run.cases_included} included | {run.cases_skipped} skipped
                </p>
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
  );
}

export default ConnectorAutomationSection;
