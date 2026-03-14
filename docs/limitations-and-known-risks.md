# Limitations And Known Risks

This document states the most important current limitations of the project in a
clear and public way.

It exists because responsible documentation should be explicit about what the
software cannot yet guarantee.

## Product Limitations

- RetainAI does not prove real-world impact on its own.
- RetainAI does not guarantee that a high-risk flag means a beneficiary will
  truly and permanently drop out.
- RetainAI does not remove the need for local follow-up protocols.
- RetainAI does not replace legal or data-protection review.
- RetainAI does not support automated exclusion decisions.

## Modeling Limitations

- model performance is context-specific
- local validation is required before live use
- public benchmarks and synthetic stress tests are not substitutes for partner
  data
- fairness behavior can vary materially across programs, cohorts, and regions
- labels are often noisy because "dropout" is operationally defined, not a
  perfect ground truth

## Data Limitations

- NGO monitoring data is often incomplete or inconsistent
- connectors cannot fix upstream data-quality problems
- some valuable field observations still depend on staff entering soft signals
- silent transfers and misclassification can distort historical labels

## Deployment Limitations

- the repository includes strong deployment assets, but each deployment still
  needs local hardening
- infrastructure, secret management, and regional policy enforcement depend on
  the adopting organization
- self-hosting is supported, but operator capability still matters

## Support Limitations

- the open-source project does not imply a 24/7 support obligation
- deployers remain responsible for local operations and incident response
- support expectations must be made explicit by any future steward

## Current Technical Debt To Keep In Mind

Examples of current limitations or debt categories:

- some third-party dependency warnings remain in the Python stack
- frontend dependency vulnerabilities may still require future remediation
- full production assurance depends on real deployment verification and steward
  capacity, not just repository completeness

## Why This Document Matters

Projects in sensitive domains are often harmed by under-documented limitations.
This document is part of the project's safety posture: it helps prevent the
software from being oversold or misunderstood.

## Related Documents

- [Project Overview](project-overview.md)
- [Research and Validation](research-evidence-and-validation.md)
- [Model Governance](model-governance.md)
- [Steward Handoff Playbook](steward-handoff-playbook.md)
