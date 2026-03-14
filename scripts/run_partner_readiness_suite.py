from __future__ import annotations

import argparse
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from run_model_backtest import _bootstrap_database, _load_partner_files
from validate_partner_bundle import validate_bundle


def _render_markdown(report: dict[str, object]) -> str:
    overall = report["overall_backtest"]
    lines = [
        "# Partner Readiness Suite",
        "",
        f"- Bundle readiness: `{report['bundle_validation']['readiness']}`",
        f"- Overall backtest status: `{overall['status']}`",
        f"- Overall algorithm: `{overall['algorithm']}`",
        f"- Overall AUC: `{overall['metrics']['auc_roc']['value']}`",
        f"- Overall PR-AUC: `{overall['metrics']['pr_auc']['value']}`",
        f"- Overall top-K precision: `{overall['metrics']['top_k_precision']['value']}`",
        f"- Overall top-K recall: `{overall['metrics']['top_k_recall']['value']}`",
        "",
        "## Program Segments",
        "",
    ]
    for segment in report["program_segments"]:
        lines.append(
            f"- `{segment['label']}`: `{segment['status']}` "
            f"(AUC `{segment['metrics']['auc_roc']['value']}`, "
            f"PR-AUC `{segment['metrics']['pr_auc']['value']}`, "
            f"top-K precision `{segment['metrics']['top_k_precision']['value']}`)"
        )
    lines.extend(["", "## Cohort Segments", ""])
    for segment in report["cohort_segments"]:
        lines.append(
            f"- `{segment['label']}`: `{segment['status']}` "
            f"(AUC `{segment['metrics']['auc_roc']['value']}`, "
            f"PR-AUC `{segment['metrics']['pr_auc']['value']}`, "
            f"top-K precision `{segment['metrics']['top_k_precision']['value']}`)"
        )
    lines.extend(["", "## Interpretation", "", report["interpretation"], ""])
    return "\n".join(lines)


def _segment_summary(label: str, payload: dict[str, object]) -> dict[str, object]:
    summary = dict(payload)
    summary["label"] = label
    return summary


def _interpret(overall: dict[str, object], program_segments: list[dict[str, object]], cohort_segments: list[dict[str, object]]) -> str:
    weak_programs = [segment["label"] for segment in program_segments if segment["status"] != "ready_for_shadow_mode"]
    weak_cohorts = [segment["label"] for segment in cohort_segments if segment["status"] != "ready_for_shadow_mode"]
    if weak_programs or weak_cohorts:
        weaknesses = []
        if weak_programs:
            weaknesses.append(f"program segments not ready: {', '.join(weak_programs[:4])}")
        if weak_cohorts:
            weaknesses.append(f"cohort segments not ready: {', '.join(weak_cohorts[:4])}")
        return (
            f"Overall backtest status is {overall['status']}, but segment instability remains; "
            + "; ".join(weaknesses)
            + ". Use shadow mode only after reviewing those segments."
        )
    return "Overall, program-level, and cohort-level backtests all clear the current shadow-mode bar. The next step is a real shadow pilot with live weekly monitoring."


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a partner-data readiness suite over a beneficiary/events bundle.")
    parser.add_argument("--beneficiaries-file", type=Path, required=True)
    parser.add_argument("--events-file", type=Path, required=True)
    parser.add_argument("--program-name", required=True)
    parser.add_argument("--program-type", required=True)
    parser.add_argument("--country", required=True)
    parser.add_argument("--bootstrap-iterations", type=int, default=20)
    parser.add_argument("--rolling-folds", type=int, default=4)
    parser.add_argument("--output-json", type=Path)
    parser.add_argument("--output-md", type=Path)
    args = parser.parse_args()

    bundle_validation = validate_bundle(args.beneficiaries_file, args.events_file)

    temp_dir = TemporaryDirectory()
    database_url = f"sqlite:///{Path(temp_dir.name, 'retainai-partner-suite.db').as_posix()}"
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
        from app.models import Beneficiary, Program
        from app.services.evaluation import evaluate_model_backtest
        from sqlalchemy import select

        with SessionLocal() as session:
            overall = evaluate_model_backtest(
                session,
                schemas.EvaluationRequest(
                    temporal_strategy="rolling",
                    rolling_folds=args.rolling_folds,
                    bootstrap_iterations=args.bootstrap_iterations,
                ),
            ).model_dump()

            programs = list(session.scalars(select(Program).order_by(Program.name)).all())
            cohorts = sorted(
                {
                    value
                    for value in session.scalars(select(Beneficiary.cohort)).all()
                    if value
                }
            )

            program_segments: list[dict[str, object]] = []
            for program in programs:
                try:
                    segment = evaluate_model_backtest(
                        session,
                        schemas.EvaluationRequest(
                            temporal_strategy="rolling",
                            rolling_folds=args.rolling_folds,
                            bootstrap_iterations=args.bootstrap_iterations,
                            program_ids=[program.id],
                        ),
                    ).model_dump()
                except ValueError:
                    continue
                program_segments.append(_segment_summary(program.name, segment))

            cohort_segments: list[dict[str, object]] = []
            for cohort in cohorts:
                try:
                    segment = evaluate_model_backtest(
                        session,
                        schemas.EvaluationRequest(
                            temporal_strategy="rolling",
                            rolling_folds=args.rolling_folds,
                            bootstrap_iterations=args.bootstrap_iterations,
                            cohorts=[cohort],
                        ),
                    ).model_dump()
                except ValueError:
                    continue
                cohort_segments.append(_segment_summary(cohort, segment))

        report = {
            "bundle_validation": bundle_validation,
            "overall_backtest": overall,
            "program_segments": program_segments,
            "cohort_segments": cohort_segments,
        }
        report["interpretation"] = _interpret(overall, program_segments, cohort_segments)
        if args.output_json:
            args.output_json.write_text(json.dumps(report, indent=2), encoding="utf-8")
        if args.output_md:
            args.output_md.write_text(_render_markdown(report), encoding="utf-8")
        print(json.dumps(report, indent=2))
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
