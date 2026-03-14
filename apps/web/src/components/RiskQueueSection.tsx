/**
 * Day-to-day tracing queue for supportive retention follow-up.
 *
 * This is one of the most operationally important UI surfaces in RetainAI. It
 * combines:
 *
 * - prioritised at-risk case lists
 * - filtering by geography, program, cohort, phase, and risk level
 * - the action / verification / dismissal workflow introduced in the retention
 *   operations phases
 * - follow-up export shortcuts for external channels
 *
 * If the product's core loop is "flag -> action -> verification -> outcome",
 * this component is the frontend anchor of that loop.
 */

import type { FormEventHandler } from "react";

import type { InterventionRecord, RiskCase, RiskLevel, SoftSignalSnapshot } from "../types";

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

interface RiskQueueSectionProps {
  allowExports: boolean;
  allowInterventionLogging: boolean;
  isSubmitting: boolean;
  filteredCases: RiskCase[];
  interventions: InterventionRecord[];
  selectedWorkflowCase: RiskCase | null;
  workflowForm: WorkflowFormState;
  search: string;
  riskFilter: "All" | RiskLevel;
  programFilter: string;
  regionFilter: string;
  cohortFilter: string;
  phaseFilter: string;
  programs: string[];
  regions: string[];
  cohorts: string[];
  phases: string[];
  onSearchChange: (value: string) => void;
  onRiskFilterChange: (value: "All" | RiskLevel) => void;
  onProgramFilterChange: (value: string) => void;
  onRegionFilterChange: (value: string) => void;
  onCohortFilterChange: (value: string) => void;
  onPhaseFilterChange: (value: string) => void;
  onExport: (dataset: "risk_cases" | "interventions") => void;
  onFollowUpExport: (mode: "whatsapp" | "sms" | "field_visit") => void;
  onLogAction: (riskCase: RiskCase) => void;
  onWorkflowFieldChange: <K extends keyof WorkflowFormState>(field: K, value: WorkflowFormState[K]) => void;
  onWorkflowSoftSignalChange: (field: keyof SoftSignalSnapshot, value: number | null) => void;
  onSubmitWorkflow: FormEventHandler<HTMLFormElement>;
  onCloseWorkflow: () => void;
  nextActionLabel: (riskLevel: RiskLevel) => string;
  formatTimestamp: (value: string) => string;
}

