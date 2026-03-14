import type { Page, Route } from "@playwright/test";

const NOW = "2026-03-10T10:15:00Z";
const CURRENT_USER = {
  id: "user-admin",
  full_name: "Amina Program Lead",
  email: "admin@retainai.local",
  role: "admin",
  is_active: true,
  last_login_at: NOW,
  created_at: "2026-01-01T08:00:00Z",
};

const PROGRAM = {
  id: "program-1",
  name: "Northern Cash Transfer",
  program_type: "Cash Transfer",
  country: "Kenya",
  delivery_modality: "mobile_money",
  status: "active",
  created_at: "2026-01-02T08:00:00Z",
};

const RISK_CASES = [
  {
    id: "case-1",
    name: "Amina Noor",
    program: "Northern Cash Transfer",
    program_type: "Cash Transfer",
    region: "Northern Region",
    cohort: "2026-A",
    phase: "Enrollment",
    risk_level: "High",
    risk_score: 92,
    explanation: "Amina missed 2 of the last 3 check-ins and reported transport barriers.",
    recommended_action: "Call within 48 hours and schedule a field visit if unreachable.",
    flags: ["Missed 2 recent check-ins", "Transport barrier"],
    last_contact_days: 17,
    attendance_rate_30d: 34,
    intervention_status: "No outreach logged",
    confidence: "High confidence",
    opted_out: false,
    assigned_worker: "Northern queue 1",
    assigned_site: "Northern Region Site 1",
    queue_rank: 1,
    queue_bucket: "Due now",
    workflow: null,
    tracing_protocol: {
      current_step: "visit",
      current_channel: "visit",
      current_due_at: "2026-03-13T10:15:00Z",
      next_step: null,
      next_due_at: null,
      sms_delay_days: 3,
      call_delay_days: 7,
      visit_delay_days: 14,
    },
    soft_signals: {
      household_stability_signal: 2,
      economic_stress_signal: 4,
      family_support_signal: 2,
      health_change_signal: null,
      motivation_signal: 3,
    },
  },
  {
    id: "case-2",
    name: "David Ochieng",
    program: "Northern Cash Transfer",
    program_type: "Cash Transfer",
    region: "Coastal Region",
    cohort: "2026-B",
    phase: "Follow-up",
    risk_level: "Medium",
    risk_score: 61,
    explanation: "David has a declining attendance trend after a recent household shock.",
    recommended_action: "Queue for follow-up call this week.",
    flags: ["Declining attendance"],
    last_contact_days: 9,
    attendance_rate_30d: 62,
    intervention_status: "Queued",
    confidence: "High confidence",
    opted_out: false,
    assigned_worker: "Coastal queue 1",
    assigned_site: "Coastal Region Site 1",
    queue_rank: 2,
    queue_bucket: "This week",
    workflow: {
      intervention_id: "intervention-1",
      status: "queued",
      verification_status: "pending",
      assigned_to: "Coastal queue 1",
      assigned_site: "Coastal Region Site 1",
      due_at: "2026-03-14T09:00:00Z",
      completed_at: null,
      verified_at: null,
      note: "Queued from existing workflow.",
      verification_note: null,
      dismissal_reason: null,
      support_channel: "call",
      protocol_step: "call",
      attempt_count: 0,
      successful: null,
      tracing_protocol: {
        current_step: "call",
        current_channel: "call",
        current_due_at: "2026-03-14T09:00:00Z",
        next_step: "visit",
        next_due_at: "2026-03-17T10:15:00Z",
        sms_delay_days: 3,
        call_delay_days: 7,
        visit_delay_days: 14,
      },
    },
    tracing_protocol: {
      current_step: "call",
      current_channel: "call",
      current_due_at: "2026-03-14T09:00:00Z",
      next_step: "visit",
      next_due_at: "2026-03-17T10:15:00Z",
      sms_delay_days: 3,
      call_delay_days: 7,
      visit_delay_days: 14,
    },
    soft_signals: {
      household_stability_signal: 3,
      economic_stress_signal: 3,
      family_support_signal: 4,
      health_change_signal: null,
      motivation_signal: 4,
    },
  },
];

