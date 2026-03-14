# Governance

## Purpose

RetainAI exists to increase retention and supportive follow-up quality in global development programs. It is intended to be maintained as open digital infrastructure rather than a closed proprietary product.

## Ownership

- The repository is collectively authored by its contributors.
- Each contributor retains copyright to their own contribution.
- All contributions merged into the project are licensed under the terms in [LICENSE](LICENSE).
- Until a formal steward transfer is completed, repository stewardship sits with Anton Waagaard (`hello@antons.site`).

This ownership model is designed to make future institutional handoff possible without revoking existing open rights.

## Publication Requirement

Before formal public release or DPGA submission, the current steward must
publish a named interim or permanent maintainer identity and update the
repository metadata listed in
[docs/public-metadata-and-steward-template.md](docs/public-metadata-and-steward-template.md).

The project should not be presented as anonymously stewarded at publication
time.

The current named interim steward is Anton Waagaard (`hello@antons.site`).

## Stewardship Model

The intended long-term model is transfer to, or sustained stewardship by, a mission-aligned public-interest organization with the operational capacity to maintain open-source infrastructure for NGOs, ministries, or research partners.

Possible steward profiles include:

- an open-source digital health or case-management platform organization
- a technical NGO or nonprofit infrastructure team
- a university or research institution with an explicit maintenance commitment
- a multi-organization public-good consortium

Any transfer of stewardship should preserve the open-source license and public documentation.

## Decision-Making

Project decisions should optimize for:

1. beneficiary safety and benefit
2. operational usefulness for implementing organizations
3. transparency and explainability
4. privacy and data-protection compliance
5. maintainability as an open-source public good

When these goals conflict, beneficiary safety and legal/ethical obligations take precedence over speed or feature breadth.

## Roles

### Core maintainers

Core maintainers are responsible for:

- roadmap and release decisions
- security and privacy triage
- approving breaking architectural changes
- managing the public-good documentation set
- evaluating steward-transfer opportunities

### Contributors

Contributors may propose code, documentation, tests, research notes, or deployment assets. Contributor responsibilities are documented in [CONTRIBUTING.md](CONTRIBUTING.md) and [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md).

### Deploying organizations

Organizations deploying RetainAI are responsible for:

- lawful and ethical local use
- deployment configuration and infrastructure security
- defining program-appropriate dropout labels
- validating model performance on their own data
- ensuring staff training, safeguarding, and beneficiary communication

## Release Policy

Changes affecting these areas require extra review:

- privacy, consent, data export, or tokenization behavior
- risk scoring logic or default thresholds
- intervention workflow semantics
- authentication, authorization, session, or audit behavior
- connector write-back behavior into external systems
- evaluation or fairness methodology

Releases should not be described as production-ready for a given deployment until that deployment has completed its own validation and security review.

## Openness and Public-Good Commitments

RetainAI aims to remain:

- openly licensed
- publicly documented
- platform-independent where feasible
- interoperable with widely used open systems
- explicit about limitations and deployment risks

## Governance Artifacts

The following files are part of the governance package:

- [LICENSE](LICENSE)
- [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md)
- [CONTRIBUTING.md](CONTRIBUTING.md)
- [SECURITY.md](SECURITY.md)
- [docs/privacy-policy.md](docs/privacy-policy.md)
- [docs/community-safety.md](docs/community-safety.md)
- [docs/dpga-audit-evidence.md](docs/dpga-audit-evidence.md)
