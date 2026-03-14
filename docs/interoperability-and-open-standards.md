# Interoperability and Open Standards

## Goal

RetainAI is intended to be portable, extractable, and interoperable with existing NGO and public-sector data ecosystems.

## Input and Output Formats

RetainAI supports or exposes:

- JSON over HTTP
- CSV import and export
- XLSX import
- PDF and XLSX donor reporting outputs
- REST-style API integrations

These are deliberately common, non-proprietary integration surfaces.

## Supported Source Systems

Current connector coverage targets:

- KoboToolbox
- CommCare
- ODK Central
- DHIS2
- Salesforce NPSP

RetainAI is designed to complement those systems rather than require their replacement.

## Open Standards and Common Protocols

The codebase currently uses or aligns with:

- HTTP and HTTPS
- JSON
- CSV
- OAuth 2.0 / OIDC concepts for SSO
- JWT for authenticated sessions
- Prometheus-style metrics
- Docker and OCI container workflows
- Kubernetes manifests
- Terraform infrastructure-as-code

## Data Export and Non-PII Extraction

The project supports non-PII data extraction through:

- pseudonymized risk exports
- pseudonymized intervention exports
- evaluation and validation reports
- synthetic data generation
- data structures that can be exported without direct identifiers

This is important for public-good interoperability, research collaboration, and low-risk system migration.

## Platform Independence

RetainAI is not tied to a single cloud vendor or runtime environment.

The repository supports:

- local development on commodity hardware
- self-hosted deployment
- Kubernetes deployment
- SQLite fallback for constrained environments
- PostgreSQL as the recommended production datastore

## Avoiding Vendor Lock-In

The project is intentionally structured so an adopting organization can:

- run the software on its own infrastructure
- inspect and modify source code
- export core operational data
- replace deployment tooling if required
- integrate with multiple upstream systems

## Current Interoperability Caveats

- some connectors are more mature than others
- deployment-specific write-back needs partner validation
- public API stability should still be versioned and governed carefully as the project matures

## Why This Matters for Digital Public Goods Review

This documentation exists to make clear that RetainAI is not a black-box hosted service requirement. It is designed as reusable infrastructure that organizations can adopt, host, audit, and extract from using open formats and common protocols.
