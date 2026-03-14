# Partner Data Request

This document is the concrete data request to send to a pilot NGO before a RetainAI shadow deployment.

## Goal

We need one historical beneficiary bundle that supports:

- temporal backtesting
- cohort and program-segment validation
- fairness auditing
- threshold tuning for field follow-up capacity

This is not the full production integration request. It is the minimum package required to decide whether the model is trustworthy enough for shadow mode.

## Minimum Bundle

Provide two tabular files, `.csv` or `.xlsx`.

### 1. Beneficiaries file

One row per beneficiary.

Required columns:

- `external_id`
- `name`
- `region`
- `enrollment_date`

Strongly recommended columns:

- `status`
- `dropout_date`
- `completion_date`
- `cohort`
- `phase`
- `gender`
- `household_type`
- `household_size`
- `pmt_score`
- `food_insecurity_index`
- `distance_to_service_km`
- `preferred_contact_phone`
- `preferred_contact_channel`
- `notes`
- `modeling_consent_status`
- `opted_out`

### 2. Events file

One row per beneficiary interaction, attendance event, payment collection, visit, or outreach attempt.

Required columns:

- `external_id`
- `event_date`
- `event_type`

Strongly recommended columns:

- `successful`
- `response_received`
- `source`
- `notes`

## Minimum History Threshold

For a meaningful first validation run, aim for:

- at least `500` beneficiaries
- at least `200` labeled dropouts
- at least `2` cohorts or waves
- at least `90` days of usable event history for most beneficiaries
- explicit dropout or completion dates where possible

If the bundle is smaller than this, RetainAI can still run the backtest, but the result should be treated as exploratory only.

## Preferred Export Scope

The best first bundle usually covers exactly one program in one country, not the whole organization.

Preferred scope:

- one program type
- one country team
- 12 to 24 months of history
- one consistent operational workflow

This keeps the first validation interpretable.

## Privacy Rules

Before transfer:

- remove direct identifiers not required for follow-up modeling
- do not include national ID numbers
- do not include exact home addresses
- do not include free-text notes that contain highly sensitive medical, legal, or protection details unless they are already approved for analytical use

If phone numbers are included, use a restricted-transfer channel and document why they are necessary. For backtesting only, phone numbers are usually not needed.

## Suggested System Exports

### KoboToolbox / ODK / CommCare

Export:

- enrollment form submissions
- follow-up form submissions
- attendance or visit form submissions

If possible, include a derived `status` column in the beneficiary export rather than forcing RetainAI to infer it from raw forms alone.

### DHIS2

Export:

- tracked entity roster
- enrollment dates
- program stage events
- completion / cancellation status

### Salesforce NPSP

Export:

- contacts or program participants
- program engagements
- attendance / service-delivery events
- closed-lost / completed equivalents

## Validation Workflow

Once the bundle is available:

1. Run `scripts/validate_partner_bundle.py`
2. Fix any schema or coverage issues
3. Run `scripts/run_partner_readiness_suite.py`
4. Review:
   - overall rolling backtest
   - per-program stability
   - per-cohort stability
   - fairness alerts

## Example Commands

```bash
python scripts/validate_partner_bundle.py ^
  --beneficiaries-file data/partner/beneficiaries.csv ^
  --events-file data/partner/events.csv ^
  --output-json data/partner/validation.json ^
  --output-md data/partner/validation.md
```

```bash
python scripts/run_partner_readiness_suite.py ^
  --beneficiaries-file data/partner/beneficiaries.csv ^
  --events-file data/partner/events.csv ^
  --program-name "Pilot Cash Transfer" ^
  --program-type "Cash Transfer" ^
  --country Kenya ^
  --output-json data/partner/readiness-suite.json ^
  --output-md data/partner/readiness-suite.md
```

## Decision Rule

Do not enable live decision-support use only because the overall backtest looks good.

The bundle is ready for shadow mode only if:

- the bundle validator does not report blocking errors
- the overall rolling backtest is at least `ready_for_shadow_mode`
- no major program or cohort segment collapses
- fairness alerts are reviewed and judged acceptable for the intended pilot
