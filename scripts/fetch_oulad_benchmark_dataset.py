from __future__ import annotations

import argparse
import csv
import io
import json
import zipfile
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Any
from urllib.request import urlopen


OULAD_URL = "https://archive.ics.uci.edu/static/public/349/open+university+learning+analytics+dataset.zip"
DEFAULT_OUTPUT_DIR = Path("data/public/oulad-retention-benchmark")
EVENT_BIN_DAYS = 28

BENEFICIARY_HEADERS = [
    "external_id",
    "name",
    "region",
    "enrollment_date",
    "status",
    "cohort",
    "phase",
    "gender",
    "household_size",
    "household_type",
    "pmt_score",
    "food_insecurity_index",
    "distance_to_service_km",
    "delivery_modality",
    "preferred_contact_channel",
    "notes",
    "dropout_date",
    "completion_date",
    "modeling_consent_status",
    "consent_method",
    "consent_note",
    "opted_out",
]

EVENT_HEADERS = [
    "external_id",
    "event_date",
    "event_type",
    "successful",
    "response_received",
    "source",
    "notes",
]


@dataclass
class BeneficiaryContext:
    beneficiary_row: dict[str, str]
    course_start: date
    observation_end: date
    registration_offset: int
    outcome_offset: int


def _presentation_start(code_presentation: str) -> date:
    year = int(code_presentation[:4])
    session = code_presentation[-1].upper()
    if session == "B":
        return date(year, 2, 1)
    if session == "J":
        return date(year, 10, 1)
    return date(year, 1, 1)


def _safe_int(value: str | None, *, default: int = 0) -> int:
    if value is None:
        return default
    stripped = value.strip()
    if not stripped or stripped == "?":
        return default
    return int(float(stripped))


def _safe_float(value: str | None, *, default: float = 0.0) -> float:
    if value is None:
        return default
    stripped = value.strip()
    if not stripped or stripped == "?":
        return default
    return float(stripped)


def _parse_imd_band(imd_band: str) -> float:
    value = imd_band.strip()
    if not value or value == "?":
        return 50.0
    if "-" in value:
        start, end = value.replace("%", "").split("-")
        return (float(start) + float(end)) / 2
    return 50.0


def _read_zip_csv(archive: zipfile.ZipFile, filename: str) -> list[dict[str, str]]:
    with archive.open(filename) as handle:
        text = io.TextIOWrapper(handle, encoding="utf-8-sig", newline="")
        return list(csv.DictReader(text))


def _external_id(row: dict[str, str]) -> str:
    return f"OULAD-{row['code_module']}-{row['code_presentation']}-{row['id_student']}"


def _course_key(row: dict[str, str]) -> tuple[str, str]:
    return (row["code_module"], row["code_presentation"])


def _student_key(row: dict[str, str]) -> tuple[str, str, str]:
    return (row["code_module"], row["code_presentation"], row["id_student"])


def _household_type(age_band: str, highest_education: str, disability: str) -> str:
    if disability == "Y":
        return "disability_supported_household"
    if age_band == "0-35":
        return "working_age_household"
    if age_band == "35-55":
        return "midlife_learning_household"
    if "A Level" in highest_education or "Lower Than" in highest_education:
        return "education_transition_household"
    return "mature_student_household"


def _distance_proxy(region: str, studied_credits: int) -> float:
    base = (sum(ord(character) for character in region) % 90) / 10
    return round(2.0 + base + max(0, studied_credits - 60) / 45, 1)


