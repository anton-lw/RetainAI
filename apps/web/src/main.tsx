/**
 * Browser entrypoint for the React application.
 *
 * This file intentionally stays minimal: mount the root application, import the
 * global stylesheet, and keep startup behavior predictable for both standard
 * browser use and the PWA packaging path.
 */

import React from "react";
import ReactDOM from "react-dom/client";
import { registerSW } from "virtual:pwa-register";
import App from "./App";
import "./styles.css";

registerSW({ immediate: true });

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
