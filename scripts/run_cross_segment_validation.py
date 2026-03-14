from __future__ import annotations

import argparse
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from run_model_backtest import _bootstrap_database, _load_partner_files


def _segment_payload(label: str, payload: dict[str, object]) -> dict[str, object]:
    segment = dict(payload)
    segment["label"] = label
    return segment


def _render_segment_section(title: str, segments: list[dict[str, object]]) -> list[str]:
    lines = ["", f"## {title}", ""]
    if not segments:
        lines.append("- No evaluable segments met the minimum data threshold.")
        return lines
    lines.append("| Segment | Status | AUC | PR-AUC | Top-K precision | Top-K recall | Fairness |")
    lines.append("| --- | --- | --- | --- | --- | --- | --- |")
    for segment in segments:
        fairness = (segment.get("fairness_audit") or {}).get("status", "n/a")
        lines.append(
            "| {label} | {status} | {auc:.4f} | {pr_auc:.4f} | {top_k_precision:.4f} | {top_k_recall:.4f} | {fairness} |".format(
                label=segment["label"],
                status=segment["status"],
                auc=segment["metrics"]["auc_roc"]["value"],
                pr_auc=segment["metrics"]["pr_auc"]["value"],
                top_k_precision=segment["metrics"]["top_k_precision"]["value"],
                top_k_recall=segment["metrics"]["top_k_recall"]["value"],
                fairness=fairness,
            )
        )
    return lines


def _interpret(summary: dict[str, object]) -> str:
    issues: list[str] = []
    for key in (
        "program_backtests",
        "cohort_backtests",
        "program_holdouts",
        "cohort_holdouts",
    ):
        failed = [segment["label"] for segment in summary[key] if segment["status"] != "ready_for_shadow_mode"]
        if failed:
            issues.append(f"{key.replace('_', ' ')} not ready: {', '.join(failed[:4])}")
    if issues:
        return "Cross-segment validation found unstable slices. " + "; ".join(issues) + ". Use these results to narrow pilot scope or raise follow-up capacity thresholds."
    return "Cross-segment validation is stable across the evaluated program and cohort slices. The remaining gate is real partner shadow-pilot evidence."


def _render_markdown(summary: dict[str, object]) -> str:
    overall = summary["overall"]
    lines = [
        "# Cross-Segment Validation",
        "",
        f"- Overall status: `{overall['status']}`",
        f"- Overall algorithm: `{overall['algorithm']}`",
        f"- Overall AUC: `{overall['metrics']['auc_roc']['value']}`",
        f"- Overall PR-AUC: `{overall['metrics']['pr_auc']['value']}`",
        f"- Overall top-K precision: `{overall['metrics']['top_k_precision']['value']}`",
        f"- Overall top-K recall: `{overall['metrics']['top_k_recall']['value']}`",
        f"- Overall top-K lift: `{overall['metrics']['top_k_lift']['value']}`",
        f"- Overall calibration error: `{overall['metrics']['expected_calibration_error']['value']}`",
    ]
    lines.extend(_render_segment_section("Program Backtests", summary["program_backtests"]))
    lines.extend(_render_segment_section("Cohort Backtests", summary["cohort_backtests"]))
    lines.extend(_render_segment_section("Program Holdouts", summary["program_holdouts"]))
    lines.extend(_render_segment_section("Cohort Holdouts", summary["cohort_holdouts"]))
    lines.extend(["", "## Interpretation", "", summary["interpretation"], ""])
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run richer RetainAI cross-program and cross-cohort validation.")
    parser.add_argument("--database-url")
    parser.add_argument("--beneficiaries-file", type=Path)
    parser.add_argument("--events-file", type=Path)
    parser.add_argument("--program-name", default="Cross-Segment Validation")
    parser.add_argument("--program-type", default="Cash Transfer")
    parser.add_argument("--country", default="Unknown")
    parser.add_argument("--rolling-folds", type=int, default=4)
    parser.add_argument("--bootstrap-iterations", type=int, default=40)
    parser.add_argument("--horizon-days", type=int, default=30)
    parser.add_argument("--min-history-days", type=int, default=60)
    parser.add_argument("--top-k-share", type=float, default=0.2)
    parser.add_argument("--top-k-capacity", type=int)
    parser.add_argument("--output-json", type=Path)
    parser.add_argument("--output-md", type=Path)
    args = parser.parse_args()

    if not args.database_url and not (args.beneficiaries_file or args.events_file):
        raise SystemExit("Either --database-url or a beneficiary/events bundle is required.")

    temp_dir: TemporaryDirectory[str] | None = None
    database_url = args.database_url
    if database_url is None:
        temp_dir = TemporaryDirectory()
        database_url = f"sqlite:///{Path(temp_dir.name, 'retainai-cross-segment.db').as_posix()}"

    try:
        _bootstrap_database(database_url)
        if args.beneficiaries_file or args.events_file:
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
        from app.services.evaluation import (
            collect_snapshot_dataset,
            evaluate_model_backtest,
            evaluate_segment_holdout_reports,
        )
        from sqlalchemy import select

        request = schemas.EvaluationRequest(
            temporal_strategy="rolling",
            rolling_folds=args.rolling_folds,
            bootstrap_iterations=args.bootstrap_iterations,
            horizon_days=args.horizon_days,
            min_history_days=args.min_history_days,
            top_k_share=args.top_k_share,
            top_k_capacity=args.top_k_capacity,
        )

        with SessionLocal() as session:
            overall = evaluate_model_backtest(session, request).model_dump()
            _, snapshots, beneficiaries_by_id = collect_snapshot_dataset(session, request)

            programs = list(session.scalars(select(Program).order_by(Program.name)).all())
            program_name_by_id = {program.id: program.name for program in programs}
            cohorts = sorted({value for value in session.scalars(select(Beneficiary.cohort)).all() if value})

            program_backtests: list[dict[str, object]] = []
            for program in programs:
                try:
                    payload = evaluate_model_backtest(
                        session,
                        request.model_copy(update={"program_ids": [program.id]}),
                    ).model_dump()
                except ValueError:
                    continue
                program_backtests.append(_segment_payload(program.name, payload))

            cohort_backtests: list[dict[str, object]] = []
            for cohort in cohorts:
                try:
                    payload = evaluate_model_backtest(
                        session,
                        request.model_copy(update={"cohorts": [cohort]}),
                    ).model_dump()
                except ValueError:
                    continue
                cohort_backtests.append(_segment_payload(cohort, payload))

            program_holdouts = [
                _segment_payload(label, report.model_dump())
                for label, report in evaluate_segment_holdout_reports(
                    request=request,
                    snapshots=snapshots,
                    beneficiaries_by_id=beneficiaries_by_id,
                    dimension="program",
                    label_resolver=lambda value: program_name_by_id.get(value, value),
                )
            ]
            cohort_holdouts = [
                _segment_payload(label, report.model_dump())
                for label, report in evaluate_segment_holdout_reports(
                    request=request,
                    snapshots=snapshots,
                    beneficiaries_by_id=beneficiaries_by_id,
                    dimension="cohort",
                )
            ]

        summary = {
            "overall": overall,
            "program_backtests": program_backtests,
            "cohort_backtests": cohort_backtests,
            "program_holdouts": program_holdouts,
            "cohort_holdouts": cohort_holdouts,
        }
        summary["interpretation"] = _interpret(summary)
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
        if temp_dir is not None:
            temp_dir.cleanup()


if __name__ == "__main__":
    raise SystemExit(main())