const APP_BUNDLE = {
  health: {
    status: "ok",
    environment: "test",
    database_configured: true,
    programs: 1,
  },
  programs: [PROGRAM],
  program_settings: [
    {
      id: "setting-1",
      program_id: PROGRAM.id,
      weekly_followup_capacity: 25,
      worker_count: 4,
      medium_risk_multiplier: 2,
      high_risk_share_floor: 0.1,
      review_window_days: 30,
      label_definition_preset: "cct_missed_cycle",
      dropout_inactivity_days: 30,
      prediction_window_days: 30,
      label_noise_strategy: "operational_soft_labels",
      soft_label_weight: 0.35,
      silent_transfer_detection_enabled: true,
      low_risk_channel: "sms",
      medium_risk_channel: "call",
      high_risk_channel: "visit",
      tracing_sms_delay_days: 3,
      tracing_call_delay_days: 7,
      tracing_visit_delay_days: 14,
      escalation_window_days: 7,
      escalation_max_attempts: 2,
      fairness_reweighting_enabled: true,
      fairness_target_dimensions: ["gender", "region", "household_type"],
      fairness_max_gap: 0.15,
      fairness_min_group_size: 15,
      updated_at: NOW,
    },
  ],
  program_validation_settings: [
    {
      id: "validation-1",
      program_id: PROGRAM.id,
      shadow_mode_enabled: true,
      shadow_prediction_window_days: 30,
      minimum_precision_at_capacity: 0.7,
      minimum_recall_at_capacity: 0.5,
      require_fairness_review: true,
      last_evaluation_status: "ready_for_shadow_mode",
      last_shadow_run_at: NOW,
      updated_at: NOW,
    },
  ],
  program_data_policies: [
    {
      id: "policy-1",
      program_id: PROGRAM.id,
      storage_mode: "self_hosted",
      data_residency_region: "eu-central",
      cross_border_transfers_allowed: false,
      pii_tokenization_enabled: true,
      consent_required: true,
      federated_learning_enabled: true,
      updated_at: NOW,
    },
  ],
  governance_beneficiaries: [
    {
      id: "case-1",
      full_name: "Amina Noor",
      external_id_masked: "NOR-***-001",
      pii_token: "tok_case_1",
      program_name: PROGRAM.name,
      region: "Northern Region",
      status: "active",
      opted_out: false,
      modeling_consent_status: "granted",
      consent_captured_at: NOW,
      consent_explained_at: NOW,
      consent_method: "verbal",
      consent_note: "Explained during enrollment visit",
      risk_level: "High",
      risk_score: 92,
      last_contact_days: 17,
      last_intervention_at: null,
    },
  ],
  governance_alerts: [
    {
      beneficiary_id: "alert-1",
      beneficiary_name: "Ruth Achieng",
      program_name: PROGRAM.name,
      region: "Northern Region",
      alert_level: "attention",
      dropout_date: "2026-03-02T00:00:00Z",
      risk_level: "High",
      note: "Beneficiary dropped out without supportive outreach in the prior 30 days.",
    },
  ],
  connectors: [],
  connector_sync_runs: [],
  connector_dispatch_runs: [],
  model_evaluations: [
    {
      id: "evaluation-1",
      created_by_email: CURRENT_USER.email,
      program_ids: [PROGRAM.id],
      cohorts: [],
      temporal_strategy: "rolling",
      status: "ready_for_shadow_mode",
      algorithm: "stacked_ensemble",
      horizon_days: 30,
      samples_evaluated: 420,
      positive_cases: 88,
      created_at: NOW,
      report: {
        status: "ready_for_shadow_mode",
        note: "Rolling validation meets the current shadow-mode threshold.",
        algorithm: "stacked_ensemble",
        horizon_days: 30,
        min_history_days: 60,
        top_k_share: 0.2,
        top_k_count: 25,
        samples_evaluated: 420,
        positive_cases: 88,
        split: {
          temporal_strategy: "rolling",
          train_cases: 280,
          test_cases: 140,
          train_positive_rate: 0.2,
          test_positive_rate: 0.21,
          train_start: "2025-06-01",
          train_end: "2026-01-31",
          test_start: "2026-02-01",
          test_end: "2026-03-01",
          folds_considered: 4,
          folds_used: 4,
          balanced_folds: 4,
          aggregation_note: "Counts are averaged across rolling folds.",
        },
        metrics: {
          auc_roc: { value: 0.84, lower_ci: 0.79, upper_ci: 0.88 },
          pr_auc: { value: 0.67, lower_ci: 0.6, upper_ci: 0.73 },
          precision: { value: 0.71, lower_ci: 0.64, upper_ci: 0.77 },
          recall: { value: 0.69, lower_ci: 0.61, upper_ci: 0.76 },
          f1: { value: 0.7, lower_ci: 0.63, upper_ci: 0.76 },
          brier_score: { value: 0.16, lower_ci: 0.14, upper_ci: 0.19 },
          top_k_precision: { value: 0.72, lower_ci: 0.64, upper_ci: 0.78 },
          top_k_recall: { value: 0.56, lower_ci: 0.49, upper_ci: 0.63 },
          top_k_lift: { value: 3.1, lower_ci: 2.8, upper_ci: 3.4 },
          expected_calibration_error: { value: 0.06, lower_ci: 0.04, upper_ci: 0.08 },
        },
        calibration: [
          {
            bin_index: 1,
            lower_bound: 0.03,
            upper_bound: 0.12,
            predicted_rate: 0.08,
            observed_rate: 0.09,
            count: 84,
          },
        ],
        fairness_audit: {
          status: "attention",
          note: "Regional parity should be reviewed before any live action.",
          dimensions: [
            {
              dimension: "region",
              status: "attention",
              note: "Northern Region false-positive rate is elevated.",
              max_false_positive_gap: 0.11,
              max_recall_gap: 0.08,
              groups: [
                {
                  group_name: "Northern Region",
                  sample_size: 31,
                  positive_count: 7,
                  predicted_positive_count: 9,
                  flagged_rate: 0.29,
                  false_positive_rate: 0.17,
                  recall_rate: 0.71,
                  severity: "attention",
                  guidance: "Review transport-barrier features before live use.",
                },
              ],
            },
          ],
        },
      },
    },
  ],
  shadow_runs: [
    {
      id: "shadow-1",
      program_id: PROGRAM.id,
      program_name: PROGRAM.name,
      status: "partial_followup",
      snapshot_date: "2026-02-20",
      horizon_days: 30,
      top_k_count: 10,
      cases_captured: 24,
      high_risk_cases: 8,
      due_now_cases: 6,
      matured_cases: 12,
      observed_positive_cases: 3,
      actioned_cases: 7,
      top_k_precision: 0.4,
      top_k_recall: 0.67,
      note: "Half the shadow cohort has now matured.",
      created_by_email: CURRENT_USER.email,
      created_at: NOW,
      completed_at: null,
    },
  ],
  federated_rounds: [
    {
      id: "round-1",
      round_name: "retainai-round-001",
      status: "open",
      opened_at: NOW,
      closed_at: null,
      aggregation_note: "1 secure update collected.",
      aggregated_payload: null,
      updates: [
        {
          id: "update-1",
          deployment_label: "demo-site",
          submitted_at: NOW,
          source_program_id: PROGRAM.id,
          status: "verified",
          fingerprint: "abc123",
          verification_note: "Signature valid",
        },
      ],
    },
  ],
  jobs: [
    {
      id: "job-1",
      job_type: "model_train",
      status: "succeeded",
      payload: { force: true },
      result: { training_rows: 180 },
      error_message: null,
      attempts: 1,
      max_attempts: 3,
      retry_backoff_seconds: 45,
      available_at: NOW,
      started_at: NOW,
      completed_at: NOW,
      last_error_at: null,
      dead_lettered_at: null,
      created_at: NOW,
      created_by_email: CURRENT_USER.email,
    },
  ],
  model_schedule: {
    id: "schedule-1",
    enabled: true,
    cadence: "weekly",
    auto_retrain_after_sync: true,
    last_run_at: NOW,
    next_run_at: "2026-03-17T10:00:00Z",
    updated_at: NOW,
  },
  imports: [
    {
      id: "import-1",
      program_id: PROGRAM.id,
      program_name: PROGRAM.name,
      dataset_type: "beneficiaries",
      source_format: "csv",
      filename: "beneficiaries.csv",
      records_received: 200,
      records_processed: 198,
      records_failed: 2,
      duplicates_detected: 1,
      resolved_mapping: { external_id: "id", enrollment_date: "enrollment_date" },
      warnings: ["2 rows had missing household size"],
      quality_summary: { quality_score: 0.94 },
      created_at: NOW,
    },
  ],
  summary: {
    active_beneficiaries: 198,
    high_risk_cases: 12,
    predicted_30_day_dropout: 18,
    intervention_success_rate: 67,
    weekly_followups_due: 16,
    model_mode: "program_specific_with_base_model",
    last_retrained: NOW,
    quality_note: "Model calibrated to current staff follow-up capacity.",
    top_risk_drivers: [
      { name: "Missed check-ins", impacted_beneficiaries: 14, insight: "Attendance slippage is concentrated in the last two weeks." },
      { name: "Transport barriers", impacted_beneficiaries: 9, insight: "Remote northern communities report longer travel times." },
    ],
    region_alerts: [
      { region: "Northern Region", retention_delta: -8, note: "Retention is down 8 points over the last quarter." },
    ],
    model_status: {
      id: "model-1",
      model_mode: "program_specific_with_base_model",
      algorithm: "stacked_ensemble",
      status: "deployed",
      mlflow_run_id: "run-123",
      trained_at: NOW,
      training_rows: 180,
      positive_rows: 42,
      feature_count: 31,
      metrics: {
        auc_roc: 0.84,
        precision: 0.71,
        recall: 0.78,
        top_20pct_recall: 0.74,
        high_risk_threshold_score: 80,
        high_risk_precision: 0.72,
        medium_or_higher_recall: 0.86,
      },
      top_drivers: [
        { name: "days_since_last_contact", direction: "up", contribution: 0.32, detail: "Recent contact gap is widening." },
        { name: "attendance_rate_30d", direction: "down", contribution: 0.24, detail: "Attendance is below cohort median." },
        { name: "sentiment_score", direction: "down", contribution: 0.11, detail: "Field notes indicate higher distress." },
      ],
      notes: "Deployed with stacked ensemble and SHAP explanations.",
      fallback_active: false,
      bias_audit: {
        status: "ok",
        note: "No material fairness gaps exceeded the configured threshold.",
        dimensions: [
          {
            dimension: "region",
            status: "ok",
            note: "Regional flagged-rate gaps remain within policy thresholds.",
            groups: [
              {
                group_name: "Northern Region",
                flagged_rate: 0.21,
                false_positive_rate: 0.08,
                recall_rate: 0.76,
                support_count: 31,
              },
            ],
          },
        ],
      },
      drift_report: {
        id: "drift-1",
        status: "ok",
        overall_psi: 0.09,
        note: "Recent scoring distribution remains stable.",
        monitored_at: NOW,
        feature_reports: [
          { feature_name: "attendance_rate_30d", psi: 0.06, status: "ok", note: "Stable" },
        ],
      },
    },
  },
  risk_cases: RISK_CASES,
  retention_curves: {
    narrative: "Retention remains strongest in the first cash-transfer cohort but the newest cohort is slipping during enrollment.",
    series: [
      { key: "cohort_2026_a", label: "Cohort 2026-A", color: "#204f5a" },
      { key: "cohort_2026_b", label: "Cohort 2026-B", color: "#a55d35" },
    ],
    data: [
      { month: "Month 1", cohort_2026_a: 100, cohort_2026_b: 100 },
      { month: "Month 2", cohort_2026_a: 94, cohort_2026_b: 88 },
      { month: "Month 3", cohort_2026_a: 92, cohort_2026_b: 80 },
    ],
  },
  retention_analytics: {
    narrative: "Northern Region has the sharpest recent decline, especially during enrollment transitions.",
    trend_highlights: ["Northern Region retention fell 8% over the last 3 months."],
    breakdowns: [
      { dimension: "region", group_name: "Northern Region", retention_rate: 0.72, recent_dropout_rate: 0.18, active_beneficiaries: 94 },
      { dimension: "gender", group_name: "Women", retention_rate: 0.81, recent_dropout_rate: 0.12, active_beneficiaries: 122 },
    ],
  },
  interventions: [
    {
      beneficiary_id: "case-2",
      beneficiary_name: "David Ochieng",
      action_type: "Follow-up call",
      note: "Confirmed availability for next payment collection point.",
      successful: true,
      logged_at: NOW,
    },
  ],
  intervention_effectiveness: {
    narrative: "Field calls followed by a visit outperform call-only interventions in low-connectivity regions.",
    top_recommendations: ["Pair calls with field visits in Northern Region for high-risk households."],
    rows: [
      {
        action_type: "Follow-up call",
        context_label: "Northern Region",
        attempts: 12,
        success_rate: 0.67,
        recommendation_strength: "strong",
      },
    ],
  },
  donor_report_summary: {
    narrative: "Retention operations improved follow-up coverage while keeping beneficiary opt-out safeguards active.",
    headline_metrics: {
      active_beneficiaries: 198,
      reengagement_rate: 0.67,
      high_risk_followups_due: 16,
    },
  },
  synthetic_portfolio: [
    {
      program_type: "cash_transfer",
      program_name: "Synthetic Cash Transfer Pilot",
      beneficiaries: 180,
      expected_dropout_rate: 0.22,
      generated_at: NOW,
    },
  ],
  sso_config: {
    enabled: false,
    mode: "header",
    provider_label: null,
    interactive: false,
  },
  runtime_status: {
    status: "ok",
    deployment_region: "eu-central",
    job_backend: "db",
    enforce_runtime_policy: false,
    violations: [],
    warnings: [],
  },
  worker_health: {
    backend: "db",
    status: "healthy",
    queued: 0,
    running: 0,
    failed: 0,
    dead_letter: 0,
    worker_status: "healthy",
    workers: ["local-worker"],
    next_ready_at: null,
    oldest_queue_age_seconds: 0,
    retry_backoff_seconds: 45,
    max_attempts: 3,
    stalled_threshold_seconds: 600,
  },
  audit_logs: [
    {
      id: "audit-1",
      actor_email: CURRENT_USER.email,
      actor_role: CURRENT_USER.role,
      action: "auth.login",
      resource_type: "session",
      resource_id: "session-1",
      details: { auth_method: "password" },
      ip_address: "127.0.0.1",
      created_at: NOW,
    },
  ],
};

