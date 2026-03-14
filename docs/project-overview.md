# Project Overview

## What RetainAI Is

RetainAI is an open-source retention operations platform for development
programs that manage ongoing beneficiary relationships.

It is designed for organizations that already collect monitoring data but do
not yet have a reliable way to turn that data into timely, capacity-aware
follow-up action.

RetainAI is meant to sit alongside existing operational systems such as:

- CommCare
- DHIS2 Tracker
- KoboToolbox
- ODK Central
- Salesforce NPSP
- CSV/XLSX-based monitoring and MIS workflows

It does not replace those systems. It uses their data to support retention
operations, validation, and governance.

## The Core Problem

Many programs only recognize disengagement after it is already well advanced.
At that point, follow-up is harder, more expensive, and less likely to succeed.

At the same time, field teams rarely have enough capacity to call, visit, or
verify every case. They need help deciding:

- who most likely needs attention now
- what kind of follow-up is proportionate
- how to record what happened
- whether the system is actually helping

That is the problem RetainAI is built to address.

## Primary Use Case

RetainAI helps a program answer five operational questions:

1. Which beneficiaries are most likely to disengage in the near term?
2. Given limited capacity, which cases should staff prioritize first?
3. What supportive action should be attempted next?
4. What happened after follow-up?
5. Is the system improving retention operations, or only producing impressive
   scores?

## Intended Users

### M&E / MEAL officers

- configure imports and connectors
- review model validation and shadow-mode readiness
- manage retraining and program settings
- interpret fairness, drift, and evidence outputs

### Program and field coordinators

- work from prioritized follow-up queues
- assign, attempt, verify, dismiss, and close cases
- capture actual outcomes and soft observations

### Program leadership

- review retention trends and intervention effectiveness
- compare risk load to staff capacity
- export donor-ready and governance-facing summaries

### Researchers and audit partners

- run formal validation workflows
- inspect fairness and calibration results
- assess whether the platform is operationally credible

## What RetainAI Deliberately Does Not Do

- It does not automatically disenroll or penalize beneficiaries.
- It does not claim to infer permanent "true dropout" when only monitoring
  disengagement is observed.
- It does not eliminate the need for local human judgment.
- It does not guarantee cross-context generalizability without local
  validation.
- It does not treat predictive performance as proof of real-world impact.

## Supported Program Types

The current codebase includes seeded and synthetic support for:

- cash transfer and social-protection style programs
- education retention programs
- health adherence and appointment-based programs

The most operationally mature fit is any program with repeated, timestamped
interactions and a meaningful notion of missed visits, missed attendance, or
missed collection cycles.

## Product Capabilities

### Data ingestion

- CSV and Excel import
- guided field mapping
- schema detection and type inference
- quality checks and anomaly logging
- connector configuration for common NGO systems

### Risk scoring

- program-specific and base-model-assisted scoring
- configurable labeling windows
- capacity-aware ranking
- plain-language explanations
- uncertainty and fairness reporting

### Operational workflows

- per-beneficiary follow-up workflows
- assign / attempt / verify / dismiss / close states
- escalation logic
- per-worker and per-site queue logic
- soft-indicator capture

### Analytics and evidence

- cohort retention curves
- breakdowns by region, gender, household type, and phase
- donor exports
- intervention effectiveness summaries
- temporal backtesting
- shadow-mode validation

### Governance and safeguards

- consent and opt-out handling
- explanation support
- tokenized exports
- audit trails
- privacy-aware controls

## Current Maturity Statement

RetainAI is documented and implemented as a serious pilot-grade system. It is
not a blanket claim of real-world effectiveness across all contexts.

Before live deployment, adopters should complete:

- partner bundle validation
- retrospective backtests
- fairness review
- shadow mode
- operational training
- legal and safeguarding review

## Success Definition

The project should be judged by:

- whether flagged cases are actionable within real staff capacity
- whether the workflow is understandable and usable by operational staff
- whether the system improves verified follow-up and re-engagement
- whether safeguards prevent harmful or exclusionary use
- whether maintainers can hand it off and sustain it as open digital
  infrastructure

## Related Documents

- [Getting Started](getting-started.md)
- [Implementation Guide](implementation-guide.md)
- [Workflow Reference](workflow-reference.md)
- [Limitations And Known Risks](limitations-and-known-risks.md)
