# DPGA Audit Evidence Matrix

This document maps RetainAI to the current Digital Public Goods Standard indicators described by the Digital Public Goods Alliance.

Reference standard:

- [DPG Standard](https://new.digitalpublicgoods.net/standard)

## Scope Note

This matrix is a documentation and evidence map. It does not claim that submission is automatically approved. A formal DPGA review will still require a public repository, public metadata, and steward-confirmed submission details.

## Current Readiness Summary

RetainAI is substantively close to DPGA submission readiness, but the following
publication requirements remain outside the repository's local-only state:

- final public release tag or release artifact
- optional project website or demo link if one will be included in the submission

Those final values are tracked in
[public-metadata-and-steward-template.md](public-metadata-and-steward-template.md).

## Indicator 1: Relevance to Sustainable Development Goals

### Evidence

RetainAI is directly relevant to program effectiveness in health, education, and social protection workflows. It supports improved retention, supportive follow-up, and better use of scarce delivery resources.

Relevant repository evidence:

- [README.md](../README.md)
- [project-overview.md](project-overview.md)

### Notes

Likely SDG relevance includes:

- SDG 3
- SDG 4
- SDG 5 where inclusive follow-up matters
- SDG 10
- SDG 16 through stronger accountability and governance

## Indicator 2: Use of an Approved Open License

### Evidence

- [LICENSE](../LICENSE)

### Status

Satisfied in-repo through the MIT License.

## Indicator 3: Clear Ownership

### Evidence

- [GOVERNANCE.md](../GOVERNANCE.md)

### Status

Ownership, contribution licensing, and intended steward-transfer model are documented.

## Indicator 4: Platform Independence

### Evidence

- [README.md](../README.md)
- [architecture.md](architecture.md)
- [deployment-and-operations.md](deployment-and-operations.md)
- [interoperability-and-open-standards.md](interoperability-and-open-standards.md)

### Status

RetainAI supports self-hosting, local development, cloud deployment scaffolding, and portable data formats.

## Indicator 5: Best Practices and Open Standards

### Evidence

- [interoperability-and-open-standards.md](interoperability-and-open-standards.md)
- [architecture.md](architecture.md)

### Status

The project uses common protocols and open formats including HTTP, JSON, CSV, XLSX, JWT/OIDC patterns, Prometheus-style metrics, Docker, Kubernetes, and Terraform.

## Indicator 6: Documentation of Source Code

### Evidence

- [README.md](../README.md)
- [docs/README.md](README.md)
- [architecture.md](architecture.md)
- [data-and-ml.md](data-and-ml.md)
- [deployment-and-operations.md](deployment-and-operations.md)
- [CONTRIBUTING.md](../CONTRIBUTING.md)

### Status

The repository includes product, architecture, operational, validation, governance, and contributor documentation.

## Indicator 7: Mechanism for Extracting Non-PII Data

### Evidence

- [interoperability-and-open-standards.md](interoperability-and-open-standards.md)
- [privacy-and-safeguards.md](privacy-and-safeguards.md)
- [privacy-policy.md](privacy-policy.md)

### Status

The system supports pseudonymized exports, structured reports, and synthetic data generation for low-risk extraction and interoperability.

## Indicator 8: Adherence to Privacy Laws and Other Applicable Laws

### Evidence

- [privacy-policy.md](privacy-policy.md)
- [privacy-and-safeguards.md](privacy-and-safeguards.md)
- [SECURITY.md](../SECURITY.md)

### Status

The repository documents privacy and safeguard controls and explicitly states that deployers remain responsible for local legal compliance, lawful basis, and operational review.

## Indicator 9A: Do No Harm by Design

### Evidence

- [project-overview.md](project-overview.md)
- [privacy-and-safeguards.md](privacy-and-safeguards.md)
- [community-safety.md](community-safety.md)

### Status

RetainAI explicitly forbids exclusionary or punitive use, includes consent and opt-out controls, and documents misuse-prevention expectations.

## Indicator 9B: Protection from Inappropriate and Illegal Content

### Evidence

- [community-safety.md](community-safety.md)
- [CODE_OF_CONDUCT.md](../CODE_OF_CONDUCT.md)

### Status

The repository documents prohibited content categories, handling expectations, and reporting principles for both contributor spaces and product use contexts.

## Indicator 9C: Protection from Harassment

### Evidence

- [CODE_OF_CONDUCT.md](../CODE_OF_CONDUCT.md)
- [community-safety.md](community-safety.md)

### Status

Contributor and product-safety expectations are documented with clear prohibitions on harassment, intimidation, and abusive behavior.

## Recommended Submission Attachments

When preparing a formal DPGA submission, include:

- repository URL
- public release or tag
- project website or public home page if available
- steward/owner contact
- public issue tracker
- public deployment or demo link if appropriate
- this evidence matrix
- completed [Public Metadata And Steward Template](public-metadata-and-steward-template.md)

## Current Documentation Gap Outside the Repository

For an actual submission, the following still need to exist in public form, not just local files:

- public tagged release or equivalent release reference
- any optional website or demo link referenced in the submission

The repository now contains the documentation required to support those assets once published.
