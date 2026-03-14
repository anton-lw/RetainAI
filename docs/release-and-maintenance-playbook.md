# Release And Maintenance Playbook

This document describes how RetainAI should be maintained and released as an
open-source public-good project.

It is written for future stewards and maintainers rather than end users.

## Maintenance Philosophy

RetainAI should be maintained conservatively.

Because the software influences how field teams prioritize supportive follow-up,
the safest maintenance posture is:

- clear changes
- visible tradeoffs
- test-backed updates
- documentation kept in sync
- careful claims about readiness

## Release Types

The project should use at least three practical release categories.

### 1. Patch release

Use for:

- bug fixes
- documentation corrections
- small non-breaking UI improvements
- dependency updates with low behavioral risk

### 2. Minor release

Use for:

- new endpoints
- new UI sections
- additive schemas
- new integration options
- new evaluation outputs

### 3. High-risk or governance-sensitive release

Use for changes affecting:

- privacy
- consent
- exports
- authentication
- queue ranking
- label definitions
- model thresholds
- fairness methodology
- write-back behavior

These releases should receive a stronger review bar and explicit release notes.

## Recommended Release Checklist

Before release, a maintainer should confirm:

### Code quality

- backend tests pass
- frontend build passes
- Playwright tests pass
- relevant local sanity checks pass

### Schema and deployment

- Alembic upgrade path is valid
- deployment docs still match the code
- infra changes have been reviewed if touched

### Product behavior

- affected workflows were manually sanity-checked
- evaluation or queue-impacting changes were reviewed against validation tooling
- privacy/export behavior was reviewed if touched

### Documentation

- README updated if behavior or setup changed
- docs hub updated if new docs were added
- relevant API, workflow, or governance docs updated

## Suggested Release Process

### Step 1: prepare release scope

- collect merged changes
- identify whether any are high-risk
- draft release notes

### Step 2: validate

- run the standard engineering checks
- run at least one evaluation or benchmark regression if model or queue logic
  changed
- run deployment smoke checks when release scope touched packaging or infra

### Step 3: review public claims

Before publishing notes, check that the release description does not imply:

- universal production readiness
- universal sector validity
- real-world impact proof where only backtests exist

### Step 4: publish

- tag release
- publish release notes
- update any public release-tracking doc if one exists

## Maintenance Cadence

A realistic public-good maintenance rhythm is:

- ongoing issue triage
- small patch releases as needed
- bundled minor releases at a predictable cadence
- immediate security releases when required

## Issue Triage Categories

Every issue should be triaged into one of these broad buckets:

- security and privacy
- data integrity
- operational workflow
- evaluation and ML
- documentation and onboarding

## Maintainer Checklists

### Weekly

- review new issues
- review dependency alerts
- review CI failures
- check whether docs drifted behind code changes

### Monthly

- review open bug backlog
- review unresolved governance or safety questions
- review whether release notes are needed
- review benchmark or validation tooling health

### Quarterly

- reassess roadmap and scope
- review public claims and documentation freshness
- review whether steward contact and support channels are still accurate
- review DPGA submission posture if applicable

## High-Risk Change Review Checklist

For changes touching sensitive behavior, explicitly review:

- what new data is exposed or stored?
- who can trigger this path?
- does it alter queue ranking or intervention recommendation behavior?
- does it change audit coverage?
- does it require user-facing documentation updates?
- does it require validation reruns?

## Related Documents

- [Testing And Quality Reference](testing-and-quality-reference.md)
- [Migrations And Schema Evolution](migrations-and-schema-evolution.md)
- [Steward Handoff Playbook](steward-handoff-playbook.md)
