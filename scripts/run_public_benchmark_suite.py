from __future__ import annotations

import argparse
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from run_model_backtest import _bootstrap_database, _load_partner_files


DEFAULT_SCENARIOS = (
    ("30d_top10", 30, 60, 0.10),
    ("30d_top20", 30, 60, 0.20),
    ("60d_top20", 60, 90, 0.20),
    ("90d_top20", 90, 120, 0.20),
)


def _render_markdown(summary: dict[str, object]) -> str:
    lines = [
        "# RetainAI Public Benchmark Suite",
        "",
        f"- Dataset label: `{summary['dataset_label']}`",
        f"- Beneficiaries file: `{summary['beneficiaries_file']}`",
        f"- Events file: `{summary['events_file']}`",
        "",
        "## Scenarios",
        "",
        "| Scenario | Horizon | Top-K share | Status | Algorithm | AUC | PR-AUC | Top-K precision | Top-K recall |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for result in summary["results"]:
        lines.append(
            "| {name} | {horizon_days} | {top_k_share:.2f} | {status} | {algorithm} | {auc:.4f} | {pr_auc:.4f} | {top_k_precision:.4f} | {top_k_recall:.4f} |".format(
                name=result["name"],
                horizon_days=result["horizon_days"],
                top_k_share=result["top_k_share"],
                status=result["status"],
                algorithm=result["algorithm"],
                auc=result["metrics"]["auc_roc"]["value"],
                pr_auc=result["metrics"]["pr_auc"]["value"],
                top_k_precision=result["metrics"]["top_k_precision"]["value"],
                top_k_recall=result["metrics"]["top_k_recall"]["value"],
            )
        )
    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            summary["interpretation"],
            "",
        ]
    )
    return "\n".join(lines)


def _interpret(results: list[dict[str, object]]) -> str:
    suspicious = [
        result
        for result in results
        if result["metrics"]["auc_roc"]["value"] >= 0.98 and result["metrics"]["precision"]["value"] >= 0.98
    ]
    if suspicious:
        return (
            "One or more scenarios still look unrealistically strong. Treat this as a useful public benchmark for pipeline stress-testing, "
            "not as evidence of deployment-ready predictive validity."
        )
    ready = [result for result in results if result["status"] == "ready_for_shadow_mode"]
    if ready:
        return (
            "At least one harsher public benchmark scenario clears the current shadow-mode bar, but live NGO readiness still requires partner data "
            "and prospective validation."
        )
    return "None of the public benchmark scenarios clear the current shadow-mode bar. The model stack still needs real-world calibration and validation."


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a multi-scenario RetainAI backtest suite on one public benchmark dataset.")
    parser.add_argument("--beneficiaries-file", type=Path, required=True)
    parser.add_argument("--events-file", type=Path, required=True)
    parser.add_argument("--dataset-label", required=True)
    parser.add_argument("--program-name", required=True)
    parser.add_argument("--program-type", required=True)
    parser.add_argument("--country", required=True)
    parser.add_argument("--temporal-strategy", choices=("holdout", "rolling"), default="rolling")
    parser.add_argument("--rolling-folds", type=int, default=4)
    parser.add_argument("--bootstrap-iterations", type=int, default=20)
    parser.add_argument("--output-json", type=Path)
    parser.add_argument("--output-md", type=Path)
    args = parser.parse_args()

    temp_dir = TemporaryDirectory()
    database_url = f"sqlite:///{Path(temp_dir.name, 'retainai-benchmark-suite.db').as_posix()}"

    try:
        _bootstrap_database(database_url)
        _load_partner_files(
            beneficiaries_file=args.beneficiaries_file,
            events_file=args.events_file,
            program_name=args.program_name,
            program_type=args.program_type,
            country=args.country,
        )

        from app import schemas
        from app.db import SessionLocal, reset_db_connection
        from app.services.evaluation import evaluate_model_backtest

        results: list[dict[str, object]] = []
        with SessionLocal() as session:
            for name, horizon_days, min_history_days, top_k_share in DEFAULT_SCENARIOS:
                report = evaluate_model_backtest(
                    session,
                    schemas.EvaluationRequest(
                        temporal_strategy=args.temporal_strategy,
                        horizon_days=horizon_days,
                        min_history_days=min_history_days,
                        holdout_share=0.25,
                        rolling_folds=args.rolling_folds,
                        top_k_share=top_k_share,
                        bootstrap_iterations=args.bootstrap_iterations,
                    ),
                )
                payload = report.model_dump()
                payload["name"] = name
                results.append(payload)

        summary = {
            "dataset_label": args.dataset_label,
            "beneficiaries_file": str(args.beneficiaries_file.resolve()),
            "events_file": str(args.events_file.resolve()),
            "results": results,
            "interpretation": _interpret(results),
        }
        if args.output_json:
            args.output_json.write_text(json.dumps(summary, indent=2), encoding="utf-8")
        if args.output_md:
            args.output_md.write_text(_render_markdown(summary), encoding="utf-8")
        print(json.dumps(summary, indent=2))
        reset_db_connection()
        return 0
    finally:
        try:
            from app.db import reset_db_connection

            reset_db_connection()
        except Exception:
            pass
        temp_dir.cleanup()


if __name__ == "__main__":
    raise SystemExit(main())