function fulfillJson(route: Route, body: unknown, status = 200): Promise<void> {
  return route.fulfill({
    status,
    contentType: "application/json",
    body: JSON.stringify(body),
  });
}

export async function mockRetainAiApi(page: Page): Promise<void> {
  await page.route("**/health", async (route) => {
    await fulfillJson(route, APP_BUNDLE.health);
  });

  await page.route("**/api/v1/**", async (route) => {
    const url = new URL(route.request().url());
    const path = url.pathname;
    const method = route.request().method();

    if (method === "GET" && path === "/api/v1/auth/sso/config") {
      await fulfillJson(route, APP_BUNDLE.sso_config);
      return;
    }
    if (method === "POST" && path === "/api/v1/auth/login") {
      await fulfillJson(route, {
        access_token: "mock-token",
        token_type: "bearer",
        expires_in_seconds: 43200,
        session_id: "session-1",
        user: CURRENT_USER,
      });
      return;
    }
    if (method === "GET" && path === "/api/v1/auth/me") {
      await fulfillJson(route, CURRENT_USER);
      return;
    }
    if (method === "POST" && path === "/api/v1/auth/logout") {
      await fulfillJson(route, { status: "revoked", session_id: "session-1" });
      return;
    }
    if (method === "GET" && path === "/api/v1/audit-logs") {
      await fulfillJson(route, APP_BUNDLE.audit_logs);
      return;
    }
    if (method === "GET" && path === "/api/v1/governance/alerts") {
      await fulfillJson(route, APP_BUNDLE.governance_alerts);
      return;
    }
    if (method === "GET" && path === "/api/v1/beneficiaries/governance") {
      await fulfillJson(route, APP_BUNDLE.governance_beneficiaries);
      return;
    }
    if (method === "GET" && path.endsWith("/explanation")) {
      await fulfillJson(route, {
        beneficiary_id: path.split("/")[4],
        program_name: PROGRAM.name,
        risk_level: "High",
        beneficiary_label: "Amina Noor",
        explanation: "Amina has missed recent check-ins and may benefit from a supportive outreach call.",
        beneficiary_facing_summary: "This case should prompt supportive outreach, not any punitive action.",
        confidence: "High confidence",
        translated_ready_note: "Plain-language summary ready for beneficiary discussion.",
        data_points_used: ["Missed recent check-ins", "Transport barrier reported in field note"],
        support_recommendation: "Call within 48 hours and arrange a field visit if unreachable.",
      });
      return;
    }
    if (method === "POST" && path === "/api/v1/interventions") {
      const payload = route.request().postDataJSON() as Record<string, string>;
      await fulfillJson(route, {
        beneficiary_id: payload.beneficiary_id ?? "case-1",
        beneficiary_name: "Amina Noor",
        action_type: payload.action_type ?? "Follow-up call",
        note: payload.note ?? "Logged from queue",
        successful: true,
        logged_at: NOW,
      });
      return;
    }

    const simpleGetMap: Record<string, unknown> = {
      "/api/v1/programs": APP_BUNDLE.programs,
      "/api/v1/program-settings": APP_BUNDLE.program_settings,
      "/api/v1/program-validation": APP_BUNDLE.program_validation_settings,
      "/api/v1/program-data-policies": APP_BUNDLE.program_data_policies,
      "/api/v1/connectors": APP_BUNDLE.connectors,
      "/api/v1/connectors/sync-runs": APP_BUNDLE.connector_sync_runs,
      "/api/v1/connectors/dispatch-runs": APP_BUNDLE.connector_dispatch_runs,
      "/api/v1/model/evaluations": APP_BUNDLE.model_evaluations,
      "/api/v1/program-validation/shadow-runs": APP_BUNDLE.shadow_runs,
      "/api/v1/federated/rounds": APP_BUNDLE.federated_rounds,
      "/api/v1/jobs": APP_BUNDLE.jobs,
      "/api/v1/model/schedule": APP_BUNDLE.model_schedule,
      "/api/v1/imports": APP_BUNDLE.imports,
      "/api/v1/dashboard/summary": APP_BUNDLE.summary,
      "/api/v1/risk-cases": APP_BUNDLE.risk_cases,
      "/api/v1/retention/curves": APP_BUNDLE.retention_curves,
      "/api/v1/retention/analytics": APP_BUNDLE.retention_analytics,
      "/api/v1/interventions": APP_BUNDLE.interventions,
      "/api/v1/interventions/effectiveness": APP_BUNDLE.intervention_effectiveness,
      "/api/v1/reports/donor-summary": APP_BUNDLE.donor_report_summary,
      "/api/v1/synthetic/portfolio": APP_BUNDLE.synthetic_portfolio,
      "/api/v1/ops/runtime-status": APP_BUNDLE.runtime_status,
      "/api/v1/ops/worker-health": APP_BUNDLE.worker_health,
    };

    if (method === "GET" && path in simpleGetMap) {
      await fulfillJson(route, simpleGetMap[path]);
      return;
    }

    await route.abort();
  });
}
