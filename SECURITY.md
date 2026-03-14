# Security Policy

## Scope

This policy covers the RetainAI codebase, deployment artifacts, and documentation in this repository.

## Security Priorities

Because RetainAI may be deployed in sensitive humanitarian, health, education, or social-protection settings, the highest-priority classes of vulnerability are:

- unauthorized access to beneficiary data
- privilege escalation or role-bypass
- export paths that reveal PII or sensitive case notes
- connector credential leakage
- session hijacking or token forgery
- model or queue manipulation that could alter follow-up priorities
- audit-log tampering

## Reporting a Vulnerability

Do not disclose exploitable vulnerabilities publicly before maintainers have had a chance to assess and mitigate them.

If a private disclosure channel is available through the repository steward, use it. If not:

1. avoid posting exploit details in a public issue
2. notify the repository steward at `hello@antons.site`
3. include reproduction steps, affected files, and potential impact

The current security disclosure contact is Anton Waagaard
(`hello@antons.site`).

## What to Include

Please include:

- affected component or file
- deployment assumptions
- reproduction steps
- potential data or integrity impact
- whether a workaround exists

## Coordinated Disclosure

The project aims to follow coordinated disclosure:

- acknowledge receipt
- reproduce and triage
- scope impact
- prepare a fix
- document migration or mitigation steps
- disclose after mitigation is available where appropriate

## Secure Contribution Expectations

Contributors must not:

- commit real secrets
- commit real beneficiary data
- weaken authorization, tokenization, or audit behavior without documentation and tests
- disable safeguards to make local development easier without clearly scoping those changes to non-production paths

## Security Features Present in the Repository

The current codebase includes:

- JWT authentication with rotation support
- server-tracked sessions and logout revocation
- login throttling and session caps
- trusted-host and security-header controls
- role-based access control
- audit logging
- connector secret encryption
- PII tokenization support
- residency-aware export controls
- optional OIDC SSO

These controls still require deployment-specific configuration and review before production use.