function RiskQueueSection({
  allowExports,
  allowInterventionLogging,
  isSubmitting,
  filteredCases,
  interventions,
  selectedWorkflowCase,
  workflowForm,
  search,
  riskFilter,
  programFilter,
  regionFilter,
  cohortFilter,
  phaseFilter,
  programs,
  regions,
  cohorts,
  phases,
  onSearchChange,
  onRiskFilterChange,
  onProgramFilterChange,
  onRegionFilterChange,
  onCohortFilterChange,
  onPhaseFilterChange,
  onExport,
  onFollowUpExport,
  onLogAction,
  onWorkflowFieldChange,
  onWorkflowSoftSignalChange,
  onSubmitWorkflow,
  onCloseWorkflow,
  nextActionLabel,
  formatTimestamp,
}: RiskQueueSectionProps) {
  return (
    <section className="action-layout">
      <article className="panel action-panel" data-testid="risk-queue-section">
        <div className="section-heading">
          <div>
            <span className="eyebrow">Beneficiary queue</span>
            <h2>High-priority follow-up list</h2>
          </div>
          {allowExports ? (
            <div className="connector-actions">
              <button className="secondary-button" type="button" onClick={() => onExport("risk_cases")} disabled={isSubmitting}>
                {isSubmitting ? "Working..." : "Export queue CSV"}
              </button>
              <button className="secondary-button" type="button" onClick={() => onFollowUpExport("whatsapp")} disabled={isSubmitting}>
                {isSubmitting ? "Working..." : "Export WhatsApp list"}
              </button>
              <button className="secondary-button" type="button" onClick={() => onFollowUpExport("sms")} disabled={isSubmitting}>
                {isSubmitting ? "Working..." : "Export SMS list"}
              </button>
              <button className="secondary-button" type="button" onClick={() => onFollowUpExport("field_visit")} disabled={isSubmitting}>
                {isSubmitting ? "Working..." : "Export visit schedule"}
              </button>
              <button className="secondary-button" type="button" onClick={() => onExport("interventions")} disabled={isSubmitting}>
                {isSubmitting ? "Working..." : "Export interventions CSV"}
              </button>
            </div>
          ) : null}
        </div>

        <div className="filters">
          <input
            className="search-input"
            type="search"
            aria-label="Risk queue search"
            placeholder="Search name, program, or region"
            value={search}
            onChange={(event) => onSearchChange(event.target.value)}
          />
          <select aria-label="Risk level filter" value={riskFilter} onChange={(event) => onRiskFilterChange(event.target.value as "All" | RiskLevel)}>
            <option value="All">All risks</option>
            <option value="High">High risk</option>
            <option value="Medium">Medium risk</option>
            <option value="Low">Low risk</option>
          </select>
          <select aria-label="Program filter" value={programFilter} onChange={(event) => onProgramFilterChange(event.target.value)}>
            {programs.map((program) => (
              <option value={program} key={program}>
                {program === "All" ? "All programs" : program}
              </option>
            ))}
          </select>
          <select aria-label="Region filter" value={regionFilter} onChange={(event) => onRegionFilterChange(event.target.value)}>
            {regions.map((region) => (
              <option value={region} key={region}>
                {region === "All" ? "All regions" : region}
              </option>
            ))}
          </select>
          <select aria-label="Cohort filter" value={cohortFilter} onChange={(event) => onCohortFilterChange(event.target.value)}>
            {cohorts.map((cohort) => (
              <option value={cohort} key={cohort}>
                {cohort === "All" ? "All cohorts" : cohort}
              </option>
            ))}
          </select>
          <select aria-label="Phase filter" value={phaseFilter} onChange={(event) => onPhaseFilterChange(event.target.value)}>
            {phases.map((phase) => (
              <option value={phase} key={phase}>
                {phase === "All" ? "All phases" : phase}
              </option>
            ))}
          </select>
        </div>

        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Beneficiary</th>
                <th>Risk</th>
                <th>Explanation</th>
                <th>Queue</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              {filteredCases.map((item) => (
                <tr key={item.id}>
                  <td>
                    <div className="beneficiary-cell">
                      <strong>{item.name}</strong>
                      <span>{item.program}</span>
                      <span>
                        {item.region}
                        {item.phase ? ` | ${item.phase}` : ""}
                      </span>
                    </div>
                  </td>
                  <td>
                    <span className={`risk-pill risk-${item.risk_level.toLowerCase()}`}>
                      {item.risk_level}
                    </span>
                    <div className="mini-metric">{item.risk_score}/100</div>
                  </td>
                  <td>
                    <div className="explanation-cell">
                      <p>{item.explanation}</p>
                      <div className="flag-row">
                        {item.flags.map((flag) => (
                          <span className="flag-chip" key={flag}>
                            {flag}
                          </span>
                        ))}
                        {item.opted_out ? <span className="flag-chip">Model opt-out</span> : null}
                      </div>
                    </div>
                  </td>
                  <td>
                    <div className="action-cell">
                      <p>{item.recommended_action}</p>
                      <span className="mini-metric">
                        {item.queue_bucket} | rank {item.queue_rank}
                      </span>
                      {item.tracing_protocol ? (
                        <span className="mini-metric">
                          Trace via {item.tracing_protocol.current_step.toUpperCase()} by {formatTimestamp(item.tracing_protocol.current_due_at ?? new Date().toISOString())}
                        </span>
                      ) : null}
                      <span className="mini-metric">
                        {(item.assigned_worker ?? "Unassigned worker")} | {(item.assigned_site ?? "Unassigned site")}
                      </span>
                    </div>
                  </td>
                  <td>
                    <div className="status-cell">
                      <span>{item.intervention_status}</span>
                      <span className="mini-metric">{item.confidence}</span>
                      {allowInterventionLogging ? (
                        <button type="button" onClick={() => onLogAction(item)} disabled={isSubmitting}>
                          {item.workflow?.intervention_id ? "Open workflow" : nextActionLabel(item.risk_level)}
                        </button>
                      ) : (
                        <span className="read-only-chip">Read only</span>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {filteredCases.length === 0 ? (
            <div className="empty-state">No beneficiaries match the current filters.</div>
          ) : null}
        </div>
      </article>

      <aside className="panel sidebar-panel">
        <div className="section-heading">
          <div>
            <span className="eyebrow">Action workflow</span>
            <h2>{selectedWorkflowCase ? `Follow-up for ${selectedWorkflowCase.name}` : "Select a queue item"}</h2>
          </div>
        </div>

        {selectedWorkflowCase ? (
          <form className="stacked-form" onSubmit={onSubmitWorkflow}>
            <div className="flag-row">
              <span className={`risk-pill risk-${selectedWorkflowCase.risk_level.toLowerCase()}`}>{selectedWorkflowCase.risk_level}</span>
              <span className="flag-chip">{selectedWorkflowCase.queue_bucket}</span>
              <span className="flag-chip">Rank {selectedWorkflowCase.queue_rank}</span>
            </div>
            <input type="text" value={workflowForm.action_type} onChange={(event) => onWorkflowFieldChange("action_type", event.target.value)} placeholder="Action label" />
            <select value={workflowForm.protocol_step} onChange={(event) => onWorkflowFieldChange("protocol_step", event.target.value as "sms" | "call" | "visit")}>
              <option value="sms">Protocol step: SMS / WhatsApp</option>
              <option value="call">Protocol step: Call</option>
              <option value="visit">Protocol step: Visit</option>
            </select>
            <select value={workflowForm.support_channel} onChange={(event) => onWorkflowFieldChange("support_channel", event.target.value as SupportChannel)}>
              <option value="call">Phone call</option>
              <option value="sms">SMS</option>
              <option value="visit">Home visit</option>
              <option value="whatsapp">WhatsApp</option>
              <option value="manual">Manual check-in</option>
            </select>
            <select value={workflowForm.status} onChange={(event) => onWorkflowFieldChange("status", event.target.value as WorkflowStatus)}>
              <option value="queued">Queued</option>
              <option value="attempted">Attempted</option>
              <option value="reached">Reached</option>
              <option value="verified">Verified</option>
              <option value="dismissed">Dismissed</option>
              <option value="closed">Closed</option>
              <option value="escalated">Escalated</option>
            </select>
            <select value={workflowForm.verification_status} onChange={(event) => onWorkflowFieldChange("verification_status", event.target.value as VerificationStatus)}>
              <option value="pending">Pending verification</option>
              <option value="still_enrolled">Still enrolled</option>
              <option value="re_engaged">Re-engaged</option>
              <option value="silent_transfer">Silent transfer</option>
              <option value="completed_elsewhere">Completed elsewhere</option>
              <option value="deceased">Deceased</option>
              <option value="unreachable">Unreachable</option>
              <option value="declined_support">Declined support</option>
              <option value="dropped_out_confirmed">Dropped out confirmed</option>
            </select>
            <input type="text" value={workflowForm.assigned_to} onChange={(event) => onWorkflowFieldChange("assigned_to", event.target.value)} placeholder="Assigned worker" />
            <input type="text" value={workflowForm.assigned_site} onChange={(event) => onWorkflowFieldChange("assigned_site", event.target.value)} placeholder="Assigned site" />
            <input type="datetime-local" value={workflowForm.due_at} onChange={(event) => onWorkflowFieldChange("due_at", event.target.value)} />
            <input type="number" min={0} value={workflowForm.attempt_count} onChange={(event) => onWorkflowFieldChange("attempt_count", Number(event.target.value))} />
            <label className="stacked-check">
              <span>Follow-up note</span>
              <textarea value={workflowForm.note} onChange={(event) => onWorkflowFieldChange("note", event.target.value)} rows={3} />
            </label>
            <label className="stacked-check">
              <span>Verification note</span>
              <textarea value={workflowForm.verification_note} onChange={(event) => onWorkflowFieldChange("verification_note", event.target.value)} rows={2} />
            </label>
            <label className="stacked-check">
              <span>Dismissal reason</span>
              <input type="text" value={workflowForm.dismissal_reason} onChange={(event) => onWorkflowFieldChange("dismissal_reason", event.target.value)} placeholder="Reason for override or dismissal" />
            </label>
            <label className="stacked-check">
              <span>Outcome</span>
              <select
                value={workflowForm.successful === null ? "unknown" : workflowForm.successful ? "successful" : "unsuccessful"}
                onChange={(event) =>
                  onWorkflowFieldChange(
                    "successful",
                    event.target.value === "unknown" ? null : event.target.value === "successful",
                  )
                }
              >
                <option value="unknown">Outcome not yet known</option>
                <option value="successful">Successful</option>
                <option value="unsuccessful">Unsuccessful</option>
              </select>
            </label>

            <div className="section-heading compact-heading">
              <div>
                <span className="eyebrow">Field observations</span>
                <h2>Soft indicators (1-5)</h2>
              </div>
            </div>
            {(
              [
                ["household_stability_signal", "Household stability"],
                ["economic_stress_signal", "Economic stress"],
                ["family_support_signal", "Family support risk"],
                ["health_change_signal", "Health change"],
                ["motivation_signal", "Motivation decline"],
              ] as Array<[keyof SoftSignalSnapshot, string]>
            ).map(([field, label]) => (
              <label className="mapping-row" key={field}>
                <span>{label}</span>
                <select
                  value={workflowForm.soft_signals[field] ?? ""}
                  onChange={(event) => onWorkflowSoftSignalChange(field, event.target.value ? Number(event.target.value) : null)}
                >
                  <option value="">Not recorded</option>
                  <option value="1">1</option>
                  <option value="2">2</option>
                  <option value="3">3</option>
                  <option value="4">4</option>
                  <option value="5">5</option>
                </select>
              </label>
            ))}

            <div className="connector-actions">
              <button className="primary-button" type="submit" disabled={isSubmitting}>
                {isSubmitting ? "Saving..." : selectedWorkflowCase.workflow?.intervention_id ? "Update workflow" : "Start workflow"}
              </button>
              <button className="secondary-button" type="button" onClick={onCloseWorkflow} disabled={isSubmitting}>
                Close panel
              </button>
            </div>
            <p className="helper-copy">
              Record the attempted action, verify the beneficiary&apos;s actual status, and dismiss or close the case only after documenting what happened.
            </p>
          </form>
        ) : (
          <div className="ops-note">
            <span className="eyebrow">Action loop</span>
            <p>Select a beneficiary from the queue to assign a worker, capture soft indicators, verify status, and close the follow-up loop.</p>
          </div>
        )}

        <div className="divider" />

        <div className="section-heading">
          <div>
            <span className="eyebrow">Intervention tracking</span>
            <h2>Recent actions</h2>
          </div>
        </div>

        <div className="intervention-list">
          {interventions.map((record) => (
            <div className="intervention-card" key={record.id}>
              <div>
                <strong>{record.beneficiary_name}</strong>
                <span>{record.action_type}</span>
              </div>
              <p>{record.note ?? "No note recorded."}</p>
              <span>
                {record.status}
                {record.verification_status ? ` | ${record.verification_status.replace(/_/g, " ")}` : ""}
              </span>
              <time>{formatTimestamp(record.logged_at)}</time>
            </div>
          ))}
        </div>

        <div className="ops-note">
          <span className="eyebrow">Guardrails</span>
          <p>
            The platform logs supportive outreach only. No beneficiary is automatically excluded or penalized by a risk score.
          </p>
        </div>
      </aside>
    </section>
  );
}

export default RiskQueueSection;
