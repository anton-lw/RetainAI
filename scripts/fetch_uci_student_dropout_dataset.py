from __future__ import annotations

import argparse
import csv
import io
import json
import zipfile
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Any
from urllib.request import urlopen


UCI_DATASET_URL = "https://archive.ics.uci.edu/static/public/697/predict+students+dropout+and+academic+success.zip"
DEFAULT_OUTPUT_DIR = Path("data/public/uci-student-dropout")


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


@dataclass(frozen=True)
class DerivedOutcome:
    status: str
    dropout_date: date | None
    completion_date: date | None
    phase: str


def _add_months(start: date, months: int) -> date:
    year = start.year + (start.month - 1 + months) // 12
    month = (start.month - 1 + months) % 12 + 1
    day = min(start.day, 28)
    return date(year, month, day)


def _read_source_rows(dataset_url: str) -> list[dict[str, str]]:
    with urlopen(dataset_url, timeout=60) as response:
        payload = response.read()

    archive = zipfile.ZipFile(io.BytesIO(payload))
    members = archive.namelist()
    csv_name = next((name for name in members if name.lower().endswith(".csv")), None)
    if csv_name is None:
        raise RuntimeError("Downloaded archive did not contain a CSV file.")

    raw_csv = archive.read(csv_name).decode("utf-8-sig", errors="replace")
    reader = csv.DictReader(io.StringIO(raw_csv), delimiter=";")
    return list(reader)


def _bool_from_flag(value: str) -> bool:
    return value.strip() == "1"


def _float_from_value(value: str) -> float:
    return float(value.strip() or 0.0)


def _int_from_value(value: str) -> int:
    return int(float(value.strip() or 0))


def _target_outcome(target: str, enrollment_date: date, index: int) -> DerivedOutcome:
    dropout_date = enrollment_date + timedelta(days=250 + (index % 35))
    completion_date = enrollment_date + timedelta(days=420 + (index % 28))
    normalized = target.strip().lower()
    if normalized == "dropout":
        return DerivedOutcome(
            status="dropped",
            dropout_date=dropout_date,
            completion_date=None,
            phase="Exited after academic disengagement",
        )
    if normalized == "graduate":
        return DerivedOutcome(
            status="completed",
            dropout_date=None,
            completion_date=completion_date,
            phase="Program completed",
        )
    return DerivedOutcome(
        status="active",
        dropout_date=None,
        completion_date=None,
        phase="Second semester continuing",
    )


def _enrollment_date(index: int) -> date:
    cohort_month = index // 90
    within_month_offset = index % 28
    return _add_months(date(2019, 1, 15), cohort_month) + timedelta(days=within_month_offset)


def _region_for(row: dict[str, str]) -> str:
    course_code = _int_from_value(row["Course"])
    return f"Campus cluster {course_code % 6 + 1}"


def _gender_for(row: dict[str, str]) -> str:
    return "Male" if _bool_from_flag(row["Gender"]) else "Female"


def _household_size_for(row: dict[str, str]) -> int:
    age = _int_from_value(row["Age at enrollment"])
    marital_status = _int_from_value(row["Marital status"])
    size = 1
    if marital_status != 1:
        size += 1
    if age >= 28:
        size += 1
    if age >= 35:
        size += 1
    return min(size, 6)


def _household_type_for(row: dict[str, str]) -> str:
    if _bool_from_flag(row["International"]):
        return "student_far_from_support"
    if _bool_from_flag(row["Displaced"]):
        return "student_mobility_disrupted"
    if _bool_from_flag(row["Scholarship holder"]):
        return "scholarship_supported"
    return "standard_student_household"


def _pmt_score_for(row: dict[str, str]) -> float:
    previous_grade = _float_from_value(row["Previous qualification (grade)"])
    admission_grade = _float_from_value(row["Admission grade"])
    debtor_penalty = 9 if _bool_from_flag(row["Debtor"]) else 0
    scholarship_bonus = -4 if _bool_from_flag(row["Scholarship holder"]) else 0
    raw_score = ((previous_grade + admission_grade) / 2.8) - debtor_penalty + scholarship_bonus
    return round(max(5.0, min(raw_score, 95.0)), 2)


