/**
 * Lightweight application state shell for loading and fatal-error states.
 *
 * The app uses this component before full data bootstrap completes or when the
 * dashboard cannot render a useful working surface due to an unrecoverable
 * error.
 */

import type { ReactNode } from "react";

interface StatusScreenProps {
  eyebrow: string;
  title: string;
  message: string;
  children?: ReactNode;
}

function StatusScreen({ eyebrow, title, message, children }: StatusScreenProps) {
  return (
    <div className="loading-shell">
      <div className="loading-card">
        <span className="eyebrow">{eyebrow}</span>
        <h1>{title}</h1>
        <p>{message}</p>
        {children}
      </div>
    </div>
  );
}

export default StatusScreen;
