from __future__ import annotations

import argparse
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from run_model_backtest import _bootstrap_database, _load_partner_files
from validate_partner_bundle import validate_bundle


def _serialize_segment(label: str, payload: dict[str, object]) -> dict[str, object]:
    segment = dict(payload)
    segment["label"] = label
    return segment


def _render_markdown(summary: dict[str, object]) -> str:
    lines = [
        "# Synthetic Stress Suite",
        "",
        f"- Rows per program: `{summary['rows_per_program']}`",
        f"- Seed: `{summary['seed']}`",
        "",
        "| Scenario | Status | AUC | PR-AUC | Top-K precision | Top-K lift | Fairness |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for scenario in summary["scenarios"]:
        fairness = (scenario["overall"].get("fairness_audit") or {}).get("status", "n/a")
        lines.append(
            "| {name} | {status} | {auc:.4f} | {pr_auc:.4f} | {top_k_precision:.4f} | {top_k_lift:.4f} | {fairness} |".format(
                name=scenario["scenario"],
                status=scenario["overall"]["status"],
                auc=scenario["overall"]["metrics"]["auc_roc"]["value"],
                pr_auc=scenario["overall"]["metrics"]["pr_auc"]["value"],
                top_k_precision=scenario["overall"]["metrics"]["top_k_precision"]["value"],
                top_k_lift=scenario["overall"]["metrics"]["top_k_lift"]["value"],
                fairness=fairness,
            )
        )

    for scenario in summary["scenarios"]:
        lines.extend(
            [
                "",
                f"## {scenario['scenario']}",
                "",
                f"- Description: {scenario['description']}",
                f"- Overall status: `{scenario['overall']['status']}`",
                f"- Validation readiness: `{scenario['validation_readiness']}`",
                f"- Interpretation: {scenario['interpretation']}",
                "",
                "### Program Holdouts",
                "",
            ]
        )
        if scenario["program_holdouts"]:
            for segment in scenario["program_holdouts"]:
                lines.append(
                    f"- `{segment['label']}`: `{segment['status']}`; AUC `{segment['metrics']['auc_roc']['value']}`, "
                    f"PR-AUC `{segment['metrics']['pr_auc']['value']}`, fairness `{(segment.get('fairness_audit') or {}).get('status', 'n/a')}`"
                )
        else:
            lines.append("- No program holdouts met the minimum threshold.")
        lines.extend(["", "### Cohort Holdouts", ""])
        if scenario["cohort_holdouts"]:
            for segment in scenario["cohort_holdouts"]:
                lines.append(
                    f"- `{segment['label']}`: `{segment['status']}`; AUC `{segment['metrics']['auc_roc']['value']}`, "
                    f"PR-AUC `{segment['metrics']['pr_auc']['value']}`, fairness `{(segment.get('fairness_audit') or {}).get('status', 'n/a')}`"
                )
        else:
            lines.append("- No cohort holdouts met the minimum threshold.")
    lines.extend(["", "## Overall Interpretation", "", summary["interpretation"], ""])
    return "\n".join(lines)


def _scenario_interpretation(report: dict[str, object]) -> str:
    fairness_status = (report["overall"].get("fairness_audit") or {}).get("status")
    if fairness_status == "attention":
        return "Ranking performance is acceptable, but fairness drift is visible under this stress scenario."
    if report["overall"]["status"] != "ready_for_shadow_mode":
        return "This stress scenario degrades the model below the current shadow-mode bar."
    return "This stress scenario remains inside the current shadow-mode bar."


def _overall_interpretation(scenarios: list[dict[str, object]]) -> str:
    failures = [scenario["scenario"] for scenario in scenarios if scenario["overall"]["status"] != "ready_for_shadow_mode"]
    fairness = [
        scenario["scenario"]
        for scenario in scenarios
        if (scenario["overall"].get("fairness_audit") or {}).get("status") == "attention"
    ]
    notes: list[str] = []
    if failures:
        notes.append(f"scenarios below the current bar: {', '.join(failures)}")
    if fairness:
        notes.append(f"scenarios with fairness attention flags: {', '.join(fairness)}")
    if not notes:
        return "All configured synthetic stress scenarios stayed within the current shadow-mode bar. Real partner data is still required before live deployment."
    return "Synthetic stress testing exposed meaningful fragility: " + "; ".join(notes) + "."


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate synthetic stress portfolios and run the formal RetainAI evaluation suite.")
    parser.add_argument("--output-dir", type=Path, default=Path("data/synthetic/stress-suite"))
    parser.add_argument("--rows-per-program", type=int, default=300)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--scenarios", nargs="*", default=[])
    parser.add_argument("--rolling-folds", type=int, default=4)
    parser.add_argument("--bootstrap-iterations", type=int, default=20)
    parser.add_argument("--horizon-days", type=int, default=30)
    parser.add_argument("--min-history-days", type=int, default=60)
    parser.add_argument("--top-k-share", type=float, default=0.2)
    parser.add_argument("--top-k-capacity", type=int)
    parser.add_argument("--output-json", type=Path)
    parser.add_argument("--output-md", type=Path)
    args = parser.parse_args()

    _bootstrap_database(None)

    from app import schemas
    from app.services.synthetic_data import (
        PROGRAM_TYPE_BASELINES,
        STRESS_SCENARIOS,
        generate_synthetic_stress_portfolio,
        write_synthetic_portfolio_csv,
    )

    selected_scenarios = args.scenarios or list(STRESS_SCENARIOS.keys())
    unknown = [name for name in selected_scenarios if name not in STRESS_SCENARIOS]
    if unknown:
        raise SystemExit(f"Unknown stress scenarios: {', '.join(unknown)}")

    request = schemas.EvaluationRequest(
        temporal_strategy="rolling",
        rolling_folds=args.rolling_folds,
        bootstrap_iterations=args.bootstrap_iterations,
        horizon_days=args.horizon_days,
        min_history_days=args.min_history_days,
        top_k_share=args.top_k_share,
        top_k_capacity=args.top_k_capacity,
    )

    from app.db import SessionLocal, reset_db_connection
    from app.models import Beneficiary, Program
    from app.services.evaluation import (
        collect_snapshot_dataset,
        evaluate_model_backtest,
        evaluate_segment_holdout_reports,
    )
    from sqlalchemy import select

    scenario_reports: list[dict[str, object]] = []
    for scenario_index, scenario_name in enumerate(selected_scenarios):
        scenario_dir = args.output_dir / scenario_name
        portfolio = generate_synthetic_stress_portfolio(
            scenario_name=scenario_name,
            rows_per_program=args.rows_per_program,
            seed=args.seed + (scenario_index * 1000),
        )
        file_manifest = write_synthetic_portfolio_csv(portfolio, scenario_dir)

        validations = []
        for item in file_manifest:
            validations.append(
                {
                    "program_type": item["program_type"],
                    **validate_bundle(Path(item["beneficiaries_file"]), Path(item["events_file"])),
                }
            )

        temp_dir = TemporaryDirectory()
        database_url = f"sqlite:///{Path(temp_dir.name, 'retainai-synthetic-stress.db').as_posix()}"
        try:
            _bootstrap_database(database_url)
            for item in file_manifest:
                _load_partner_files(
                    beneficiaries_file=Path(item["beneficiaries_file"]),
                    events_file=Path(item["events_file"]),
                    program_name=item["program_name"],
                    program_type=item["program_type"],
                    country=item["country"],
                )

            with SessionLocal() as session:
                overall = evaluate_model_backtest(session, request).model_dump()
                _, snapshots, beneficiaries_by_id = collect_snapshot_dataset(session, request)
                programs = list(session.scalars(select(Program).order_by(Program.name)).all())
                program_name_by_id = {program.id: program.name for program in programs}
                cohorts = sorted({value for value in session.scalars(select(Beneficiary.cohort)).all() if value})

                program_backtests = []
                for program in programs:
                    try:
                        payload = evaluate_model_backtest(
                            session,
                            request.model_copy(update={"program_ids": [program.id]}),
                        ).model_dump()
                    except ValueError:
                        continue
                    program_backtests.append(_serialize_segment(program.name, payload))

                cohort_backtests = []
                for cohort in cohorts:
                    try:
                        payload = evaluate_model_backtest(
                            session,
                            request.model_copy(update={"cohorts": [cohort]}),
                        ).model_dump()
                    except ValueError:
                        continue
                    cohort_backtests.append(_serialize_segment(cohort, payload))

                program_holdouts = [
                    _serialize_segment(label, report.model_dump())
                    for label, report in evaluate_segment_holdout_reports(
                        request=request,
                        snapshots=snapshots,
                        beneficiaries_by_id=beneficiaries_by_id,
                        dimension="program",
                        label_resolver=lambda value: program_name_by_id.get(value, value),
                    )
                ]
                cohort_holdouts = [
                    _serialize_segment(label, report.model_dump())
                    for label, report in evaluate_segment_holdout_reports(
                        request=request,
                        snapshots=snapshots,
                        beneficiaries_by_id=beneficiaries_by_id,
                        dimension="cohort",
                    )
                ]

            report = {
                "scenario": scenario_name,
                "description": STRESS_SCENARIOS[scenario_name].description,
                "output_dir": str(scenario_dir.resolve()),
                "generated_programs": [item["program_type"] for item in file_manifest],
                "validation_readiness": min(
                    (validation["readiness"] for validation in validations),
                    key=lambda value: {"shadow_pilot_candidate": 3, "backtest_ready": 2, "needs_more_history": 1, "not_ready": 0}.get(value, 0),
                ),
                "validations": validations,
                "overall": overall,
                "program_backtests": program_backtests,
                "cohort_backtests": cohort_backtests,
                "program_holdouts": program_holdouts,
                "cohort_holdouts": cohort_holdouts,
            }
            report["interpretation"] = _scenario_interpretation(report)
            scenario_reports.append(report)
            reset_db_connection()
        finally:
            try:
                reset_db_connection()
            except Exception:
                pass
            temp_dir.cleanup()

    summary = {
        "rows_per_program": args.rows_per_program,
        "seed": args.seed,
        "program_types": list(PROGRAM_TYPE_BASELINES.keys()),
        "scenarios": scenario_reports,
    }
    summary["interpretation"] = _overall_interpretation(scenario_reports)

    output_json = args.output_json or (args.output_dir / "synthetic-stress-suite.json")
    output_md = args.output_md or (args.output_dir / "synthetic-stress-suite.md")
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_md.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    output_md.write_text(_render_markdown(summary), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