def _food_insecurity_for(row: dict[str, str]) -> float:
    unemployment = _float_from_value(row["Unemployment rate"])
    inflation = _float_from_value(row["Inflation rate"])
    debtor = 2.0 if _bool_from_flag(row["Debtor"]) else 0.0
    tuition_risk = 0.0 if _bool_from_flag(row["Tuition fees up to date"]) else 2.5
    scholarship_offset = -1.0 if _bool_from_flag(row["Scholarship holder"]) else 0.0
    value = (unemployment / 3.5) + (inflation / 2.0) + debtor + tuition_risk + scholarship_offset
    return round(max(0.0, min(value, 10.0)), 2)


def _distance_to_service_for(row: dict[str, str]) -> float:
    age = _int_from_value(row["Age at enrollment"])
    distance = 2.5 + (age - 18) * 0.25
    if not _bool_from_flag(row["Daytime/evening attendance\t"]):
        distance += 4.0
    if _bool_from_flag(row["International"]):
        distance += 6.0
    return round(max(1.0, min(distance, 30.0)), 1)


def _delivery_modality_for(row: dict[str, str]) -> str:
    return "in_person_daytime" if _bool_from_flag(row["Daytime/evening attendance\t"]) else "in_person_evening"


def _cohort_for(enrollment_date: date) -> str:
    return f"{enrollment_date.year}-{enrollment_date.year + 1} academic year"


def _progress_ratio(row: dict[str, str], semester: str) -> float:
    enrolled = _int_from_value(row[f"Curricular units {semester} sem (enrolled)"])
    approved = _int_from_value(row[f"Curricular units {semester} sem (approved)"])
    if enrolled <= 0:
        return 0.0
    return approved / enrolled


def _build_beneficiary_row(row: dict[str, str], index: int) -> dict[str, str]:
    enrollment = _enrollment_date(index)
    outcome = _target_outcome(row["Target"], enrollment, index)
    first_ratio = _progress_ratio(row, "1st")
    second_ratio = _progress_ratio(row, "2nd")
    tuition_current = _bool_from_flag(row["Tuition fees up to date"])
    debtor = _bool_from_flag(row["Debtor"])
    risk_markers: list[str] = []
    if debtor:
        risk_markers.append("debtor flag")
    if not tuition_current:
        risk_markers.append("tuition arrears")
    if first_ratio < 0.5:
        risk_markers.append("weak first-semester approvals")
    if second_ratio < 0.5:
        risk_markers.append("weak second-semester approvals")
    if not risk_markers:
        risk_markers.append("steady academic engagement")

    return {
        "external_id": f"UCI-STU-{index + 1:05d}",
        "name": f"Student {index + 1:05d}",
        "region": _region_for(row),
        "enrollment_date": enrollment.isoformat(),
        "status": outcome.status,
        "cohort": _cohort_for(enrollment),
        "phase": outcome.phase,
        "gender": _gender_for(row),
        "household_size": str(_household_size_for(row)),
        "household_type": _household_type_for(row),
        "pmt_score": f"{_pmt_score_for(row):.2f}",
        "food_insecurity_index": f"{_food_insecurity_for(row):.2f}",
        "distance_to_service_km": f"{_distance_to_service_for(row):.1f}",
        "delivery_modality": _delivery_modality_for(row),
        "preferred_contact_channel": "phone",
        "notes": "; ".join(risk_markers),
        "dropout_date": outcome.dropout_date.isoformat() if outcome.dropout_date else "",
        "completion_date": outcome.completion_date.isoformat() if outcome.completion_date else "",
        "modeling_consent_status": "granted",
        "consent_method": "public_open_data_transformation",
        "consent_note": "Public educational dataset transformed into RetainAI-compatible records for evaluation harness testing.",
        "opted_out": "false",
    }


def _event_note(prefix: str, *, successful: bool, response_received: bool, detail: str) -> str:
    status = "successful" if successful else "missed"
    response = "response received" if response_received else "no response"
    return f"{prefix}: {status}; {response}; {detail}"


