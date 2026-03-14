# Data Governance and Retention

## Purpose

This document describes how adopters should think about data minimization, retention, deletion, and governance when deploying RetainAI.

## Data Minimization

RetainAI is intentionally designed to work with a narrow core feature set. Organizations should only ingest the minimum data required for retention operations.

Strong defaults:

- use operational identifiers, not more identifiers than necessary
- avoid collecting broad survey fields unless they are actually used
- minimize free text when structured fields suffice
- prefer pseudonymized exports for analysis and coordination

## Core Data Categories

### Usually necessary

- program and beneficiary identifiers
- enrollment date
- region/site
- visit or attendance history
- intervention history

### Sometimes necessary

- household composition
- PMT or vulnerability proxy
- contact channel preference
- field-note text

### High-sensitivity / context-dependent

- health-related notes
- child-related case context
- stigma or protection concerns
- migration or displacement status

These should be reviewed carefully before ingestion.

## Retention Schedule Template

Each deployment should explicitly set:

- raw import retention period
- operational record retention period
- audit log retention period
- evaluation report retention period
- model artifact retention period
- backup retention period

The codebase supports these workflows conceptually, but the actual schedule is an operator decision.

## Deletion and Archiving

Adopters should define:

- when records are archived
- when records are deleted
- whether deletion is logical or physical
- how deletions affect evaluation and audit records
- whether model artifacts are retrained after deletions when legally required

## Data Ownership and Stewardship

The deploying organization is generally the data controller or equivalent accountable entity for operational data. Stewards of the open-source repository are not automatically the operator of any deployment.

## Recommended Governance Questions

Before deployment, answer:

1. What exact data fields are being imported?
2. Why is each field necessary?
3. Which roles can access each field category?
4. Which exports include direct identifiers?
5. How long is each category retained?
6. What is the deletion process?
7. How are beneficiaries informed?

## Group Data Risks

Even where direct identifiers are removed, small-group or location-level information can still create risk. This is particularly relevant for:

- low-population sites
- stigmatized conditions
- minority groups
- conflict-affected settings

Pseudonymization is not the same as zero risk.

## Recommended Governance Artifacts Per Deployment

- a local data inventory
- a retention schedule
- an access control matrix
- a DPIA or equivalent review where appropriate
- an incident response contact list
- a model approval record
