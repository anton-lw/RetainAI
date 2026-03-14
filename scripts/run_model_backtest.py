from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory


def _bootstrap_database(database_url: str | None) -> None:
    if database_url:
        os.environ["DATABASE_URL"] = database_url
    api_dir = Path(__file__).resolve().parents[1] / "apps" / "api"
    if str(api_dir) not in os.sys.path:
        os.sys.path.insert(0, str(api_dir))

    from app.core.config import get_settings
    from app.db import init_db, reset_db_connection

    get_settings.cache_clear()
    reset_db_connection()
    init_db()


def _load_partner_files(
    *,
    beneficiaries_file: Path | None,
    events_file: Path | None,
    program_name: str,
    program_type: str,
    country: str,
) -> None:
    from app.db import SessionLocal
    from app.models import Program
    from app.services.imports import detect_mapping, import_beneficiaries, import_events, parse_tabular_bytes

    with SessionLocal() as session:
        program = Program(
            name=program_name,
            program_type=program_type,
            country=country,
            delivery_modality="Imported historical program",
        )
        session.add(program)
        session.commit()
        session.refresh(program)

        if beneficiaries_file is not None:
            file_bytes = beneficiaries_file.read_bytes()
            rows, source_format = parse_tabular_bytes(file_bytes, beneficiaries_file.name)
            headers = list(rows[0].keys()) if rows else []
            mapping = detect_mapping(headers, "beneficiaries")
            import_beneficiaries(
                session,
                program,
                rows,
                mapping,
                beneficiaries_file.name,
                source_format=source_format,
            )

        if events_file is not None:
            file_bytes = events_file.read_bytes()
            rows, source_format = parse_tabular_bytes(file_bytes, events_file.name)
            headers = list(rows[0].keys()) if rows else []
            mapping = detect_mapping(headers, "events")
            import_events(
                session,
                program,
                rows,
                mapping,
                events_file.name,
                source_format=source_format,
            )


def _render_markdown(report: dict[str, object]) -> str:
    metrics = report["metrics"]
    split = report["split"]
    calibration = report["calibration"]
    lines = [
        "# RetainAI Model Backtest",
        "",
        f"- Status: `{report['status']}`",
        f"- Algorithm: `{report['algorithm']}`",
        f"- Horizon: `{report['horizon_days']}` days",
        f"- Samples evaluated: `{report['samples_evaluated']}`",
        f"- Positive cases: `{report['positive_cases']}`",
        f"- Top-K share: `{report['top_k_share']}` (`{report['top_k_count']}` cases)",
        "",
        "## Split",
        "",
        f"- Train cases: `{split['train_cases']}` from `{split['train_start']}` to `{split['train_end']}`",
        f"- Test cases: `{split['test_cases']}` from `{split['test_start']}` to `{split['test_end']}`",
        f"- Train positive rate: `{split['train_positive_rate']}`",
        f"- Test positive rate: `{split['test_positive_rate']}`",
        "",
        "## Metrics",
        "",
    ]
    for name, payload in metrics.items():
        lines.append(
            f"- `{name}`: `{payload['value']}`"
            + (
                f" (95% CI `{payload['lower_ci']}` to `{payload['upper_ci']}`)"
                if payload["lower_ci"] is not None and payload["upper_ci"] is not None
                else ""
            )
        )
    lines.extend(["", "## Calibration", ""])
    for bucket in calibration:
        lines.append(
            f"- Bin {bucket['bin_index']}: predicted `{bucket['predicted_rate']}`, observed `{bucket['observed_rate']}`, count `{bucket['count']}`"
        )
    lines.extend(["", "## Note", "", str(report["note"]), ""])
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the RetainAI temporal backtest harness.")
    parser.add_argument("--database-url", help="Existing database URL to evaluate.")
    parser.add_argument("--beneficiaries-file", type=Path, help="CSV/XLSX beneficiary export to import before evaluation.")
    parser.add_argument("--events-file", type=Path, help="CSV/XLSX monitoring events export to import before evaluation.")
    parser.add_argument("--program-name", default="Partner Historical Backtest")
    parser.add_argument("--program-type", default="Cash Transfer")
    parser.add_argument("--country", default="Unknown")
    parser.add_argument("--temporal-strategy", choices=("holdout", "rolling"), default="rolling")
    parser.add_argument("--horizon-days", type=int, default=30)
    parser.add_argument("--min-history-days", type=int, default=60)
    parser.add_argument("--holdout-share", type=float, default=0.25)
    parser.add_argument("--rolling-folds", type=int, default=4)
    parser.add_argument("--top-k-share", type=float, default=0.2)
    parser.add_argument("--top-k-capacity", type=int)
    parser.add_argument("--bootstrap-iterations", type=int, default=100)
    parser.add_argument("--output-json", type=Path)
    parser.add_argument("--output-md", type=Path)
    args = parser.parse_args()

    temp_dir: TemporaryDirectory[str] | None = None
    database_url = args.database_url
    if database_url is None and (args.beneficiaries_file or args.events_file):
        temp_dir = TemporaryDirectory()
        database_url = f"sqlite:///{Path(temp_dir.name, 'retainai-backtest.db').as_posix()}"

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
        from app.db import SessionLocal
        from app.services.evaluation import evaluate_model_backtest

        with SessionLocal() as session:
            report = evaluate_model_backtest(
                session,
                schemas.EvaluationRequest(
                    temporal_strategy=args.temporal_strategy,
                    horizon_days=args.horizon_days,
                    min_history_days=args.min_history_days,
                    holdout_share=args.holdout_share,
                    rolling_folds=args.rolling_folds,
                    top_k_share=args.top_k_share,
                    top_k_capacity=args.top_k_capacity,
                    bootstrap_iterations=args.bootstrap_iterations,
                ),
            )

        payload = report.model_dump()
        if args.output_json:
            args.output_json.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        if args.output_md:
            args.output_md.write_text(_render_markdown(payload), encoding="utf-8")

        print(json.dumps(payload, indent=2))
        return 0
    finally:
        if temp_dir is not None:
            from app.db import reset_db_connection

            reset_db_connection()
            temp_dir.cleanup()


if __name__ == "__main__":
    raise SystemExit(main())
