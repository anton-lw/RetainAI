from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date
import os
from pathlib import Path


@dataclass
class ValidationIssue:
    severity: str
    message: str


def _parse_date(value: str) -> date | None:
    if not value:
        return None
    return date.fromisoformat(value)


def _ensure_api_import_path() -> None:
    api_dir = Path(__file__).resolve().parents[1] / "apps" / "api"
    if str(api_dir) not in os.sys.path:
        os.sys.path.insert(0, str(api_dir))


def validate_bundle(beneficiaries_file: Path, events_file: Path) -> dict[str, object]:
    _ensure_api_import_path()
    from app.services.imports import detect_mapping, parse_tabular_bytes

    beneficiary_rows, beneficiary_format = parse_tabular_bytes(beneficiaries_file.read_bytes(), beneficiaries_file.name)
    event_rows, event_format = parse_tabular_bytes(events_file.read_bytes(), events_file.name)

    beneficiary_headers = list(beneficiary_rows[0].keys()) if beneficiary_rows else []
    event_headers = list(event_rows[0].keys()) if event_rows else []
    beneficiary_mapping = detect_mapping(beneficiary_headers, "beneficiaries")
    event_mapping = detect_mapping(event_headers, "events")

    issues: list[ValidationIssue] = []
    required_beneficiary = [field for field in ("external_id", "full_name", "enrollment_date", "region") if not beneficiary_mapping.get(field)]
    required_events = [field for field in ("external_id", "event_date", "event_type") if not event_mapping.get(field)]
    if required_beneficiary:
        issues.append(ValidationIssue("error", f"Missing beneficiary columns for: {', '.join(required_beneficiary)}"))
    if required_events:
        issues.append(ValidationIssue("error", f"Missing event columns for: {', '.join(required_events)}"))

    beneficiary_by_external_id: dict[str, dict[str, str]] = {}
    event_counts: Counter[str] = Counter()
    event_date_counts: dict[str, list[date]] = defaultdict(list)
    cohort_counts: Counter[str] = Counter()
    status_counts: Counter[str] = Counter()

    for row in beneficiary_rows:
        external_id = row.get(beneficiary_mapping.get("external_id") or "", "").strip()
        if not external_id:
            continue
        beneficiary_by_external_id[external_id] = row
        status = (row.get(beneficiary_mapping.get("status") or "", "") or "unknown").strip().lower()
        status_counts[status] += 1
        cohort = (row.get(beneficiary_mapping.get("cohort") or "", "") or "unknown").strip()
        cohort_counts[cohort] += 1

    orphan_events = 0
    for row in event_rows:
        external_id = row.get(event_mapping.get("external_id") or "", "").strip()
        if not external_id:
            continue
        if external_id not in beneficiary_by_external_id:
            orphan_events += 1
            continue
        event_counts[external_id] += 1
        event_date_value = row.get(event_mapping.get("event_date") or "", "").strip()
        parsed_event_date = _parse_date(event_date_value) if event_date_value else None
        if parsed_event_date is not None:
            event_date_counts[external_id].append(parsed_event_date)

    if orphan_events:
        issues.append(ValidationIssue("warning", f"{orphan_events} events reference beneficiaries not present in the beneficiary file."))

    beneficiaries_without_events = sum(1 for external_id in beneficiary_by_external_id if event_counts[external_id] == 0)
    if beneficiaries_without_events:
        issues.append(ValidationIssue("warning", f"{beneficiaries_without_events} beneficiaries have no linked events."))

    labeled_dropouts = 0
    labeled_completions = 0
    missing_outcome_dates = 0
    longitudinally_usable = 0
    event_span_days: list[int] = []

    for external_id, row in beneficiary_by_external_id.items():
        enrollment_date = _parse_date((row.get(beneficiary_mapping.get("enrollment_date") or "", "") or "").strip())
        dropout_date = _parse_date((row.get(beneficiary_mapping.get("dropout_date") or "", "") or "").strip())
        completion_date = _parse_date((row.get(beneficiary_mapping.get("completion_date") or "", "") or "").strip())
        status = (row.get(beneficiary_mapping.get("status") or "", "") or "").strip().lower()
        dates = sorted(event_date_counts.get(external_id, []))
        if dates and enrollment_date is not None:
            event_span_days.append((max(dates) - min(enrollment_date, dates[0])).days)
            if (max(dates) - enrollment_date).days >= 90:
                longitudinally_usable += 1
        if status == "dropped":
            labeled_dropouts += 1
            if dropout_date is None:
                missing_outcome_dates += 1
        if status == "completed":
            labeled_completions += 1
            if completion_date is None:
                missing_outcome_dates += 1

    if labeled_dropouts < 50:
        issues.append(ValidationIssue("warning", f"Only {labeled_dropouts} labeled dropouts found; this is likely too thin for a reliable pilot backtest."))
    if longitudinally_usable < 200:
        issues.append(ValidationIssue("warning", f"Only {longitudinally_usable} beneficiaries have at least 90 days of observed history."))
    if missing_outcome_dates:
        issues.append(ValidationIssue("warning", f"{missing_outcome_dates} beneficiaries have terminal statuses but no explicit dropout/completion date."))
    if len(cohort_counts) <= 1:
        issues.append(ValidationIssue("warning", "The bundle contains only one cohort label, so cross-cohort validation will be limited."))

    readiness = "not_ready"
    if not any(issue.severity == "error" for issue in issues):
        if labeled_dropouts >= 200 and longitudinally_usable >= 500 and len(cohort_counts) >= 2:
            readiness = "shadow_pilot_candidate"
        elif labeled_dropouts >= 50 and longitudinally_usable >= 200:
            readiness = "backtest_ready"
        else:
            readiness = "needs_more_history"

    return {
        "beneficiaries_file": str(beneficiaries_file.resolve()),
        "events_file": str(events_file.resolve()),
        "source_formats": {
            "beneficiaries": beneficiary_format,
            "events": event_format,
        },
        "counts": {
            "beneficiaries": len(beneficiary_rows),
            "events": len(event_rows),
            "dropouts": labeled_dropouts,
            "completions": labeled_completions,
            "beneficiaries_without_events": beneficiaries_without_events,
            "orphans": orphan_events,
        },
        "coverage": {
            "cohorts": dict(cohort_counts),
            "statuses": dict(status_counts),
            "avg_events_per_beneficiary": round(len(event_rows) / max(1, len(beneficiary_rows)), 2),
            "avg_event_span_days": round(sum(event_span_days) / max(1, len(event_span_days)), 1),
            "longitudinally_usable_beneficiaries": longitudinally_usable,
        },
        "mapping": {
            "beneficiaries": beneficiary_mapping,
            "events": event_mapping,
        },
        "issues": [issue.__dict__ for issue in issues],
        "readiness": readiness,
        "next_step": (
            "Run scripts/run_partner_readiness_suite.py on this bundle."
            if readiness != "not_ready"
            else "Fix the schema errors before attempting a backtest."
        ),
    }


