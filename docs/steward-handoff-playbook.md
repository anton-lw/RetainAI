# Steward Handoff Playbook

This document is the operational handoff guide for any future steward,
maintainer institution, or public-interest host of the RetainAI project.

The repository is meant to be transferable. This playbook explains what that
means in practice.

## Purpose Of The Handoff

RetainAI is intended to be more than code published and forgotten. The desired
end state is:

- open-source code remains public
- governance and safety commitments remain visible
- a named steward owns maintenance and issue triage
- deploying organizations understand what the software can and cannot promise

## What A Steward Is Taking Responsibility For

A steward is not just inheriting a repository. A steward is inheriting:

- the technical codebase
- the public-good documentation package
- the safety and governance posture
- the credibility of the project's claims

That means stewardship includes both engineering and careful restraint.

## Minimum Steward Capabilities

A serious steward should be able to do all of the following:

### Technical maintenance

- review and merge code contributions
- run and interpret the backend and frontend test suite
- maintain dependencies and release artifacts
- operate or validate self-hosted deployments
- triage bugs in connectors, queue logic, and validation flows

### Governance maintenance

- review privacy- and safety-sensitive changes
- maintain public documentation
- handle vulnerability reports responsibly
- avoid overclaiming model readiness or real-world impact

### Community maintenance

- maintain a public issue tracker
- respond to deployer questions with reasonable consistency
- onboard contributors
- preserve open-source access and licensing continuity

## Handoff Package Checklist

Before a formal steward transfer, the following should be handed over
explicitly:

### Repository package

- full source repository
- license file
- contribution, support, security, and governance docs
- documentation hub
- deployment assets
- evaluation scripts
- synthetic/demo assets

### Operational context

- current maturity assessment
- known limitations and non-goals
- current dependency and warning issues
- known public benchmark results
- known partner-validation status

### Stewardship context

- intended user groups
- intended deployment sectors
- known candidate integration homes
- current publication or DPGA readiness status

## First 30 Days For A New Steward

The first month should focus on stabilization and understanding, not ambitious
feature expansion.

### Week 1

- read the root docs and code-reference docs
- run backend tests
- build the frontend
- review CI
- review security and governance docs

### Week 2

- run a local deployment
- inspect seeded/demo behavior
- run one public benchmark
- inspect one synthetic stress run

### Week 3

- review open issues and unresolved technical debt
- verify public metadata, support channels, and steward contact details
- assess release readiness and documentation completeness

### Week 4

- publish an initial steward update
- decide support expectations
- confirm release process and issue triage process

## Things A New Steward Should Not Do Immediately

- do not broaden product claims before validating them
- do not weaken governance and privacy controls for convenience
- do not remove evaluation steps to simplify deployment messaging
- do not treat public benchmark performance as field proof
- do not accept real beneficiary data into issue reports or public threads

## Priority Decision Areas For A Steward

The steward will need to make explicit decisions on:

### Product scope

- which program domain is the primary wedge
- which integrations matter most
- whether the dashboard or embedded operations gets priority

### Maintenance scope

- best-effort community support vs. formal service ownership
- issue-response expectations
- release cadence

### Evidence scope

- how the project describes readiness
- what validation is required before recommending live use
- what fairness and governance review is mandatory for deployments

## Recommended Stewardship Structure

The healthiest model is usually:

- one named technical maintainer
- one named governance/privacy reviewer
- one public issue tracker
- one public release stream
- one public support entrypoint

## Public Commitments A Steward Should Preserve

At minimum, a steward should preserve these public commitments:

- supportive retention use only
- no automated exclusion or disenrollment
- human-in-the-loop decision support
- transparent limitations
- open licensing
- public documentation
- explicit privacy and safety posture

## Documentation A Steward Should Keep Current

At minimum:

- [README.md](../README.md)
- [docs/README.md](README.md)
- [docs/project-overview.md](project-overview.md)
- [docs/api-endpoint-reference.md](api-endpoint-reference.md)
- [docs/privacy-and-safeguards.md](privacy-and-safeguards.md)
- [docs/model-governance.md](model-governance.md)
- [docs/dpga-audit-evidence.md](dpga-audit-evidence.md)
- [GOVERNANCE.md](../GOVERNANCE.md)
- [SECURITY.md](../SECURITY.md)
- [SUPPORT.md](../SUPPORT.md)

## Handoff Risk Areas

The most common failure modes in public-interest software handoffs are:

- code published without a named maintainer
- undocumented deployment assumptions
- no issue triage process
- no clarity on what is supported vs. merely present in the codebase
- loss of safety/governance context during technical transfer

This playbook exists to reduce those risks.

## Related Documents

- [Support](../SUPPORT.md)
- [Governance](../GOVERNANCE.md)
- [Release And Maintenance Playbook](release-and-maintenance-playbook.md)
- [Publication And DPGA Submission Checklist](publication-and-dpga-submission-checklist.md)
