/**
 * Aggregate analytics and reporting surface for supervisory users.
 *
 * This component groups retention curves, donor-oriented summary cards, model
 * status, and intervention-effectiveness views that are useful for program
 * oversight but not part of the day-to-day tracing workflow.
 */

import { Suspense, lazy } from "react";

import type {
  DonorReportSummary,
  FederatedLearningRound,
  InterventionEffectivenessSummary,
  ModelStatus,
  RetentionAnalytics,
  RetentionCurves,
} from "../types";


const RetentionChart = lazy(() => import("../RetentionChart"));

interface AnalyticsOverviewProps {
  summary: {
    top_risk_drivers: Array<{ name: string; impacted_beneficiaries: number; insight: string }>;
    region_alerts: Array<{ region: string; retention_delta: number; note: string }>;
  };
  retentionCurves: RetentionCurves;
  modelStatus: ModelStatus;
  biasAudit: ModelStatus["bias_audit"];
  retentionAnalytics: RetentionAnalytics;
  interventionEffectiveness: InterventionEffectivenessSummary;
  donorSummary: DonorReportSummary;
  federatedRounds: FederatedLearningRound[];
  federatedRoundName: string;
  driverMax: number;
  allowExports: boolean;
  allowModelTraining: boolean;
  isRefreshing: boolean;
  isSubmitting: boolean;
  onRefresh: () => void;
  onDonorExport: (format: "xlsx" | "pdf") => void;
  onFederatedRoundNameChange: (value: string) => void;
  onExportFederatedUpdate: () => void;
  onAggregateFederatedRound: () => void;
  formatMetricValue: (value: string | number | undefined) => string;
  formatRate: (value: number | null | undefined) => string;
  formatBiasDimension: (dimension: string) => string;
}

