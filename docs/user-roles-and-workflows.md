# User Roles And Workflows

This guide describes the main user groups in RetainAI and the workflows each is
expected to perform.

It is useful for implementers planning training, permissions, and deployment
rollout.

## Role Model

Current roles in the product:

- `admin`
- `me_officer`
- `field_coordinator`
- `country_director`

The exact local policy for each role should be reviewed during deployment, but
the intended defaults are described below.

## Admin

Primary responsibilities:

- manage users and access indirectly through deployment configuration
- manage programs and high-privilege settings
- review operational health and queue infrastructure
- review audit and security-sensitive behavior

## M&E / MEAL Officer

Primary responsibilities:

- manage labels, windows, and validation settings
- review imports, connectors, and model status
- run backtests and shadow-mode workflows
- interpret fairness, drift, and evaluation outputs

## Field Coordinator

Primary responsibilities:

- work through the follow-up queue
- assign and attempt supportive outreach
- verify actual beneficiary status
- capture soft observations from the field

## Country Director

Primary responsibilities:

- review high-level retention trends and capacity implications
- inspect donor-oriented reports and governance posture
- understand whether the system is useful and safe

## Shared Workflow: Flag To Outcome

The most important cross-role workflow is:

1. a beneficiary appears in the queue
2. a user reviews the explanation
3. a follow-up action is selected
4. the action is logged
5. the beneficiary's status is verified
6. the case is closed, escalated, or dismissed

Different roles will touch different parts of that chain, but the chain should
be understandable to all of them.

## Training Implications

### Admin onboarding

Should cover:

- deployment assumptions
- audit and runtime health
- privacy-sensitive settings

### M&E onboarding

Should cover:

- labels and validation
- fairness and readiness interpretation
- connector and import workflows

### Field onboarding

Should cover:

- what a risk flag means
- what it does not mean
- how to log actions
- how to dismiss or annotate cases
- how to verify outcomes

### Leadership onboarding

Should cover:

- what can be concluded from dashboard and donor reports
- what still requires local validation and judgment

## Permission Design Notes

The safest deployment posture is:

- field staff can act on cases but not reconfigure model or privacy policy
- M&E staff can manage validation and operational settings
- governance and export-sensitive actions remain restricted
- admin retains the narrowest set of high-impact controls

## Related Documents

- [Implementation Guide](implementation-guide.md)
- [Workflow Reference](workflow-reference.md)
- [Privacy And Safeguards](privacy-and-safeguards.md)
