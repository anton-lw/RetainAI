# Publication And DPGA Submission Checklist

This document is a practical publication checklist for taking RetainAI from a
private or development-stage repository to a publicly reviewable digital public
good candidate.

It complements [dpga-audit-evidence.md](dpga-audit-evidence.md). The evidence
matrix explains how the repository aligns to the standard; this checklist
explains what still needs to be true at publication time.

## Repository Publication Checklist

Before publishing the repository publicly, confirm:

### Core repository materials

- [LICENSE](../LICENSE) is present and correct
- [README.md](../README.md) is current
- [GOVERNANCE.md](../GOVERNANCE.md) is current
- [CONTRIBUTING.md](../CONTRIBUTING.md) is current
- [CODE_OF_CONDUCT.md](../CODE_OF_CONDUCT.md) is current
- [SECURITY.md](../SECURITY.md) is current
- [SUPPORT.md](../SUPPORT.md) is current

### Documentation hub

- [docs/README.md](README.md) links all major docs
- project overview and architecture docs are current
- privacy, governance, and safety docs are current
- API docs and workflow docs reflect the current code

### Public metadata

- `publiccode.yml` contains real steward URLs and metadata
- placeholder organization names are replaced in all repository metadata files
- repository description and topics are accurate
- issue templates or issue guidance exist if needed

### Sensitive-data review

- no real beneficiary data is committed
- no secrets or credential material is committed
- no sample files contain real PII

## Minimum Public-Facing Metadata

At publication time, the project should have:

- a real repository URL
- a named steward or interim maintainer
- a support or issue-reporting entrypoint
- a public statement of non-goals and limitations
- a public security disclosure route

## DPGA-Oriented Checklist

Before submitting to the Digital Public Goods Alliance, verify:

### Licensing and openness

- open-source license is OSI-approved
- code is publicly accessible
- documentation is publicly accessible

### Ownership and stewardship

- steward or interim owner is named
- contribution pathway is documented
- support pathway is documented

### Privacy and do-no-harm

- privacy and safeguard docs are public
- harmful-use constraints are documented
- community safety materials are public
- export and PII handling are described clearly

### Documentation completeness

- setup docs exist
- architecture docs exist
- interoperability docs exist
- API docs exist
- user or implementer guidance exists

### Open standards and interoperability

- connectors and supported integrations are documented
- API structure is documented
- deployment assumptions are documented

## Recommended Publication Sequence

1. finish documentation cleanup
2. replace placeholder metadata
3. run release validation
4. confirm issue templates, support docs, and security docs reflect real contacts
5. publish repository
6. verify public links and docs render correctly
7. submit to DPGA

## Known Publication Risks

Publishing too early often creates these problems:

- broken setup claims
- undocumented support expectations
- public issue tracker receiving sensitive data
- unclear steward ownership
- stale privacy language

## Suggested Final Public Review

Right before publication, one maintainer should do a line-by-line check of:

- root README
- docs hub
- support and security docs
- public metadata files
- any placeholders or `example.invalid` values

## Related Documents

- [DPGA Audit Evidence Matrix](dpga-audit-evidence.md)
- [Steward Handoff Playbook](steward-handoff-playbook.md)
- [Release And Maintenance Playbook](release-and-maintenance-playbook.md)
- [Public Metadata And Steward Template](public-metadata-and-steward-template.md)
