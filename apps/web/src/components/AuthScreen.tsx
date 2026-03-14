/**
 * Authentication screen for password and optional SSO login.
 *
 * The component stays deliberately presentational: it renders the form and
 * delegates all behavioral logic to handlers passed in from `App.tsx`.
 */

import type { FormEvent } from "react";

interface AuthScreenProps {
  error: string | null;
  effectiveSsoConfig: {
    enabled: boolean;
    interactive: boolean;
    mode: string;
    provider_label?: string | null;
  } | null;
  loginForm: {
    email: string;
    password: string;
  };
  isAuthenticating: boolean;
  isStartingSso: boolean;
  showDevelopmentAccounts: boolean;
  developmentAccounts: string[];
  onEmailChange: (value: string) => void;
  onPasswordChange: (value: string) => void;
  onSubmit: (event: FormEvent<HTMLFormElement>) => void;
  onStartSso: () => void;
}

function AuthScreen({
  error,
  effectiveSsoConfig,
  loginForm,
  isAuthenticating,
  isStartingSso,
  showDevelopmentAccounts,
  developmentAccounts,
  onEmailChange,
  onPasswordChange,
  onSubmit,
  onStartSso,
}: AuthScreenProps) {
  return (
    <div className="loading-shell">
      <div className="loading-card login-card">
        <span className="eyebrow">Secure Retention Operations</span>
        <h1>Sign in to RetainAI</h1>
        <p>Role-based access control, audit logging, and deployment policy checks are now enforced across the workspace.</p>
        {error ? <div className="callout error-callout">{error}</div> : null}
        {effectiveSsoConfig?.enabled ? (
          <div className="flag-row">
            <span className="flag-chip">
              {effectiveSsoConfig.provider_label ?? "SSO"} {effectiveSsoConfig.mode === "oidc" ? "OIDC" : "gateway"}
            </span>
          </div>
        ) : null}

        <form className="stacked-form" onSubmit={onSubmit}>
          <input
            type="email"
            aria-label="Email"
            placeholder="Email"
            value={loginForm.email}
            onChange={(event) => onEmailChange(event.target.value)}
            required
          />
          <input
            type="password"
            aria-label="Password"
            placeholder="Password"
            value={loginForm.password}
            onChange={(event) => onPasswordChange(event.target.value)}
            required
          />
          <button className="primary-button" type="submit" disabled={isAuthenticating}>
            {isAuthenticating ? "Signing in..." : "Sign in"}
          </button>
        </form>
        {effectiveSsoConfig?.interactive ? (
          <button className="secondary-button" type="button" onClick={onStartSso} disabled={isStartingSso}>
            {isStartingSso
              ? `Starting ${effectiveSsoConfig.provider_label ?? "SSO"}...`
              : `Continue with ${effectiveSsoConfig.provider_label ?? "SSO"}`}
          </button>
        ) : null}
        {effectiveSsoConfig?.enabled && !effectiveSsoConfig.interactive ? (
          <p className="helper-copy">
            Single sign-on is enabled through the deployment gateway. If your organization uses gateway-authenticated access, open RetainAI through that managed entrypoint.
          </p>
        ) : null}

        {showDevelopmentAccounts ? (
          <>
            <p className="helper-copy">
              Development seed accounts use the shared API password `retainai-demo` unless it was overridden in the backend environment.
            </p>
            <div className="flag-row">
              {developmentAccounts.map((account) => (
                <span className="flag-chip" key={account}>
                  {account}
                </span>
              ))}
            </div>
          </>
        ) : null}
      </div>
    </div>
  );
}

export default AuthScreen;
