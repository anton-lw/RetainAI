# Privacy, Security, and Safeguards

## Scope

This document explains how RetainAI approaches privacy, data protection, safety, and misuse prevention at the product and deployment level.

It should be read alongside:

- [Privacy Policy](privacy-policy.md)
- [Security Policy](../SECURITY.md)
- [Community Safety](community-safety.md)

## Core Safeguard Principle

RetainAI is designed to support retention and re-engagement, not exclusion.

The system should not be used to:

- automatically remove beneficiaries
- justify denial of services
- rank people for punitive action
- expose vulnerable populations to external authorities without lawful basis

## Privacy by Design Features

Current repository features include:

- self-hosting support
- role-based access control
- server-tracked sessions
- audit logging
- tokenized beneficiary identifiers
- pseudonymized exports by default
- residency-aware export controls
- connector secret encryption
- consent tracking
- beneficiary opt-out from modeling
- explicit explanation and governance surfaces

## Sensitive Data Categories

Depending on deployment, RetainAI may process:

- names and external identifiers
- age or date-related enrollment information
- gender or household composition
- location and site data
- attendance or appointment history
- free-text field notes
- intervention history
- inferred risk categories
- consent and governance metadata

Some deployments may also involve special-category or high-risk data such as health status or information concerning children. Those deployments require heightened review.

## Access Control

The default role model includes:

- admin
- M&E officer
- field coordinator
- country director

The intent is least privilege:

- field users act on queue items
- governance controls stay with authorized staff
- exports and model governance are restricted

## Consent and Beneficiary Rights

RetainAI includes:

- consent state recording
- explanation-state recording
- opt-out flags for modeling
- beneficiary explanation sheets

Organizations deploying RetainAI remain responsible for:

- determining the lawful basis for processing
- ensuring consent processes are appropriate to the context
- explaining predictive support use to participants where required
- honoring local rights of access, correction, or deletion where applicable

## Data Residency and Cross-Border Controls

The product includes program-level policy settings for residency and cross-border restrictions. These controls are meaningful, but they are not by themselves a complete substitute for cloud-account and storage-topology enforcement.

Adopters should ensure that:

- infrastructure regions match policy settings
- storage, backups, and logs are reviewed for residency alignment
- data transfers are legally and operationally justified

## Misuse Prevention

RetainAI includes several misuse controls:

- audit trails for prediction views and exports
- governance alerts around harmful operational patterns
- pseudonymized export defaults
- role restrictions
- beneficiary opt-out and consent state tracking

Adopters should still monitor for:

- disenrollment after high-risk flagging without support attempts
- access by staff without legitimate need
- inappropriate export or sharing behavior
- use of the queue as a quality score on beneficiaries instead of a support signal

## Fairness and Bias

The ML layer includes:

- fairness-aware review thresholds
- group disparity summaries
- persisted bias audits
- validation reports that surface fairness findings

These features help identify risk. They do not eliminate bias. Final deployment decisions should include contextual review by program leadership and, where possible, independent evaluators.

## Security Controls in the Codebase

Implemented controls include:

- auth and session management
- throttling and revocation
- secret rotation support
- security headers
- trusted hosts and CORS controls
- audit logs
- encrypted connector secrets
- optional SSO

These controls still require correct environment configuration by the deployer.

## Data Lifecycle

Every deployment should define:

- which source systems feed RetainAI
- which fields are necessary
- how long raw data is retained
- how long model artifacts are retained
- whether shadow and evaluation reports are retained indefinitely
- how data deletion requests are handled

The codebase provides the structure for these workflows, but local policy remains essential.

## Safeguarding Recommendation

Any production deployment should complete:

- data-protection impact review
- legal review
- safeguarding review
- beneficiary communication review
- validation and shadow-mode review

RetainAI is a support system for serious programs. It should be deployed with the same discipline as other sensitive case-management infrastructure.
