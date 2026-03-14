# Model Governance

## Purpose

This document explains how RetainAI’s predictive components should be reviewed, approved, monitored, and constrained in practice.

## Core Principle

A technically valid model is not automatically a deployable model.

RetainAI should only be used operationally when:

- the prediction target is clearly defined
- the data bundle has been validated
- retrospective performance is reviewed
- fairness is reviewed
- shadow mode is completed or explicitly waived with justification
- local staff understand the queue and workflow

## Model Lifecycle

### 1. Label definition

Each program chooses an operational label definition. This is part of governance, not a hidden technical default.

### 2. Training

Models are trained on program history and may use base-model assistance where configured.

### 3. Validation

Formal evaluation includes:

- temporal backtests
- calibration
- fairness review
- top-K capacity review

### 4. Shadow mode

Live queues are captured without relying on them as the operational source of truth, then reviewed against later outcomes.

### 5. Deployment approval

Only after validation and shadow-mode review should a program decide whether to use the queue for live decision support.

### 6. Monitoring

Post-deployment monitoring should include:

- drift review
- fairness review
- intervention effectiveness review
- operational override review

## Metrics That Matter

The most important metrics are not just AUC.

RetainAI should be judged by:

- precision at capacity
- recall at capacity
- calibration error
- subgroup disparity
- shadow-mode observed precision
- actioned-case outcomes

## Human Override

Model governance in RetainAI assumes:

- staff can dismiss flags
- staff can annotate flags
- staff can record verification outcomes
- these actions are part of the evidence trail

## Recommended Approval Questions

Before live use, program leadership should answer:

1. What is the model predicting exactly?
2. Is that target operationally meaningful?
3. Does the queue fit staff capacity?
4. What fairness concerns remain?
5. What is the intervention protocol after flagging?
6. What is the rollback path if the queue underperforms?

## Recommended Governance Roles

- M&E / data lead
- program operations lead
- safeguarding or privacy lead
- technical steward or engineer
- optional research or evaluation partner

## Current Limits

The current repository includes substantial evaluation and governance tooling, but it does not replace external review in high-stakes contexts.
