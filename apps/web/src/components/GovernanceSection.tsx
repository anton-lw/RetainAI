/**
 * Governance and privacy controls for beneficiary-level safeguards.
 *
 * The section exposes opt-out state, explanation access, export governance, and
 * alert review in one place so privileged users can handle sensitive cases
 * without mixing those controls into the day-to-day field queue.
 */

import type { BeneficiaryGovernanceRecord, GovernanceAlert } from "../types";

interface GovernanceSectionProps {
  governanceAlerts: GovernanceAlert[];
  governanceBeneficiaries: BeneficiaryGovernanceRecord[];
  allowGovernanceManagement: boolean;
  isSubmitting: boolean;
  onShowExplanation: (beneficiaryId: string) => void;
  onToggleOptOut: (beneficiaryId: string, optedOut: boolean) => void;
  onConsentUpdate: (beneficiaryId: string, status: "granted" | "withdrawn") => void;
}

function GovernanceSection({
  governanceAlerts,
  governanceBeneficiaries,
  allowGovernanceManagement,
  isSubmitting,
  onShowExplanation,
  onToggleOptOut,
  onConsentUpdate,
}: GovernanceSectionProps) {
  return (
    <section className="two-column-grid">
      <article className="panel">
        <div className="section-heading">
          <div>
            <span className="eyebrow">Governance alerts</span>
            <h2>Potential punitive dropout patterns</h2>
          </div>
        </div>
        <p className="chart-copy">
          These alerts flag beneficiaries who dropped out with elevated disengagement signals but no supportive intervention logged in the prior 30 days.
        </p>
        <div className="intervention-list">
          {governanceAlerts.length === 0 ? (
            <div className="empty-state">No governance alerts are active right now.</div>
          ) : (
            governanceAlerts.map((alert) => (
              <div className="intervention-card" key={`${alert.beneficiary_id}-${alert.dropout_date}`}>
                <div>
                  <strong>{alert.beneficiary_name}</strong>
                  <span>{alert.program_name}</span>
                </div>
                <p>{alert.note}</p>
                <div className="flag-row">
                  <span className={`risk-pill ${alert.alert_level === "attention" ? "risk-high" : "risk-medium"}`}>
                    {alert.alert_level}
                  </span>
                  <span className="flag-chip">{alert.region}</span>
                  <span className="flag-chip">{alert.risk_level} risk</span>
                </div>
              </div>
            ))
          )}
        </div>
      </article>

      <article className="panel">
        <div className="section-heading">
          <div>
            <span className="eyebrow">Beneficiary rights</span>
            <h2>Model participation controls</h2>
          </div>
        </div>
        <p className="chart-copy">
          Opted-out beneficiaries stay in the program and on the operational queue, but RetainAI excludes them from model training and uses heuristic-only scoring.
        </p>
        <div className="intervention-list">
          {governanceBeneficiaries.map((beneficiary) => (
            <div className="intervention-card" key={beneficiary.id}>
              <div>
                <strong>{beneficiary.full_name}</strong>
                <span>{beneficiary.program_name}</span>
              </div>
              <p>
                {beneficiary.external_id_masked} | {beneficiary.region} | {beneficiary.status}
              </p>
              <div className="flag-row">
                <span className={`risk-pill risk-${beneficiary.risk_level.toLowerCase()}`}>
                  {beneficiary.risk_level} {beneficiary.risk_score}
                </span>
                <span className="flag-chip">Last contact {beneficiary.last_contact_days}d</span>
                <span className="flag-chip">Consent {beneficiary.modeling_consent_status}</span>
                {beneficiary.pii_token ? <span className="flag-chip">{beneficiary.pii_token}</span> : null}
                {beneficiary.opted_out ? <span className="flag-chip">Opted out</span> : null}
              </div>
              <div className="connector-actions">
                <button className="secondary-button" type="button" onClick={() => onShowExplanation(beneficiary.id)} disabled={isSubmitting}>
                  Explanation sheet
                </button>
                {allowGovernanceManagement ? (
                  <>
                    <button
                      className="secondary-button"
                      type="button"
                      onClick={() => onToggleOptOut(beneficiary.id, !beneficiary.opted_out)}
                      disabled={isSubmitting}
                    >
                      {beneficiary.opted_out ? "Re-enable modeling" : "Opt out of modeling"}
                    </button>
                    <button
                      className="secondary-button"
                      type="button"
                      onClick={() => onConsentUpdate(beneficiary.id, "granted")}
                      disabled={isSubmitting}
                    >
                      Mark consent granted
                    </button>
                    <button
                      className="secondary-button"
                      type="button"
                      onClick={() => onConsentUpdate(beneficiary.id, "withdrawn")}
                      disabled={isSubmitting}
                    >
                      Withdraw consent
                    </button>
                  </>
                ) : (
                  <span className="read-only-chip">Read only</span>
                )}
              </div>
            </div>
          ))}
        </div>
      </article>
    </section>
  );
}

export default GovernanceSection;
