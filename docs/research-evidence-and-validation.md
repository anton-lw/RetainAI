# Research, Evidence, and Validation

## Purpose

RetainAI is not only a software platform. It also makes causal and operational claims that must be evaluated honestly. This document explains how evidence should be interpreted.

## What the Repository Can Prove

The repository can prove:

- the software workflow exists
- evaluation and shadow-mode tooling exist
- models can be trained and scored
- fairness and calibration can be measured

## What the Repository Cannot Prove Alone

The repository cannot prove:

- universal model validity across countries or sectors
- real-world operational effectiveness in a given NGO
- causal reduction in dropout or disengagement without field evidence

## Evidence Tiers

### Tier 1: Software correctness

- tests
- builds
- migrations
- smoke checks

### Tier 2: Retrospective predictive validity

- temporal backtests
- cross-segment validation
- fairness review

### Tier 3: Prospective operational validity

- shadow mode
- observed precision at capacity
- intervention logging quality

### Tier 4: Causal effectiveness

- controlled rollouts
- quasi-experimental evaluation
- RCT-style intervention evidence

## Recommended Evidence Path

1. partner bundle validation
2. retrospective backtests
3. fairness review
4. shadow mode
5. operational pilot
6. causal evaluation if the deployment is material enough

## Public and Synthetic Data

Public benchmarks and synthetic data are useful for:

- regression testing
- benchmark comparison
- stress testing
- documentation and demos

They are not substitutes for real partner-data evaluation.

## Reporting Standard

Any steward or deployer describing RetainAI performance should clearly distinguish:

- public benchmark results
- synthetic stress results
- partner retrospective results
- shadow-mode results
- live operational outcomes

These should never be conflated.