def _build_event_rows(row: dict[str, str], beneficiary_row: dict[str, str], index: int) -> list[dict[str, str]]:
    enrollment = date.fromisoformat(beneficiary_row["enrollment_date"])
    first_evaluations = _int_from_value(row["Curricular units 1st sem (evaluations)"])
    second_evaluations = _int_from_value(row["Curricular units 2nd sem (evaluations)"])
    first_ratio = _progress_ratio(row, "1st")
    second_ratio = _progress_ratio(row, "2nd")
    tuition_current = _bool_from_flag(row["Tuition fees up to date"])
    debtor = _bool_from_flag(row["Debtor"])
    scholarship = _bool_from_flag(row["Scholarship holder"])
    target = row["Target"].strip().lower()

    first_success = first_ratio >= 0.5 and first_evaluations > 0
    second_success = second_ratio >= 0.5 and second_evaluations > 0
    finance_success = tuition_current and not debtor
    outreach_success = target != "dropout"
    outreach_response = target != "dropout" or scholarship

    events: list[dict[str, str]] = [
        {
            "external_id": beneficiary_row["external_id"],
            "event_date": (enrollment + timedelta(days=7)).isoformat(),
            "event_type": "checkin",
            "successful": "true",
            "response_received": "true",
            "source": "uci_education_dataset",
            "notes": _event_note(
                "Enrollment intake",
                successful=True,
                response_received=True,
                detail=f"application order {row['Application order']} and admission grade {row['Admission grade']}",
            ),
        },
        {
            "external_id": beneficiary_row["external_id"],
            "event_date": (enrollment + timedelta(days=120)).isoformat(),
            "event_type": "session",
            "successful": str(first_success).lower(),
            "response_received": "true" if first_evaluations > 0 else "false",
            "source": "uci_education_dataset",
            "notes": _event_note(
                "First semester review",
                successful=first_success,
                response_received=first_evaluations > 0,
                detail=f"{row['Curricular units 1st sem (approved)']} approved of {row['Curricular units 1st sem (enrolled)']} enrolled units",
            ),
        },
        {
            "external_id": beneficiary_row["external_id"],
            "event_date": (enrollment + timedelta(days=155)).isoformat(),
            "event_type": "checkin",
            "successful": str(finance_success).lower(),
            "response_received": "true" if tuition_current or scholarship else "false",
            "source": "uci_education_dataset",
            "notes": _event_note(
                "Finance check-in",
                successful=finance_success,
                response_received=tuition_current or scholarship,
                detail="tuition current" if tuition_current else "tuition not current or debtor risk present",
            ),
        },
        {
            "external_id": beneficiary_row["external_id"],
            "event_date": (enrollment + timedelta(days=240)).isoformat(),
            "event_type": "session",
            "successful": str(second_success).lower(),
            "response_received": "true" if second_evaluations > 0 else "false",
            "source": "uci_education_dataset",
            "notes": _event_note(
                "Second semester review",
                successful=second_success,
                response_received=second_evaluations > 0,
                detail=f"{row['Curricular units 2nd sem (approved)']} approved of {row['Curricular units 2nd sem (enrolled)']} enrolled units",
            ),
        },
        {
            "external_id": beneficiary_row["external_id"],
            "event_date": (enrollment + timedelta(days=310 + (index % 20))).isoformat(),
            "event_type": "checkin",
            "successful": str(outreach_success).lower(),
            "response_received": str(outreach_response).lower(),
            "source": "uci_education_dataset",
            "notes": _event_note(
                "Retention outreach",
                successful=outreach_success,
                response_received=outreach_response,
                detail="dropout-risk follow-up after semester signals" if target == "dropout" else "student re-engaged or remained enrolled",
            ),
        },
    ]

    if beneficiary_row["dropout_date"]:
        events.append(
            {
                "external_id": beneficiary_row["external_id"],
                "event_date": beneficiary_row["dropout_date"],
                "event_type": "visit",
                "successful": "false",
                "response_received": "false",
                "source": "uci_education_dataset",
                "notes": "Program exited before graduation window.",
            }
        )
    elif beneficiary_row["completion_date"]:
        events.append(
            {
                "external_id": beneficiary_row["external_id"],
                "event_date": beneficiary_row["completion_date"],
                "event_type": "visit",
                "successful": "true",
                "response_received": "true",
                "source": "uci_education_dataset",
                "notes": "Program completed successfully.",
            }
        )
    else:
        events.append(
            {
                "external_id": beneficiary_row["external_id"],
                "event_date": (enrollment + timedelta(days=420 + (index % 21))).isoformat(),
                "event_type": "visit",
                "successful": "true",
                "response_received": "true",
                "source": "uci_education_dataset",
                "notes": "Student remained enrolled at the end of the observation window.",
            }
        )

    return events


