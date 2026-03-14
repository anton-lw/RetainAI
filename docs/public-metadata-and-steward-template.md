# Public Metadata And Steward Template

This document exists to make final publication and DPGA submission cleanup
mechanical instead of ad hoc.

Do not submit RetainAI to the Digital Public Goods Alliance until every field
below has a real value and the linked files have been updated.

## Required Publication Values

Fill in the following values:

- `PUBLIC_REPOSITORY_URL`
- `PUBLIC_DOCUMENTATION_URL`
- `PUBLIC_ROADMAP_URL`
- `PUBLIC_ISSUE_TRACKER_URL`
- `PUBLIC_SECURITY_CONTACT`
- `PUBLIC_SUPPORT_CONTACT`
- `STEWARD_NAME`
- `STEWARD_TYPE`
  Examples: nonprofit, university lab, technical NGO, public-interest consortium
- `STEWARD_WEBSITE`
- `INITIAL_PUBLIC_RELEASE_TAG`

## Current Known Values

- `PUBLIC_REPOSITORY_URL`: `https://github.com/anton-lw/retainai`
- `PUBLIC_DOCUMENTATION_URL`: `https://github.com/anton-lw/retainai/tree/main/docs`
- `PUBLIC_ROADMAP_URL`: `https://github.com/anton-lw/retainai/blob/main/docs/roadmap.md`
- `PUBLIC_ISSUE_TRACKER_URL`: `https://github.com/anton-lw/retainai/issues`
- `PUBLIC_SECURITY_CONTACT`: `hello@antons.site`
- `PUBLIC_SUPPORT_CONTACT`: `hello@antons.site`
- `STEWARD_NAME`: `Anton Waagaard`
- `STEWARD_TYPE`: `individual interim steward`

Still to finalize if desired:

- `STEWARD_WEBSITE`
- `INITIAL_PUBLIC_RELEASE_TAG`

## Files To Update

### 1. Repository metadata

- [publiccode.yml](../publiccode.yml)

Update:

- `url`
- `landingURL`
- `roadmap`
- `documentation`
- any steward-facing descriptive text

### 2. Root repository landing page

- [README.md](../README.md)

Update:

- publication status section
- steward references
- any repository URL references

### 3. Governance and support

- [GOVERNANCE.md](../GOVERNANCE.md)
- [SUPPORT.md](../SUPPORT.md)
- [SECURITY.md](../SECURITY.md)
- [CODE_OF_CONDUCT.md](../CODE_OF_CONDUCT.md)

Update:

- named interim or permanent steward
- public support path
- public vulnerability disclosure path
- public conduct-reporting path if different from general support

### 4. DPGA submission evidence

- [dpga-audit-evidence.md](dpga-audit-evidence.md)
- [publication-and-dpga-submission-checklist.md](publication-and-dpga-submission-checklist.md)

Update:

- submission links
- steward references
- any remaining pre-publication caveats that are no longer true

## Minimum Steward Statement

Before publication, add a clear statement equivalent to:

`RetainAI is currently stewarded by <STEWARD_NAME>, which is responsible for repository maintenance, issue triage, release coordination, and security disclosure intake.`

Current steward statement:

`RetainAI is currently stewarded by Anton Waagaard, who is responsible for repository maintenance, issue triage, release coordination, and security disclosure intake.`

## Minimum Security Statement

Before publication, [SECURITY.md](../SECURITY.md) should contain:

- a monitored disclosure address or form
- expected acknowledgement timeline
- whether encrypted reporting is supported

## Minimum Support Statement

Before publication, [SUPPORT.md](../SUPPORT.md) should contain:

- the public issue tracker URL
- which categories belong in issues vs. security reporting
- whether community discussion happens elsewhere

## Final Check

Before release:

1. search the repository for `REPLACE_WITH_`
2. search the repository for `example.invalid`
3. search the repository for `current project maintainers` where a named steward should now exist
4. confirm all public links resolve
5. confirm the public issue tracker does not invite disclosure of sensitive beneficiary data or exploitable security details
