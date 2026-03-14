/**
 * Model validation and shadow-mode control panel.
 *
 * This section is where program leads and M&E officers move from "the model can
 * score cases" to "the model has been tested well enough to trust in shadow
 * mode." It exposes backtest settings, threshold expectations, persisted
 * evaluation runs, and shadow-mode snapshots.
 */

import type { FormEventHandler } from "react";

import type { ModelEvaluationRecord, Program, ProgramValidationSetting, ShadowRun } from "../types";

interface ValidationFormState {
  shadow_mode_enabled: boolean;
  shadow_prediction_window_days: number;
  minimum_precision_at_capacity: number;
  minimum_recall_at_capacity: number;
  require_fairness_review: boolean;
}

interface EvaluationFormState {
  temporal_strategy: "holdout" | "rolling";
  min_history_days: number;
  holdout_share: number;
  rolling_folds: number;
  top_k_share: number;
  top_k_capacity_text: string;
  calibration_bins: number;
  bootstrap_iterations: number;
}

interface ValidationSectionProps {
  allowProgramAdmin: boolean;
  isSubmitting: boolean;
  programs: Program[];
  selectedProgramId: string;
  selectedProgramValidation?: ProgramValidationSetting | null;
  validationForm: ValidationFormState;
  evaluationForm: EvaluationFormState;
  evaluations: ModelEvaluationRecord[];
  shadowRuns: ShadowRun[];
  onSelectedProgramIdChange: (value: string) => void;
  onValidationFormChange: (field: keyof ValidationFormState, value: string | number | boolean) => void;
  onEvaluationFormChange: (field: keyof EvaluationFormState, value: string | number) => void;
  onUpdateProgramValidation: FormEventHandler<HTMLFormElement>;
  onRunBacktest: () => void;
  onCreateShadowRun: () => void;
  formatTimestamp: (value: string) => string;
  formatRate: (value: number | null | undefined) => string;
}

