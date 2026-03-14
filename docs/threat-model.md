# Threat Model

## Purpose

This document summarizes the main security and misuse threats relevant to RetainAI deployments. It is not a substitute for a deployment-specific threat assessment, but it provides a baseline model for stewards and implementers.

## System Context

RetainAI processes operational beneficiary data, generates risk rankings, stores intervention actions, and may write tasks or status updates back into existing NGO systems. In many deployments, the data concerns vulnerable populations.

## Primary Assets

- beneficiary records
- attendance, visit, or payment histories
- free-text notes
- intervention logs
- model artifacts and evaluation reports
- connector credentials
- authentication secrets and session state
- audit logs

## Threat Actors

### External attacker

Could attempt to:

- gain access to beneficiary data
- steal credentials or sessions
- trigger unauthorized exports
- tamper with model or queue behavior

### Malicious insider or over-privileged user

Could attempt to:

- view data outside legitimate need
- export or share sensitive information
- misuse risk scores for exclusionary action
- alter intervention or audit trails

### Compromised upstream/downstream system

Could attempt to:

- send malformed or malicious connector payloads
- accept incorrect write-back tasks
- leak connector credentials or downstream case state

### Operational failure / misconfiguration

Could cause:

- wrong-region deployment
- unintended data sharing
- insecure storage or backup configuration
- broken queue behavior or stale scoring

## High-Risk Threat Scenarios

### 1. Unauthorized access to beneficiary data

Mitigations in repository:

- RBAC
- session controls
- JWT rotation support
- security headers and trusted-host controls
- audit logging

Remaining operator responsibility:

- secure deployment
- network policy
- secrets management
- access review

### 2. Export of sensitive data by authorized but inappropriate user

Mitigations in repository:

- export restrictions
- pseudonymized defaults
- audit trails
- governance surfaces

Remaining operator responsibility:

- user training
- least-privilege review
- internal policy enforcement

### 3. Misuse of risk scores to justify exclusion

Mitigations in repository:

- product framing around supportive follow-up
- governance alerts
- intervention-first workflow model
- consent and opt-out controls

Remaining operator responsibility:

- policy enforcement
- management oversight
- escalation for misuse incidents

### 4. Connector credential theft

Mitigations in repository:

- encrypted connector secret storage
- secret rotation support
- separate secret material for connector encryption

Remaining operator responsibility:

- secret-manager integration
- credential-scoping and periodic rotation

### 5. Model tampering or invalid deployment

Mitigations in repository:

- persisted model metadata
- evaluation reports
- shadow mode
- audit events

Remaining operator responsibility:

- release controls
- deployment approval
- artifact integrity and CI governance

### 6. Cross-border or wrong-region storage

Mitigations in repository:

- program-level policy settings
- residency-aware controls
- runtime policy visibility

Remaining operator responsibility:

- actual infra topology enforcement
- backup-region review
- vendor-region validation

## Sensitive Free-Text Risk

Field notes may contain:

- family conflict
- stigma
- health context
- migration intention
- legal or safety concerns

This means free-text handling is itself a threat surface. Deployers should minimize unstructured note exposure and export scope wherever possible.

## Threat Model Limitations

The repository is not yet a formally verified secure system and does not implement:

- secure enclave processing
- homomorphic protection
- mature secure aggregation for federated learning
- formal zero-trust deployment defaults

## Recommended Next Steps for Deployers

Before live deployment, conduct:

1. infrastructure threat review
2. secrets and key management review
3. access and role review
4. connector trust-boundary review
5. export and audit trail review
6. incident response tabletop exercise