def _beneficiary_from_row(
    row: dict[str, str],
    *,
    registration: dict[tuple[str, str, str], dict[str, int]],
    course_lengths: dict[tuple[str, str], int],
) -> BeneficiaryContext:
    student_key = _student_key(row)
    reg_meta = registration.get(student_key, {})
    course_key = _course_key(row)
    course_start = _presentation_start(row["code_presentation"])
    module_length = course_lengths.get(course_key, 270)
    registration_offset = reg_meta.get("date_registration", -30)
    unregistration_offset = reg_meta.get("date_unregistration", module_length)
    final_result = row["final_result"].strip()

    enrollment_date = course_start + timedelta(days=registration_offset)
    if final_result == "Withdrawn":
        outcome_offset = unregistration_offset if unregistration_offset != module_length else int(module_length * 0.7)
        dropout_date = course_start + timedelta(days=outcome_offset)
        completion_date = None
        status = "dropped"
        phase = "Exited before module completion"
    else:
        outcome_offset = module_length
        dropout_date = None
        completion_date = course_start + timedelta(days=module_length)
        status = "completed"
        phase = "Module completed"

    gender = "Male" if row["gender"].strip().upper() == "M" else "Female"
    imd_midpoint = _parse_imd_band(row["imd_band"])
    prev_attempts = _safe_int(row["num_of_prev_attempts"])
    studied_credits = _safe_int(row["studied_credits"], default=60)
    pmt_score = round(max(5.0, min(100.0 - imd_midpoint + (4 if row["disability"] == "N" else -2), 95.0)), 2)
    food_insecurity_index = round(
        max(0.0, min((imd_midpoint / 12.5) + prev_attempts * 0.8 + (1.2 if row["disability"] == "Y" else 0.0), 10.0)),
        2,
    )
    notes = (
        f"highest education: {row['highest_education']}; previous attempts: {prev_attempts}; "
        f"imd band: {row['imd_band'] or 'unknown'}; disability: {row['disability']}"
    )

    beneficiary_row = {
        "external_id": _external_id(row),
        "name": f"Learner {row['id_student']}",
        "region": row["region"],
        "enrollment_date": enrollment_date.isoformat(),
        "status": status,
        "cohort": row["code_presentation"],
        "phase": phase,
        "gender": gender,
        "household_size": str(1 + (1 if prev_attempts > 0 else 0) + (1 if row["age_band"] != "0-35" else 0)),
        "household_type": _household_type(row["age_band"], row["highest_education"], row["disability"]),
        "pmt_score": f"{pmt_score:.2f}",
        "food_insecurity_index": f"{food_insecurity_index:.2f}",
        "distance_to_service_km": f"{_distance_proxy(row['region'], studied_credits):.1f}",
        "delivery_modality": "remote_distance_learning",
        "preferred_contact_channel": "phone",
        "notes": notes,
        "dropout_date": dropout_date.isoformat() if dropout_date else "",
        "completion_date": completion_date.isoformat() if completion_date else "",
        "modeling_consent_status": "granted",
        "consent_method": "public_open_data_transformation",
        "consent_note": "Public OULAD dataset transformed into RetainAI-compatible records for evaluation harness testing.",
        "opted_out": "false",
    }

    return BeneficiaryContext(
        beneficiary_row=beneficiary_row,
        course_start=course_start,
        observation_end=dropout_date or completion_date or (course_start + timedelta(days=module_length)),
        registration_offset=registration_offset,
        outcome_offset=outcome_offset,
    )


def _bin_index(day_offset: int) -> int:
    return day_offset // EVENT_BIN_DAYS


def _date_from_bin(course_start: date, bin_number: int, latest_offset: int) -> date:
    return course_start + timedelta(days=max(latest_offset, (bin_number + 1) * EVENT_BIN_DAYS - 1))


def _serialize_bool(value: bool) -> str:
    return "true" if value else "false"


def _write_csv(path: Path, headers: list[str], rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=headers)
        writer.writeheader()
        writer.writerows(rows)