function ValidationSection({
  allowProgramAdmin,
  isSubmitting,
  programs,
  selectedProgramId,
  selectedProgramValidation,
  validationForm,
  evaluationForm,
  evaluations,
  shadowRuns,
  onSelectedProgramIdChange,
  onValidationFormChange,
  onEvaluationFormChange,
  onUpdateProgramValidation,
  onRunBacktest,
  onCreateShadowRun,
  formatTimestamp,
  formatRate,
}: ValidationSectionProps) {
  return (
    <section className="two-column-grid">
      <article className="panel">
        <div className="section-heading">
          <div>
            <span className="eyebrow">Validation</span>
            <h2>Shadow-mode readiness</h2>
          </div>
        </div>
        {allowProgramAdmin ? (
          <form className="stacked-form" onSubmit={onUpdateProgramValidation}>
            <select value={selectedProgramId} onChange={(event) => onSelectedProgramIdChange(event.target.value)} required>
              <option value="">Select a program</option>
              {programs.map((program) => (
                <option value={program.id} key={program.id}>
                  {program.name}
                </option>
              ))}
            </select>
            <label className="checkbox-row">
              <input
                type="checkbox"
                checked={validationForm.shadow_mode_enabled}
                onChange={(event) => onValidationFormChange("shadow_mode_enabled", event.target.checked)}
              />
              <span>Enable shadow mode for this program</span>
            </label>
            <input
              type="number"
              min={7}
              max={90}
              value={validationForm.shadow_prediction_window_days}
              onChange={(event) => onValidationFormChange("shadow_prediction_window_days", Number(event.target.value))}
            />
            <div className="inline-grid">
              <label className="stacked-check">
                <span>Minimum precision at capacity</span>
                <input
                  type="number"
                  step="0.05"
                  min={0.05}
                  max={1}
                  value={validationForm.minimum_precision_at_capacity}
                  onChange={(event) => onValidationFormChange("minimum_precision_at_capacity", Number(event.target.value))}
                />
              </label>
              <label className="stacked-check">
                <span>Minimum recall at capacity</span>
                <input
                  type="number"
                  step="0.05"
                  min={0.05}
                  max={1}
                  value={validationForm.minimum_recall_at_capacity}
                  onChange={(event) => onValidationFormChange("minimum_recall_at_capacity", Number(event.target.value))}
                />
              </label>
            </div>
            <label className="checkbox-row">
              <input
                type="checkbox"
                checked={validationForm.require_fairness_review}
                onChange={(event) => onValidationFormChange("require_fairness_review", event.target.checked)}
              />
              <span>Require fairness review before live use</span>
            </label>
            <button className="primary-button" type="submit" disabled={isSubmitting || !selectedProgramId}>
              {isSubmitting ? "Saving..." : "Save validation settings"}
            </button>
            {selectedProgramValidation ? (
              <span className="helper-copy compact-copy">
                Last evaluation status: {selectedProgramValidation.last_evaluation_status ?? "none yet"}.
                {selectedProgramValidation.last_shadow_run_at ? ` Last shadow run ${formatTimestamp(selectedProgramValidation.last_shadow_run_at)}.` : ""}
              </span>
            ) : null}
          </form>
        ) : (
          <p className="helper-copy">Validation controls are limited to admins and M&amp;E officers.</p>
        )}

        <div className="divider" />

        <div className="section-heading compact-heading">
          <div>
            <span className="eyebrow">Retrospective evidence</span>
            <h2>Run formal backtests</h2>
          </div>
        </div>
        <div className="stacked-form">
          <div className="inline-grid">
            <label className="stacked-check">
              <span>Temporal strategy</span>
              <select value={evaluationForm.temporal_strategy} onChange={(event) => onEvaluationFormChange("temporal_strategy", event.target.value)}>
                <option value="rolling">Rolling folds</option>
                <option value="holdout">Single temporal holdout</option>
              </select>
            </label>
            <label className="stacked-check">
              <span>Minimum history days</span>
              <input type="number" min={14} max={365} value={evaluationForm.min_history_days} onChange={(event) => onEvaluationFormChange("min_history_days", Number(event.target.value))} />
            </label>
          </div>
          <div className="inline-grid">
            <label className="stacked-check">
              <span>Top-K share</span>
              <input type="number" step="0.05" min={0.05} max={0.5} value={evaluationForm.top_k_share} onChange={(event) => onEvaluationFormChange("top_k_share", Number(event.target.value))} />
            </label>
            <label className="stacked-check">
              <span>Explicit Top-K capacity</span>
              <input type="number" min={1} placeholder="Optional" value={evaluationForm.top_k_capacity_text} onChange={(event) => onEvaluationFormChange("top_k_capacity_text", event.target.value)} />
            </label>
          </div>
          <div className="inline-grid">
            <label className="stacked-check">
              <span>Holdout share</span>
              <input type="number" step="0.05" min={0.1} max={0.5} value={evaluationForm.holdout_share} onChange={(event) => onEvaluationFormChange("holdout_share", Number(event.target.value))} />
            </label>
            <label className="stacked-check">
              <span>Rolling folds</span>
              <input type="number" min={2} max={8} value={evaluationForm.rolling_folds} onChange={(event) => onEvaluationFormChange("rolling_folds", Number(event.target.value))} />
            </label>
          </div>
          <div className="inline-grid">
            <label className="stacked-check">
              <span>Calibration bins</span>
              <input type="number" min={3} max={10} value={evaluationForm.calibration_bins} onChange={(event) => onEvaluationFormChange("calibration_bins", Number(event.target.value))} />
            </label>
            <label className="stacked-check">
              <span>Bootstrap iterations</span>
              <input type="number" min={20} max={500} value={evaluationForm.bootstrap_iterations} onChange={(event) => onEvaluationFormChange("bootstrap_iterations", Number(event.target.value))} />
            </label>
          </div>
          <div className="connector-actions">
            <button className="secondary-button" type="button" onClick={onRunBacktest} disabled={isSubmitting || !selectedProgramId}>
              {isSubmitting ? "Working..." : "Run backtest"}
            </button>
            <button className="primary-button" type="button" onClick={onCreateShadowRun} disabled={isSubmitting || !selectedProgramId}>
              {isSubmitting ? "Working..." : "Capture shadow run"}
            </button>
          </div>
          <p className="helper-copy compact-copy">
            Backtests persist their reports for later review. Shadow runs snapshot the current queue and can later be scored against observed outcomes.
          </p>
        </div>
      </article>

      <article className="panel">
        <div className="section-heading">
          <div>
            <span className="eyebrow">Evidence log</span>
            <h2>Recent evaluations and shadow runs</h2>
          </div>
        </div>
        <div className="issue-list">
          {evaluations.length === 0 ? (
            <div className="empty-state">No evaluation reports captured yet.</div>
          ) : (
            evaluations.map((evaluation) => (
              <div className="issue-row" key={evaluation.id}>
                <div>
                  <strong>{evaluation.status.replace(/_/g, " ")}</strong>
                  <span>
                    {evaluation.algorithm} | {evaluation.samples_evaluated} cases | {formatRate(evaluation.report.metrics.top_k_precision.value)} precision@K
                  </span>
                  <span>{evaluation.report.note}</span>
                </div>
                <span>{formatTimestamp(evaluation.created_at)}</span>
              </div>
            ))
          )}
        </div>

        <div className="divider" />

        <div className="issue-list">
          {shadowRuns.length === 0 ? (
            <div className="empty-state">No shadow runs captured yet.</div>
          ) : (
            shadowRuns.map((run) => (
              <div className="issue-row" key={run.id}>
                <div>
                  <strong>{run.program_name}</strong>
                  <span>
                    {run.status.replace(/_/g, " ")} | {run.cases_captured} cases | precision {formatRate(run.top_k_precision)}
                  </span>
                </div>
                <span>{formatTimestamp(run.created_at)}</span>
              </div>
            ))
          )}
        </div>
      </article>
    </section>
  );
}

export default ValidationSection;