def _render_markdown(report: dict[str, object]) -> str:
    counts = report["counts"]
    coverage = report["coverage"]
    issues = report["issues"]
    lines = [
        "# Partner Bundle Validation",
        "",
        f"- Readiness: `{report['readiness']}`",
        f"- Beneficiaries: `{counts['beneficiaries']}`",
        f"- Events: `{counts['events']}`",
        f"- Dropouts: `{counts['dropouts']}`",
        f"- Completions: `{counts['completions']}`",
        f"- Avg events per beneficiary: `{coverage['avg_events_per_beneficiary']}`",
        f"- Avg event span days: `{coverage['avg_event_span_days']}`",
        f"- Longitudinally usable beneficiaries: `{coverage['longitudinally_usable_beneficiaries']}`",
        "",
        "## Issues",
        "",
    ]
    if issues:
        for issue in issues:
            lines.append(f"- `{issue['severity']}`: {issue['message']}")
    else:
        lines.append("- No blocking schema issues detected.")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate whether a beneficiary/events bundle is ready for RetainAI backtesting.")
    parser.add_argument("--beneficiaries-file", type=Path, required=True)
    parser.add_argument("--events-file", type=Path, required=True)
    parser.add_argument("--output-json", type=Path)
    parser.add_argument("--output-md", type=Path)
    args = parser.parse_args()

    report = validate_bundle(args.beneficiaries_file, args.events_file)
    if args.output_json:
        args.output_json.write_text(json.dumps(report, indent=2), encoding="utf-8")
    if args.output_md:
        args.output_md.write_text(_render_markdown(report), encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
