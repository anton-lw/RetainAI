"""Synthetic program-bundle generation for demos, stress tests, and evaluation.

This module is intentionally separate from the seed path because it serves a
different purpose. Seeds help developers boot a local environment quickly;
synthetic bundles are used to:

- generate portable demo environments
- stress the evaluation harness under missingness, drift, and fairness shifts
- exercise ingestion and reporting flows without real beneficiary data

These datasets are useful for testing infrastructure and workflows, but they
are not substitutes for real partner-data validation.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date, timedelta
import json
from pathlib import Path
from random import Random
from typing import Any
import csv

import pandas as pd

try:
    from sdv.metadata import SingleTableMetadata
    from sdv.single_table import GaussianCopulaSynthesizer
except Exception:  # pragma: no cover - optional dependency fallback
    GaussianCopulaSynthesizer = None
    SingleTableMetadata = None


PROGRAM_TYPE_BASELINES: dict[str, dict[str, Any]] = {
    "Cash Transfer": {
        "country": "Kenya",
        "regions": ["Northern", "Coastal", "Rift Valley"],
        "phases": ["Onboarding", "Month 2", "Collection"],
        "household_types": ["Female-headed", "Two-parent", "Caregiver-led"],
        "dropout_rate": 0.22,
        "channels": ["sms", "call", "whatsapp"],
    },
    "Education": {
        "country": "Bangladesh",
        "regions": ["Dhaka", "Khulna", "Sylhet"],
        "phases": ["Primary", "Transition", "Secondary"],
        "household_types": ["Two-parent", "Grandparent-led", "Sibling-led"],
        "dropout_rate": 0.3,
        "channels": ["sms", "call", "whatsapp"],
    },
    "Health": {
        "country": "Uganda",
        "regions": ["Kampala", "Gulu", "Mbale"],
        "phases": ["Enrollment", "Refill", "Postnatal"],
        "household_types": ["Single adult", "Two-parent", "Extended family"],
        "dropout_rate": 0.35,
        "channels": ["call", "visit", "whatsapp"],
    },
}


@dataclass(frozen=True)
class SyntheticStressScenario:
    name: str
    description: str
    dropout_multiplier: float = 1.0
    missingness_rate: float = 0.0
    event_failure_bias: float = 0.0
    response_penalty: float = 0.0
    shock_region_share: float = 0.0
    shock_dropout_penalty: float = 0.0
    fairness_group: str | None = None
    fairness_dropout_penalty: float = 0.0
    fairness_event_penalty: float = 0.0
    late_cohort_dropout_penalty: float = 0.0
    thin_history_tail_share: float = 0.0
    duplicate_event_share: float = 0.0


STRESS_SCENARIOS: dict[str, SyntheticStressScenario] = {
    "baseline": SyntheticStressScenario(
        name="baseline",
        description="Balanced baseline synthetic bundle with moderate dropout and stable field operations.",
    ),
    "high_missingness": SyntheticStressScenario(
        name="high_missingness",
        description="Large portions of socioeconomic fields and event responses are missing.",
        missingness_rate=0.28,
        response_penalty=0.18,
    ),
    "regional_shock": SyntheticStressScenario(
        name="regional_shock",
        description="One region experiences a late-program disruption that sharply increases dropout and failed visits.",
        shock_region_share=0.34,
        shock_dropout_penalty=0.35,
        event_failure_bias=0.2,
        late_cohort_dropout_penalty=0.12,
    ),
    "fairness_gap": SyntheticStressScenario(
        name="fairness_gap",
        description="A protected group receives systematically worse follow-up outcomes and higher dropout risk.",
        fairness_group="Female-headed",
        fairness_dropout_penalty=0.24,
        fairness_event_penalty=0.22,
    ),
    "class_imbalance": SyntheticStressScenario(
        name="class_imbalance",
        description="Dropout becomes a rare class, stressing recall and threshold tuning.",
        dropout_multiplier=0.35,
    ),
    "thin_history": SyntheticStressScenario(
        name="thin_history",
        description="A large tail of beneficiaries has very short observation histories.",
        thin_history_tail_share=0.4,
        dropout_multiplier=0.8,
    ),
    "duplicate_noise": SyntheticStressScenario(
        name="duplicate_noise",
        description="Operational sync duplication creates repeated event rows and noisier recent engagement traces.",
        duplicate_event_share=0.18,
        event_failure_bias=0.05,
    ),
}


@dataclass
class SyntheticBundle:
    beneficiaries: list[dict[str, Any]]
    events: list[dict[str, Any]]
    metadata: dict[str, Any]


@dataclass
class SyntheticPortfolioBundle:
    program_name: str
    program_type: str
    country: str
    scenario_name: str
    bundle: SyntheticBundle


def _baseline_rows(program_type: str, rows: int, seed: int) -> pd.DataFrame:
    rng = Random(seed)
    profile = PROGRAM_TYPE_BASELINES.get(program_type, PROGRAM_TYPE_BASELINES["Cash Transfer"])
    baseline: list[dict[str, Any]] = []
    start_date = date(2024, 1, 1)
    for index in range(rows):
        enrolled = start_date + timedelta(days=rng.randint(0, 540))
        status = "dropped" if rng.random() <= profile["dropout_rate"] else "active"
        dropout_date = None
        completion_date = None
        if status == "dropped":
            dropout_date = enrolled + timedelta(days=rng.randint(45, 240))
        elif rng.random() > 0.35:
            status = "completed"
            completion_date = enrolled + timedelta(days=rng.randint(240, 420))
        baseline.append(
            {
                "external_id": f"SYN-{program_type[:3].upper()}-{index + 1:05d}",
                "full_name": f"Synthetic Beneficiary {index + 1}",
                "gender": rng.choice(["female", "male"]),
                "region": rng.choice(profile["regions"]),
                "cohort": f"2024-C{rng.randint(1, 3)}" if enrolled.year == 2024 else f"2025-C{rng.randint(1, 3)}",
                "phase": rng.choice(profile["phases"]),
                "household_type": rng.choice(profile["household_types"]),
                "enrollment_date": enrolled.isoformat(),
                "status": status,
                "dropout_date": dropout_date.isoformat() if dropout_date else None,
                "completion_date": completion_date.isoformat() if completion_date else None,
                "household_size": rng.randint(1, 8),
                "pmt_score": round(rng.uniform(10, 80), 2),
                "food_insecurity_index": round(rng.uniform(0, 10), 2),
                "distance_to_service_km": round(rng.uniform(0.2, 16), 2),
                "preferred_contact_channel": rng.choice(profile["channels"]),
                "current_note": rng.choice(
                    [
                        "Transport barrier discussed with caregiver",
                        "Household coping but income remains unstable",
                        "Recent illness disrupted attendance",
                        "Field staff note stable follow-up",
                        "Seasonal work competing with program visits",
                    ]
                ),
            }
        )
    return pd.DataFrame(baseline)


def _synthesizer_for(df: pd.DataFrame) -> Any | None:
    if GaussianCopulaSynthesizer is None or SingleTableMetadata is None:
        return None
    metadata = SingleTableMetadata()
    metadata.detect_from_dataframe(df)
    synthesizer = GaussianCopulaSynthesizer(metadata)
    synthesizer.fit(df)
    return synthesizer


def _random_date(rng: Random, start: date, max_days: int) -> date:
    return start + timedelta(days=rng.randint(0, max_days))


def _is_missing(value: Any) -> bool:
    if value is None:
        return True
    try:
        return bool(pd.isna(value))
    except Exception:
        return False


def _normalize_optional_date(value: Any) -> str | None:
    if _is_missing(value):
        return None
    if hasattr(value, "date"):
        try:
            return value.date().isoformat()
        except Exception:
            pass
    text = str(value).strip()
    if not text or text.lower() in {"nan", "nat", "none"}:
        return None
    return text[:10]


def _normalize_synthetic_beneficiary(
    row: dict[str, Any],
    *,
    program_type: str,
    index: int,
    rng: Random,
    profile: dict[str, Any],
) -> dict[str, Any]:
    enrollment_date = _normalize_optional_date(row.get("enrollment_date")) or (
        date(2024, 1, 1) + timedelta(days=rng.randint(0, 540))
    ).isoformat()
    status = str(row.get("status") or "active").strip().lower()
    if status not in {"active", "completed", "dropped"}:
        status = "active"
    dropout_date = _normalize_optional_date(row.get("dropout_date"))
    completion_date = _normalize_optional_date(row.get("completion_date"))
    if status == "dropped" and dropout_date is None:
        dropout_date = (date.fromisoformat(enrollment_date) + timedelta(days=rng.randint(60, 220))).isoformat()
        completion_date = None
    elif status == "completed" and completion_date is None:
        completion_date = (date.fromisoformat(enrollment_date) + timedelta(days=rng.randint(240, 380))).isoformat()
        dropout_date = None
    elif status == "active":
        dropout_date = None
        completion_date = None

    def _text(value: Any, fallback: str) -> str:
        return fallback if _is_missing(value) else str(value).strip() or fallback

    def _number(value: Any, fallback: float) -> float | None:
        if _is_missing(value):
            return fallback
        try:
            return float(value)
        except Exception:
            return fallback

    return {
        "external_id": f"SYN-{program_type[:3].upper()}-{index + 1:05d}",
        "full_name": _text(row.get("full_name"), f"Synthetic Beneficiary {index + 1}"),
        "gender": _text(row.get("gender"), rng.choice(["female", "male"])),
        "region": _text(row.get("region"), rng.choice(profile["regions"])),
        "cohort": _text(row.get("cohort"), f"2024-C{rng.randint(1, 3)}"),
        "phase": _text(row.get("phase"), rng.choice(profile["phases"])),
        "household_type": _text(row.get("household_type"), rng.choice(profile["household_types"])),
        "enrollment_date": enrollment_date,
        "status": status,
        "dropout_date": dropout_date,
        "completion_date": completion_date,
        "household_size": int(round(_number(row.get("household_size"), float(rng.randint(1, 8))) or 1)),
        "pmt_score": round(float(_number(row.get("pmt_score"), rng.uniform(10, 80)) or 0.0), 2),
        "food_insecurity_index": round(float(_number(row.get("food_insecurity_index"), rng.uniform(0, 10)) or 0.0), 2),
        "distance_to_service_km": round(float(_number(row.get("distance_to_service_km"), rng.uniform(0.2, 16)) or 0.0), 2),
        "preferred_contact_channel": _text(row.get("preferred_contact_channel"), rng.choice(profile["channels"])),
        "current_note": _text(row.get("current_note"), "Synthetic follow-up note."),
    }


def _event_rows_for_beneficiary(
    beneficiary: dict[str, Any],
    *,
    rng: Random,
    program_type: str,
    scenario: SyntheticStressScenario,
    shock_regions: set[str],
) -> list[dict[str, Any]]:
    enrollment_date = date.fromisoformat(str(beneficiary["enrollment_date"]))
    phase = str(beneficiary.get("phase", "unknown")).lower()
    status = str(beneficiary.get("status", "active")).lower()
    dropout_date = date.fromisoformat(str(beneficiary["dropout_date"])) if beneficiary.get("dropout_date") else None
    completion_date = date.fromisoformat(str(beneficiary["completion_date"])) if beneficiary.get("completion_date") else None
    outcome_date = dropout_date or completion_date or (enrollment_date + timedelta(days=360))
    observation_days = max(90, (outcome_date - enrollment_date).days)
    if scenario.thin_history_tail_share > 0 and rng.random() < scenario.thin_history_tail_share:
        observation_days = min(observation_days, rng.randint(60, 110))

    event_types = ["attendance", "checkin", "visit", "payment_collection"] if program_type == "Cash Transfer" else ["attendance", "checkin", "session", "visit"]
    total_windows = max(3, int(observation_days / 30))
    events: list[dict[str, Any]] = []
    fairness_penalty = 0.0
    if scenario.fairness_group and str(beneficiary.get("household_type")) == scenario.fairness_group:
        fairness_penalty = scenario.fairness_event_penalty
    shock_penalty = scenario.event_failure_bias if str(beneficiary.get("region")) in shock_regions else 0.0

    for window_index in range(total_windows):
        event_date = enrollment_date + timedelta(days=(window_index * 30) + rng.randint(0, 12))
        if event_date > outcome_date:
            break
        failure_probability = 0.18 + scenario.event_failure_bias + fairness_penalty + shock_penalty
        if "transition" in phase and window_index >= 2:
            failure_probability += 0.08
        if status == "dropped" and window_index >= total_windows - 2:
            failure_probability += 0.25
        successful = rng.random() > min(0.92, failure_probability)
        response_received = rng.random() > min(0.95, 0.15 + scenario.response_penalty + fairness_penalty)
        note = rng.choice(
            [
                "Follow-up completed",
                "Transport barrier still active",
                "Caregiver asked for reschedule",
                "Household moved temporarily",
                "Livelihood shock noted by field team",
            ]
        )
        events.append(
            {
                "external_id": beneficiary["external_id"],
                "event_date": event_date.isoformat(),
                "event_type": rng.choice(event_types),
                "successful": successful,
                "response_received": response_received,
                "source": "synthetic",
                "notes": note,
            }
        )

    terminal_event_date = outcome_date
    events.append(
        {
            "external_id": beneficiary["external_id"],
            "event_date": terminal_event_date.isoformat(),
            "event_type": "outcome",
            "successful": status != "dropped",
            "response_received": status != "dropped",
            "source": "synthetic",
            "notes": "Synthetic terminal observation",
        }
    )
    return events


def _apply_stress(
    beneficiaries: list[dict[str, Any]],
    *,
    scenario: SyntheticStressScenario,
    rng: Random,
    profile: dict[str, Any],
) -> tuple[list[dict[str, Any]], set[str]]:
    shock_regions: set[str] = set()
    if scenario.shock_region_share > 0:
        region_count = max(1, int(round(len(profile["regions"]) * scenario.shock_region_share)))
        shock_regions = set(profile["regions"][:region_count])

    for beneficiary in beneficiaries:
        base_dropout = beneficiary.get("status") == "dropped"
        dropout_probability = profile["dropout_rate"] * scenario.dropout_multiplier
        if scenario.fairness_group and beneficiary.get("household_type") == scenario.fairness_group:
            dropout_probability += scenario.fairness_dropout_penalty
        if beneficiary.get("region") in shock_regions:
            dropout_probability += scenario.shock_dropout_penalty
        if str(beneficiary.get("cohort", "")).startswith("2025"):
            dropout_probability += scenario.late_cohort_dropout_penalty
        dropout_probability = min(0.92, max(0.01, dropout_probability))

        enrollment_date = date.fromisoformat(str(beneficiary["enrollment_date"]))
        if rng.random() < dropout_probability:
            beneficiary["status"] = "dropped"
            dropout_date = _random_date(rng, enrollment_date + timedelta(days=50), 240)
            beneficiary["dropout_date"] = dropout_date.isoformat()
            beneficiary["completion_date"] = None
        elif base_dropout:
            beneficiary["status"] = "completed"
            beneficiary["dropout_date"] = None
            beneficiary["completion_date"] = (enrollment_date + timedelta(days=330 + rng.randint(0, 45))).isoformat()
        elif beneficiary.get("status") != "completed" and rng.random() > 0.4:
            beneficiary["status"] = "completed"
            beneficiary["completion_date"] = (enrollment_date + timedelta(days=330 + rng.randint(0, 45))).isoformat()

        if scenario.missingness_rate > 0:
            for field in ("pmt_score", "food_insecurity_index", "distance_to_service_km", "current_note"):
                if rng.random() < scenario.missingness_rate:
                    beneficiary[field] = None if field != "current_note" else ""

    return beneficiaries, shock_regions


def generate_synthetic_bundle(program_type: str, rows: int = 250, seed: int = 42) -> SyntheticBundle:
    return generate_synthetic_stress_bundle(program_type, scenario_name="baseline", rows=rows, seed=seed)


def generate_synthetic_stress_bundle(
    program_type: str,
    *,
    scenario_name: str,
    rows: int = 250,
    seed: int = 42,
) -> SyntheticBundle:
    rng = Random(seed)
    profile = PROGRAM_TYPE_BASELINES.get(program_type, PROGRAM_TYPE_BASELINES["Cash Transfer"])
    scenario = STRESS_SCENARIOS[scenario_name]
    baseline = _baseline_rows(program_type, rows, seed)
    synthesizer = _synthesizer_for(baseline)
    if synthesizer is not None:
        synthetic_df = synthesizer.sample(num_rows=rows)
    else:  # pragma: no cover
        synthetic_df = baseline.sample(n=rows, replace=True, random_state=seed).reset_index(drop=True)

    beneficiaries = [
        _normalize_synthetic_beneficiary(
            row,
            program_type=program_type,
            index=index,
            rng=rng,
            profile=profile,
        )
        for index, row in enumerate(synthetic_df.to_dict(orient="records"))
    ]
    beneficiaries, shock_regions = _apply_stress(beneficiaries, scenario=scenario, rng=rng, profile=profile)

    events: list[dict[str, Any]] = []
    for beneficiary in beneficiaries:
        events.extend(
            _event_rows_for_beneficiary(
                beneficiary,
                rng=rng,
                program_type=program_type,
                scenario=scenario,
                shock_regions=shock_regions,
            )
        )

    if scenario.duplicate_event_share > 0 and events:
        duplicate_count = int(len(events) * scenario.duplicate_event_share)
        for _ in range(duplicate_count):
            events.append(dict(rng.choice(events)))

    metadata = {
        "program_type": program_type,
        "scenario_name": scenario.name,
        "scenario_description": scenario.description,
        "country": profile["country"],
        "rows": len(beneficiaries),
        "event_rows": len(events),
        "shock_regions": sorted(shock_regions),
    }
    return SyntheticBundle(beneficiaries=beneficiaries, events=events, metadata=metadata)


def write_synthetic_bundle_csv(bundle: SyntheticBundle, output_dir: Path) -> dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    beneficiaries_path = output_dir / "beneficiaries.csv"
    events_path = output_dir / "events.csv"
    manifest_path = output_dir / "manifest.json"

    beneficiary_headers = [
        "external_id",
        "full_name",
        "gender",
        "region",
        "cohort",
        "phase",
        "household_type",
        "enrollment_date",
        "status",
        "dropout_date",
        "completion_date",
        "household_size",
        "pmt_score",
        "food_insecurity_index",
        "distance_to_service_km",
        "preferred_contact_channel",
        "current_note",
        "modeling_consent_status",
        "opted_out",
    ]
    event_headers = ["external_id", "event_date", "event_type", "successful", "response_received", "source", "notes"]

    with beneficiaries_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=beneficiary_headers)
        writer.writeheader()
        for row in bundle.beneficiaries:
            payload = dict(row)
            payload.setdefault("modeling_consent_status", "granted")
            payload.setdefault("opted_out", False)
            writer.writerow(payload)

    with events_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=event_headers)
        writer.writeheader()
        for row in bundle.events:
            writer.writerow(row)

    manifest_path.write_text(json.dumps(bundle.metadata, indent=2), encoding="utf-8")
    return {
        "beneficiaries_file": str(beneficiaries_path.resolve()),
        "events_file": str(events_path.resolve()),
        "manifest_file": str(manifest_path.resolve()),
    }


def list_stress_scenarios() -> list[dict[str, str]]:
    return [
        {"name": scenario.name, "description": scenario.description}
        for scenario in STRESS_SCENARIOS.values()
    ]


def generate_synthetic_stress_portfolio(
    *,
    scenario_name: str,
    rows_per_program: int = 250,
    seed: int = 42,
) -> list[SyntheticPortfolioBundle]:
    portfolio: list[SyntheticPortfolioBundle] = []
    for index, (program_type, profile) in enumerate(PROGRAM_TYPE_BASELINES.items()):
        bundle_seed = seed + (index * 101)
        portfolio.append(
            SyntheticPortfolioBundle(
                program_name=f"Synthetic {program_type} {scenario_name.replace('_', ' ').title()}",
                program_type=program_type,
                country=str(profile["country"]),
                scenario_name=scenario_name,
                bundle=generate_synthetic_stress_bundle(
                    program_type,
                    scenario_name=scenario_name,
                    rows=rows_per_program,
                    seed=bundle_seed,
                ),
            )
        )
    return portfolio


def write_synthetic_portfolio_csv(
    portfolio: list[SyntheticPortfolioBundle],
    output_dir: Path,
) -> list[dict[str, str]]:
    manifest_rows: list[dict[str, str]] = []
    for bundle in portfolio:
        bundle_dir = output_dir / bundle.program_type.lower().replace(" ", "-")
        file_map = write_synthetic_bundle_csv(bundle.bundle, bundle_dir)
        manifest_rows.append(
            {
                "program_name": bundle.program_name,
                "program_type": bundle.program_type,
                "country": bundle.country,
                "scenario_name": bundle.scenario_name,
                **file_map,
            }
        )
    manifest_path = output_dir / "portfolio-manifest.json"
    manifest_path.write_text(json.dumps(manifest_rows, indent=2), encoding="utf-8")
    return manifest_rows


def summarize_synthetic_portfolio(rows_per_program: int = 250) -> list[dict[str, Any]]:
    summary: list[dict[str, Any]] = []
    for program_type in PROGRAM_TYPE_BASELINES:
        bundle = generate_synthetic_bundle(program_type, rows=rows_per_program)
        dropped = sum(1 for row in bundle.beneficiaries if row.get("status") == "dropped")
        by_region: dict[str, int] = defaultdict(int)
        for row in bundle.beneficiaries:
            by_region[str(row.get("region", "Unknown"))] += 1
        summary.append(
            {
                "program_type": program_type,
                "beneficiaries": len(bundle.beneficiaries),
                "events": len(bundle.events),
                "dropout_rate": round(dropped / max(1, len(bundle.beneficiaries)), 4),
                "regions": dict(sorted(by_region.items())),
            }
        )
    return summary


def summarize_stress_suite(rows_per_program: int = 250, seed: int = 42) -> list[dict[str, Any]]:
    summary: list[dict[str, Any]] = []
    for program_type in PROGRAM_TYPE_BASELINES:
        for scenario_name in STRESS_SCENARIOS:
            bundle = generate_synthetic_stress_bundle(program_type, scenario_name=scenario_name, rows=rows_per_program, seed=seed)
            dropped = sum(1 for row in bundle.beneficiaries if row.get("status") == "dropped")
            summary.append(
                {
                    "program_type": program_type,
                    "scenario": scenario_name,
                    "beneficiaries": len(bundle.beneficiaries),
                    "events": len(bundle.events),
                    "dropout_rate": round(dropped / max(1, len(bundle.beneficiaries)), 4),
                }
            )
    return summary
