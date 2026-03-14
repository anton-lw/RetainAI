# Implementation Guide

## Purpose

This guide is for organizations preparing a first real RetainAI deployment.

## Recommended First Deployment Profile

The strongest first deployment candidate is a program that has:

- repeated beneficiary interactions
- stable identifiers
- at least several months of history
- a clear operational notion of missed engagement
- staff who already perform reactive follow-up

## Step 1: Define the Program Scope

Clarify:

- program type
- geographic scope
- source systems
- users and roles
- follow-up channels
- what operational event counts as disengagement

## Step 2: Prepare the Data Bundle

Use:

- [partner-data-request.md](partner-data-request.md)

Then run:

- `scripts/validate_partner_bundle.py`

## Step 3: Load and Inspect

Before training:

- inspect field mapping
- review anomaly flags
- review missingness
- confirm that key identifiers and dates are correct

## Step 4: Configure Program Settings

Review:

- label-definition preset
- inactivity threshold
- prediction window
- weekly follow-up capacity
- worker count
- default support channels
- escalation window

## Step 5: Run Validation

Run:

- retrospective backtest
- partner readiness suite
- cross-segment validation if possible

Review:

- precision and recall at capacity
- fairness findings
- calibration
- sample sufficiency

## Step 6: Enable Shadow Mode

Shadow mode is strongly recommended before operational reliance. Capture queue snapshots, then review observed precision and recall once outcomes mature.

## Step 7: Train Staff

Staff should understand:

- what the queue is and is not
- how to act on a case
- how to dismiss or annotate
- how to verify outcomes
- how to escalate concerns

## Step 8: Go-Live Decision

Go live only if:

- validation is acceptable
- fairness concerns are understood
- operational workflow is ready
- privacy and safeguarding review is complete

## Step 9: Ongoing Review

After go-live:

- monitor drift
- review overrides
- review intervention effectiveness
- reassess thresholds as staffing changes