def _write_csv(path: Path, headers: list[str], rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=headers)
        writer.writeheader()
        writer.writerows(rows)


def _write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _summarize(rows: list[dict[str, str]], beneficiaries: list[dict[str, str]], events: list[dict[str, str]], output_dir: Path) -> dict[str, Any]:
    targets: dict[str, int] = {}
    for row in rows:
        targets[row["Target"]] = targets.get(row["Target"], 0) + 1

    statuses: dict[str, int] = {}
    for row in beneficiaries:
        statuses[row["status"]] = statuses.get(row["status"], 0) + 1

    return {
        "source": {
            "name": "UCI Predict Students' Dropout and Academic Success",
            "url": UCI_DATASET_URL,
            "license_note": "Public UCI Machine Learning Repository dataset.",
        },
        "output_dir": str(output_dir.resolve()),
        "row_count": len(rows),
        "beneficiary_rows": len(beneficiaries),
        "event_rows": len(events),
        "target_distribution": targets,
        "status_distribution": statuses,
        "transformation_notes": [
            "RetainAI requires beneficiary and event histories; this script preserves the raw UCI file and derives a deterministic operational timeline from semester-level features.",
            "The output is useful for evaluation-harness and ingestion validation, but it is still a public proxy dataset rather than a true NGO operational MIS export.",
            "The region field is a deterministic campus-cluster proxy derived from course code because the source data does not include geographic deployment regions.",
        ],
        "next_step": (
            "Run scripts/run_model_backtest.py with the generated beneficiaries.csv and events.csv to evaluate the model on this public proxy dataset."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Fetch the public UCI student dropout dataset and transform it into RetainAI-compatible beneficiary/event CSV files."
    )
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--dataset-url", default=UCI_DATASET_URL)
    parser.add_argument("--force", action="store_true", help="Overwrite existing output files.")
    args = parser.parse_args()

    output_dir = args.output_dir
    raw_csv_path = output_dir / "raw" / "uci_student_dropout_data.csv"
    beneficiaries_path = output_dir / "retainai" / "beneficiaries.csv"
    events_path = output_dir / "retainai" / "events.csv"
    manifest_path = output_dir / "manifest.json"

    if not args.force and all(path.exists() for path in (raw_csv_path, beneficiaries_path, events_path, manifest_path)):
        print(json.dumps({"status": "skipped", "reason": "output already exists", "output_dir": str(output_dir.resolve())}, indent=2))
        return 0

    rows = _read_source_rows(args.dataset_url)
    beneficiaries: list[dict[str, str]] = []
    events: list[dict[str, str]] = []

    raw_buffer = io.StringIO()
    raw_writer = None
    for index, row in enumerate(rows):
        if raw_writer is None:
            raw_writer = csv.DictWriter(raw_buffer, fieldnames=list(row.keys()), delimiter=";")
            raw_writer.writeheader()
        raw_writer.writerow(row)

        beneficiary_row = _build_beneficiary_row(row, index)
        beneficiaries.append(beneficiary_row)
        events.extend(_build_event_rows(row, beneficiary_row, index))

    _write_text(raw_csv_path, raw_buffer.getvalue())
    _write_csv(beneficiaries_path, BENEFICIARY_HEADERS, beneficiaries)
    _write_csv(events_path, EVENT_HEADERS, events)

    manifest = _summarize(rows, beneficiaries, events, output_dir)
    _write_text(manifest_path, json.dumps(manifest, indent=2))
    print(json.dumps(manifest, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