function AnalyticsOverview({
  summary,
  retentionCurves,
  modelStatus,
  biasAudit,
  retentionAnalytics,
  interventionEffectiveness,
  donorSummary,
  federatedRounds,
  federatedRoundName,
  driverMax,
  allowExports,
  allowModelTraining,
  isRefreshing,
  isSubmitting,
  onRefresh,
  onDonorExport,
  onFederatedRoundNameChange,
  onExportFederatedUpdate,
  onAggregateFederatedRound,
  formatMetricValue,
  formatRate,
  formatBiasDimension,
}: AnalyticsOverviewProps) {
  return (
    <>
      <section className="two-column-grid">
        <article className="panel">
          <div className="section-heading">
            <div>
              <span className="eyebrow">What is driving risk</span>
              <h2>Top signals this week</h2>
            </div>
          </div>
          <div className="driver-list">
            {summary.top_risk_drivers.map((driver) => (
              <div className="driver-row" key={driver.name}>
                <div className="driver-copy">
                  <strong>{driver.name}</strong>
                  <p>{driver.insight}</p>
                </div>
                <div className="driver-bar-track">
                  <div
                    className="driver-bar"
                    style={{
                      width: `${(driver.impacted_beneficiaries / driverMax) * 100}%`,
                    }}
                  />
                </div>
                <span className="driver-value">{driver.impacted_beneficiaries}</span>
              </div>
            ))}
          </div>

          <div className="alert-grid">
            {summary.region_alerts.map((alert) => (
              <div className="alert-card" key={alert.region}>
                <span className="meta-label">{alert.region}</span>
                <strong className={alert.retention_delta < 0 ? "delta-down" : "delta-up"}>
                  {alert.retention_delta > 0 ? "+" : ""}
                  {alert.retention_delta} pts
                </strong>
                <p>{alert.note}</p>
              </div>
            ))}
          </div>
        </article>

        <article className="panel">
          <div className="section-heading">
            <div>
              <span className="eyebrow">Aggregate retention</span>
              <h2>Cohort retention curves</h2>
            </div>
            <button className="secondary-button" type="button" onClick={onRefresh}>
              {isRefreshing ? "Refreshing..." : "Refresh"}
            </button>
          </div>
          <p className="chart-copy">{retentionCurves.narrative}</p>
          <div className="chart-wrap">
            <Suspense fallback={<div className="chart-loading">Loading retention chart...</div>}>
              <RetentionChart curves={retentionCurves} />
            </Suspense>
          </div>
        </article>
      </section>

      <section className="metrics-grid secondary-metrics">
        <article className="metric-card neutral">
          <span>Labeled training rows</span>
          <strong>{modelStatus.training_rows.toLocaleString()}</strong>
        </article>
        <article className="metric-card warning">
          <span>Observed dropouts</span>
          <strong>{modelStatus.positive_rows.toLocaleString()}</strong>
        </article>
        <article className="metric-card positive">
          <span>Feature count</span>
          <strong>{modelStatus.feature_count.toLocaleString()}</strong>
        </article>
        <article className="metric-card neutral">
          <span>Top-20% recall</span>
          <strong>{formatMetricValue(modelStatus.metrics.top_20pct_recall)}</strong>
        </article>
        <article className="metric-card warning">
          <span>High-risk threshold</span>
          <strong>&ge; {formatMetricValue(modelStatus.metrics.high_risk_threshold_score)}</strong>
        </article>
        <article className="metric-card positive">
          <span>High-risk precision</span>
          <strong>{formatMetricValue(modelStatus.metrics.high_risk_precision)}</strong>
        </article>
        <article className="metric-card neutral">
          <span>Medium+ recall</span>
          <strong>{formatMetricValue(modelStatus.metrics.medium_or_higher_recall)}</strong>
        </article>
      </section>

      <section className="panel audit-panel">
        <div className="section-heading">
          <div>
            <span className="eyebrow">Bias audit</span>
            <h2>Fairness checks before deployment</h2>
          </div>
          <span
            className={`risk-pill ${
              biasAudit?.status === "attention"
                ? "risk-high"
                : biasAudit?.status === "ok"
                  ? "risk-low"
                  : "risk-medium"
            }`}
          >
            {biasAudit?.status ?? "insufficient_data"}
          </span>
        </div>
        <p className="chart-copy">
          {biasAudit?.note ?? "A fairness audit will appear once there is enough labeled validation data for a trained model."}
        </p>
        <div className="alert-grid">
          {(biasAudit?.dimensions ?? []).map((dimension) => (
            <div className="alert-card" key={dimension.dimension}>
              <span className="meta-label">{formatBiasDimension(dimension.dimension)}</span>
              <strong
                className={
                  dimension.status === "attention" ? "delta-down" : dimension.status === "ok" ? "delta-up" : undefined
                }
              >
                {dimension.status.replace(/_/g, " ")}
              </strong>
              <p>{dimension.note}</p>
              <div className="warning-list">
                {dimension.groups.slice(0, 3).map((group) => (
                  <span className="flag-chip" key={`${dimension.dimension}-${group.group_name}`}>
                    {group.group_name}: FPR {formatRate(group.false_positive_rate)} | Recall {formatRate(group.recall_rate)}
                  </span>
                ))}
              </div>
            </div>
          ))}
        </div>
      </section>

      <section className="two-column-grid">
        <article className="panel">
          <div className="section-heading">
            <div>
              <span className="eyebrow">Portfolio analytics</span>
              <h2>Retention breakdowns and trend lines</h2>
            </div>
          </div>
          <p className="chart-copy">{retentionAnalytics.narrative}</p>
          <div className="warning-list">
            {retentionAnalytics.trend_highlights.map((item) => (
              <span className="flag-chip" key={item}>
                {item}
              </span>
            ))}
          </div>
          <div className="table-wrap compact-table">
            <table>
              <thead>
                <tr>
                  <th>Dimension</th>
                  <th>Group</th>
                  <th>Retention</th>
                  <th>Recent dropout</th>
                  <th>Active</th>
                </tr>
              </thead>
              <tbody>
                {retentionAnalytics.breakdowns.slice(0, 8).map((row) => (
                  <tr key={`${row.dimension}-${row.group_name}`}>
                    <td>{row.dimension}</td>
                    <td>{row.group_name}</td>
                    <td>{formatRate(row.retention_rate)}</td>
                    <td>{formatRate(row.recent_dropout_rate)}</td>
                    <td>{row.active_beneficiaries}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </article>

        <article className="panel">
          <div className="section-heading">
            <div>
              <span className="eyebrow">Intervention effectiveness</span>
              <h2>Observed re-engagement patterns</h2>
            </div>
          </div>
          <p className="chart-copy">{interventionEffectiveness.narrative}</p>
          <div className="warning-list">
            {interventionEffectiveness.top_recommendations.map((item) => (
              <span className="flag-chip" key={item}>
                {item}
              </span>
            ))}
          </div>
          <div className="table-wrap compact-table">
            <table>
              <thead>
                <tr>
                  <th>Action</th>
                  <th>Context</th>
                  <th>Attempts</th>
                  <th>Success</th>
                  <th>Strength</th>
                </tr>
              </thead>
              <tbody>
                {interventionEffectiveness.rows.slice(0, 8).map((row) => (
                  <tr key={`${row.action_type}-${row.context_label}`}>
                    <td>{row.action_type}</td>
                    <td>{row.context_label}</td>
                    <td>{row.attempts}</td>
                    <td>{formatRate(row.success_rate)}</td>
                    <td>{row.recommendation_strength}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </article>
      </section>

      <section className="two-column-grid">
        <article className="panel">
          <div className="section-heading">
            <div>
              <span className="eyebrow">Donor-ready reporting</span>
              <h2>Adaptive management exports</h2>
            </div>
            {allowExports ? (
              <div className="connector-actions">
                <button className="secondary-button" type="button" onClick={() => onDonorExport("xlsx")} disabled={isSubmitting}>
                  {isSubmitting ? "Working..." : "Export Excel"}
                </button>
                <button className="secondary-button" type="button" onClick={() => onDonorExport("pdf")} disabled={isSubmitting}>
                  {isSubmitting ? "Working..." : "Export PDF"}
                </button>
              </div>
            ) : null}
          </div>
          <p className="chart-copy">{donorSummary.narrative}</p>
          <div className="alert-grid">
            {Object.entries(donorSummary.headline_metrics).map(([key, value]) => (
              <div className="alert-card" key={key}>
                <span className="meta-label">{key.replace(/_/g, " ")}</span>
                <strong>{formatMetricValue(value)}</strong>
              </div>
            ))}
          </div>
        </article>

        <article className="panel">
          <div className="section-heading">
            <div>
              <span className="eyebrow">Federated learning</span>
              <h2>Cross-deployment base model sharing</h2>
            </div>
          </div>
          <div className="stacked-form">
            <input
              type="text"
              value={federatedRoundName}
              onChange={(event) => onFederatedRoundNameChange(event.target.value)}
              placeholder="Round name"
            />
            {allowModelTraining ? (
              <div className="connector-actions">
                <button className="secondary-button" type="button" onClick={onExportFederatedUpdate} disabled={isSubmitting}>
                  {isSubmitting ? "Working..." : "Export local update"}
                </button>
                <button className="secondary-button" type="button" onClick={onAggregateFederatedRound} disabled={isSubmitting}>
                  {isSubmitting ? "Working..." : "Aggregate round"}
                </button>
              </div>
            ) : null}
          </div>
          <div className="intervention-list">
            {federatedRounds.map((round) => (
              <div className="intervention-card" key={round.id}>
                <div>
                  <strong>{round.round_name}</strong>
                  <span>{round.status}</span>
                </div>
                <p>{round.aggregation_note ?? `${round.updates.length} update(s) collected.`}</p>
              </div>
            ))}
          </div>
        </article>
      </section>
    </>
  );
}

export default AnalyticsOverview;
