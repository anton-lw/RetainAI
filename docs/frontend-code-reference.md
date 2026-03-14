# Frontend Code Reference

This document explains how the React + TypeScript web client is structured,
which files own which responsibilities, and how the frontend maps onto backend
workflows.

## Frontend Topology

```text
apps/web/src/
|- App.tsx                         Main orchestration shell
|- api.ts                          Typed HTTP client helpers
|- types.ts                        Shared UI-side contract models
|- main.tsx                        Browser entrypoint
|- MobileLiteView.tsx              Constrained field-facing workflow view
|- RetentionChart.tsx              Analytics visualization component
`- components/
   |- AuthScreen.tsx               Login and SSO entry screen
   |- StatusScreen.tsx             Loading / fatal error shell
   |- RiskQueueSection.tsx         Core tracing queue workflow
   |- OperationsSection.tsx        Program settings and capacity controls
   |- ConnectorAutomationSection.tsx Connector and sync administration
   |- GovernanceSection.tsx        Consent / export / safeguard controls
   |- ValidationSection.tsx        Backtest and shadow-mode controls
   `- AnalyticsOverview.tsx        Supervisory analytics and reporting
```

## Core Frontend Responsibilities

The frontend is intentionally thin in domain logic. It should:

- render operational state clearly
- hold transient UI state and form state
- call backend endpoints through `api.ts`
- present model results and governance controls without re-implementing backend
  business rules

The frontend should not:

- define its own dropout logic
- compute model scores
- bypass backend privacy rules in export behavior
- duplicate backend validation beyond basic form safety

## Main Modules

### `App.tsx`

`App.tsx` remains the orchestration shell.

It owns:

- auth bootstrap from local storage and the backend session
- top-level app-data loading
- cross-section form state
- error and loading state coordination
- handler wiring into extracted section components

It is still larger than ideal, but it is increasingly a coordination file rather
than a monolithic render-only file.

When changing `App.tsx`, ask:

- should this state live in a more focused section component?
- should this be a typed helper in `api.ts` instead of inline fetch logic?
- is this a cross-section concern or a section-local concern?

### `api.ts`

This file is the single HTTP client surface for the UI.

It owns:

- access-token storage and retrieval
- request header attachment
- parsing backend errors into `ApiError`
- all route-specific request functions
- bootstrap aggregation through `loadAppData`

When backend contracts change, update this file and `types.ts` first. Let the
rest of the UI consume those typed helpers.

### `types.ts`

This file mirrors the backend schema layer.

It should stay:

- explicit
- boring
- close to the backend response shape

Avoid adding purely speculative UI-only domain models unless they genuinely
reduce complexity. The current strategy is to keep the contract obvious.

### `main.tsx`

This is intentionally minimal and should remain that way.

### `MobileLiteView.tsx`

This is the field-oriented, reduced-friction view for smaller screens and more
constrained operational use. It should prioritize:

- fast scanning
- clear explanations
- minimal configuration overhead

It is not intended to expose every supervisory control present in the full web
dashboard.

## Section Components

### `components/RiskQueueSection.tsx`

This is the operational heart of the frontend.

It owns:

- risk-case listing and filters
- follow-up export entry points
- workflow editing for action, dismissal, verification, and closure
- display of plain-language reasons and support-channel choices

If the product's core loop is "flag -> action -> verification -> outcome," this
component is the main UI surface for that loop.

### `components/OperationsSection.tsx`

This section manages program-level operational controls such as:

- label-definition presets
- worker/site capacity settings
- escalation thresholds
- channel defaults

It is administrative but operationally important because these settings shape
how the queue behaves.

### `components/ConnectorAutomationSection.tsx`

This section is for operators managing data integration and write-back flows.

It exposes:

- connector creation
- preview and sync actions
- dispatch/write-back actions
- connector run history

### `components/GovernanceSection.tsx`

This is where privacy and beneficiary-rights controls become usable in the UI.

It includes:

- beneficiary governance records
- opt-out and consent-adjacent actions
- explanation retrieval
- safeguard alert display
- export controls

### `components/ValidationSection.tsx`

This section makes the evaluation harness visible to product users and
maintainers, not just script users.

It owns:

- backtest parameter inputs
- program validation settings
- evaluation history display
- shadow-mode run display

### `components/AnalyticsOverview.tsx`

This section packages higher-level analytics for supervisors and donor-facing
users:

- retention curves
- donor report summaries
- intervention-effectiveness views
- model status summaries

### `components/AuthScreen.tsx` and `StatusScreen.tsx`

These are intentionally simple presentation shells:

- `AuthScreen.tsx` focuses on login and SSO entry
- `StatusScreen.tsx` focuses on loading and fatal-state messaging

## Data Flow In The Frontend

### 1. App bootstrap

1. `main.tsx` mounts `App.tsx`
2. `App.tsx` loads any persisted token
3. `App.tsx` calls `fetchCurrentUser` or `loadAppData`
4. typed responses flow through `types.ts`
5. extracted components render their sections

### 2. User action flow

1. section component triggers handler passed from `App.tsx`
2. handler calls an `api.ts` function
3. backend responds with updated records or triggers refresh
4. `App.tsx` updates state and passes fresh props back down

### 3. Validation flow

1. user configures evaluation or shadow settings in `ValidationSection.tsx`
2. `App.tsx` calls the relevant `api.ts` helper
3. backend persists evaluation/shadow records
4. refreshed records appear in the section

## Frontend Design Constraints

The frontend is not just a generic admin app. The code should continue to
respect the project's product assumptions:

- risk flags are decision support, not automated decisions
- sensitive governance controls must remain role-aware
- mobile-lite flow matters because many field settings are device-constrained
- explanations should stay understandable by operational users with varying
  technical literacy

## Frontend Testing Surfaces

Primary UI verification:

- `npm --prefix apps/web run build`
- Playwright tests in `apps/web/e2e/`

The Playwright layer is currently narrow but important because it validates that
high-value flows still work in a browser:

- login
- queue filtering
- mobile-lite explanation flow
- validation section behavior

## Refactor Priorities For Future Stewards

The most obvious future maintainability work remains:

- continue shrinking `App.tsx`
- move section-local form state closer to each section when cross-section
  coordination is no longer needed
- add more component-level tests around governance and operations settings
- keep `api.ts` authoritative instead of scattering fetch logic

## Related Documents

- [Codebase Reference](codebase-reference.md)
- [Backend Code Reference](backend-code-reference.md)
- [Workflow Reference](workflow-reference.md)
- [Implementation Guide](implementation-guide.md)
