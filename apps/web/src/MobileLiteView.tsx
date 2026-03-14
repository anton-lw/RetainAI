/**
 * Mobile-lite field view for constrained devices and fast in-field triage.
 *
 * The main dashboard is designed for supervisors and M&E staff. This component
 * is the narrower field-facing surface: fewer controls, faster scanning, and a
 * simpler explanation-first presentation of active cases and interventions.
 */

import type { AppData, CurrentUser } from "./types";

interface MobileLiteViewProps {
  bundle: AppData;
  currentUser: CurrentUser | null;
  isSubmitting: boolean;
  allowInterventionLogging: boolean;
  onLogIntervention: (beneficiaryId: string, riskLevel: "High" | "Medium" | "Low") => void;
  onExplain: (beneficiaryId: string) => void;
}

function MobileLiteView({
  bundle,
  currentUser,
  isSubmitting,
  allowInterventionLogging,
  onLogIntervention,
  onExplain,
}: MobileLiteViewProps) {
  const topCases = bundle.risk_cases.slice(0, 6);
  const recentInterventions = bundle.interventions.slice(0, 5);

  return (
    <section className="mobile-lite-stack" data-testid="mobile-lite-view">
      <article className="panel">
        <span className="eyebrow">Field mode</span>
        <h2>Mobile-lite follow-up queue</h2>
        <p className="chart-copy">
          Compact workflow for coordinators in low-connectivity settings. Cached data remains visible when the API is briefly unavailable.
        </p>
        <div className="hero-metrics compact-metrics">
          <div className="metric-card">
            <span>High risk</span>
            <strong>{bundle.summary.high_risk_cases}</strong>
          </div>
          <div className="metric-card">
            <span>Weekly due</span>
            <strong>{bundle.summary.weekly_followups_due}</strong>
          </div>
          <div className="metric-card">
            <span>User</span>
            <strong>{currentUser?.full_name ?? "Offline cache"}</strong>
          </div>
        </div>
      </article>

      <article className="panel">
        <div className="section-heading">
          <div>
            <span className="eyebrow">Top queue</span>
            <h2>Immediate follow-ups</h2>
          </div>
        </div>
        <div className="intervention-list">
          {topCases.map((riskCase) => (
            <div className="intervention-card" key={`mobile-${riskCase.id}`}>
              <div>
                <strong>{riskCase.name}</strong>
                <span>{riskCase.program}</span>
              </div>
              <p>{riskCase.explanation}</p>
              <div className="flag-row">
                <span className={`risk-pill risk-${riskCase.risk_level.toLowerCase()}`}>{riskCase.risk_level}</span>
                <span className="flag-chip">{riskCase.region}</span>
                <span className="flag-chip">{riskCase.confidence}</span>
              </div>
              <div className="connector-actions">
                <button className="secondary-button" type="button" onClick={() => onExplain(riskCase.id)} disabled={isSubmitting}>
                  Explain case
                </button>
                {allowInterventionLogging ? (
                  <button
                    className="primary-button"
                    type="button"
                    onClick={() => onLogIntervention(riskCase.id, riskCase.risk_level)}
                    disabled={isSubmitting}
                  >
                    Log follow-up
                  </button>
                ) : null}
              </div>
            </div>
          ))}
        </div>
      </article>

      <article className="panel">
        <div className="section-heading">
          <div>
            <span className="eyebrow">Recent actions</span>
            <h2>Latest intervention log</h2>
          </div>
        </div>
        <div className="intervention-list">
          {recentInterventions.map((entry) => (
            <div className="intervention-card" key={`${entry.beneficiary_id}-${entry.logged_at}`}>
              <div>
                <strong>{entry.beneficiary_name}</strong>
                <span>{entry.action_type}</span>
              </div>
              <p>{entry.note ?? "No note recorded."}</p>
            </div>
          ))}
        </div>
      </article>
    </section>
  );
}

export default MobileLiteView;