def _write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Fetch the public OULAD dataset and transform it into a harsher RetainAI benchmark with beneficiary and event histories."
    )
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--dataset-url", default=OULAD_URL)
    parser.add_argument("--force", action="store_true", help="Overwrite existing transformed files.")
    args = parser.parse_args()

    output_dir = args.output_dir
    raw_dir = output_dir / "raw"
    transformed_dir = output_dir / "retainai"
    beneficiaries_path = transformed_dir / "beneficiaries.csv"
    events_path = transformed_dir / "events.csv"
    manifest_path = output_dir / "manifest.json"
    raw_zip_path = raw_dir / "oulad.zip"

    if not args.force and all(path.exists() for path in (beneficiaries_path, events_path, manifest_path, raw_zip_path)):
        print(json.dumps({"status": "skipped", "reason": "output already exists", "output_dir": str(output_dir.resolve())}, indent=2))
        return 0

    with urlopen(args.dataset_url, timeout=90) as response:
        payload = response.read()
    raw_dir.mkdir(parents=True, exist_ok=True)
    raw_zip_path.write_bytes(payload)

    archive = zipfile.ZipFile(io.BytesIO(payload))
    course_rows = _read_zip_csv(archive, "courses.csv")
    student_rows = _read_zip_csv(archive, "studentInfo.csv")
    registration_rows = _read_zip_csv(archive, "studentRegistration.csv")
    assessment_rows = _read_zip_csv(archive, "assessments.csv")
    student_assessment_rows = _read_zip_csv(archive, "studentAssessment.csv")
    vle_rows = _read_zip_csv(archive, "vle.csv")

    course_lengths = {
        (row["code_module"], row["code_presentation"]): _safe_int(row["module_presentation_length"], default=270)
        for row in course_rows
    }
    registration = {
        _student_key(row): {
            "date_registration": _safe_int(row["date_registration"], default=-30),
            "date_unregistration": _safe_int(
                row["date_unregistration"],
                default=course_lengths.get((row["code_module"], row["code_presentation"]), 270),
            ),
        }
        for row in registration_rows
    }
    assessment_meta = {
        row["id_assessment"]: {
            "assessment_type": row["assessment_type"],
            "due_date": _safe_int(row["date"], default=0),
            "weight": _safe_float(row["weight"], default=0.0),
            "course_key": (row["code_module"], row["code_presentation"]),
        }
        for row in assessment_rows
    }
    activity_types = {row["id_site"]: row["activity_type"] or "resource" for row in vle_rows}

    contexts: dict[tuple[str, str, str], BeneficiaryContext] = {}
    beneficiaries: list[dict[str, str]] = []
    result_distribution: Counter[str] = Counter()
    for row in student_rows:
        context = _beneficiary_from_row(row, registration=registration, course_lengths=course_lengths)
        contexts[_student_key(row)] = context
        beneficiaries.append(context.beneficiary_row)
        result_distribution[row["final_result"]] += 1

    activity_agg: dict[tuple[str, str, str, int], dict[str, Any]] = {}
    with archive.open("studentVle.csv") as handle:
        text = io.TextIOWrapper(handle, encoding="utf-8-sig", newline="")
        for row in csv.DictReader(text):
            student_key = _student_key(row)
            context = contexts.get(student_key)
            if context is None:
                continue
            day_offset = _safe_int(row["date"], default=0)
            if day_offset > context.outcome_offset:
                continue
            bucket = _bin_index(day_offset)
            agg_key = (*student_key, bucket)
            stats = activity_agg.setdefault(
                agg_key,
                {
                    "clicks": 0,
                    "records": 0,
                    "latest_offset": day_offset,
                    "activity_counts": Counter(),
                },
            )
            stats["clicks"] += _safe_int(row["sum_click"], default=0)
            stats["records"] += 1
            stats["latest_offset"] = max(stats["latest_offset"], day_offset)
            stats["activity_counts"][activity_types.get(row["id_site"], "resource")] += 1

    assessment_agg: dict[tuple[str, str, str, int], dict[str, Any]] = {}
    for row in student_assessment_rows:
        assessment = assessment_meta.get(row["id_assessment"])
        if assessment is None:
            continue
        student_key = (assessment["course_key"][0], assessment["course_key"][1], row["id_student"])
        context = contexts.get(student_key)
        if context is None:
            continue
        submission_offset = _safe_int(row["date_submitted"], default=assessment["due_date"])
        if submission_offset > context.outcome_offset:
            continue
        bucket = _bin_index(submission_offset)
        agg_key = (*student_key, bucket)
        stats = assessment_agg.setdefault(
            agg_key,
            {
                "count": 0,
                "score_total": 0.0,
                "pass_count": 0,
                "latest_offset": submission_offset,
                "late_count": 0,
                "type_counts": Counter(),
            },
        )
        score = _safe_float(row["score"], default=0.0)
        stats["count"] += 1
        stats["score_total"] += score
        stats["pass_count"] += 1 if score >= 40.0 else 0
        stats["latest_offset"] = max(stats["latest_offset"], submission_offset)
        stats["late_count"] += 1 if submission_offset > assessment["due_date"] else 0
        stats["type_counts"][assessment["assessment_type"]] += 1

    events: list[dict[str, str]] = []
    for student_key, context in contexts.items():
        events.append(
            {
                "external_id": context.beneficiary_row["external_id"],
                "event_date": context.beneficiary_row["enrollment_date"],
                "event_type": "checkin",
                "successful": "true",
                "response_received": "true",
                "source": "oulad_registration",
                "notes": f"Registration at offset {context.registration_offset} days from presentation start.",
            }
        )

    for agg_key, stats in activity_agg.items():
        student_key = (agg_key[0], agg_key[1], agg_key[2])
        context = contexts[student_key]
        dominant_activity = stats["activity_counts"].most_common(1)[0][0] if stats["activity_counts"] else "resource"
        events.append(
            {
                "external_id": context.beneficiary_row["external_id"],
                "event_date": _date_from_bin(context.course_start, agg_key[3], stats["latest_offset"]).isoformat(),
                "event_type": "session",
                "successful": _serialize_bool(stats["clicks"] >= 30 or stats["records"] >= 4),
                "response_received": "true",
                "source": "oulad_vle",
                "notes": f"Learning-platform activity: {stats['clicks']} clicks across {stats['records']} interactions; dominant activity {dominant_activity}.",
            }
        )

    for agg_key, stats in assessment_agg.items():
        student_key = (agg_key[0], agg_key[1], agg_key[2])
        context = contexts[student_key]
        dominant_type = stats["type_counts"].most_common(1)[0][0] if stats["type_counts"] else "assessment"
        average_score = stats["score_total"] / max(stats["count"], 1)
        events.append(
            {
                "external_id": context.beneficiary_row["external_id"],
                "event_date": _date_from_bin(context.course_start, agg_key[3], stats["latest_offset"]).isoformat(),
                "event_type": "visit",
                "successful": _serialize_bool(average_score >= 40.0),
                "response_received": "true",
                "source": "oulad_assessment",
                "notes": (
                    f"{stats['count']} {dominant_type} submissions; average score {average_score:.1f}; "
                    f"{stats['late_count']} late submissions."
                ),
            }
        )

    for student_key, context in contexts.items():
        beneficiary = context.beneficiary_row
        final_date = beneficiary["dropout_date"] or beneficiary["completion_date"]
        final_status = "Learner withdrew from the module." if beneficiary["status"] == "dropped" else "Learner reached the module outcome window."
        events.append(
            {
                "external_id": beneficiary["external_id"],
                "event_date": final_date,
                "event_type": "outcome",
                "successful": _serialize_bool(beneficiary["status"] != "dropped"),
                "response_received": _serialize_bool(beneficiary["status"] != "dropped"),
                "source": "oulad_outcome",
                "notes": final_status,
            }
        )

    events.sort(key=lambda row: (row["external_id"], row["event_date"], row["event_type"]))
    _write_csv(beneficiaries_path, BENEFICIARY_HEADERS, beneficiaries)
    _write_csv(events_path, EVENT_HEADERS, events)

    manifest = {
        "source": {
            "name": "Open University Learning Analytics Dataset",
            "url": OULAD_URL,
            "license_note": "Public UCI Machine Learning Repository dataset.",
        },
        "output_dir": str(output_dir.resolve()),
        "beneficiary_rows": len(beneficiaries),
        "event_rows": len(events),
        "result_distribution": dict(result_distribution),
        "status_distribution": dict(Counter(row["status"] for row in beneficiaries)),
        "event_type_distribution": dict(Counter(row["event_type"] for row in events)),
        "transformation_notes": [
            "This benchmark uses true multi-table activity history from OULAD rather than a single flat outcome table.",
            "Monthly learning-platform activity and assessment summaries are converted into RetainAI session and visit events.",
            "Withdrawn learners become dropout labels; pass, distinction, and fail outcomes are treated as program-complete observations rather than dropouts.",
        ],
    }
    _write_text(manifest_path, json.dumps(manifest, indent=2))
    print(json.dumps(manifest, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
