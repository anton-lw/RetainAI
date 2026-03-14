"""Development seed data for local demos, tests, and maintainer onboarding.

The seed path is intentionally richer than a trivial fixture set. It creates a
small but representative operational environment with:

- users across the supported roles
- one or more programs with operational settings
- beneficiaries, events, and interventions
- governance and workflow states needed by the queue UI

Maintainers should treat this module as convenience scaffolding, not as a
reference for real program assumptions or production-safe synthetic data.
"""

from __future__ import annotations

import random
from datetime import date, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.time import utc_now
from app.models import Beneficiary, Intervention, MonitoringEvent, Program, User
from app.services.auth import (
    ROLE_ADMIN,
    ROLE_COUNTRY_DIRECTOR,
    ROLE_FIELD_COORDINATOR,
    ROLE_ME_OFFICER,
    hash_password,
    normalize_email,
)


FIRST_NAMES = [
    "Fatima",
    "Amina",
    "Moses",
    "Grace",
    "Rahima",
    "John",
    "Halima",
    "Neema",
    "Abel",
    "Mariam",
    "Joseph",
    "Lina",
    "Noor",
    "Esther",
    "David",
    "Sarah",
    "Ibrahim",
    "Joyce",
]

LAST_NAMES = [
    "Idris",
    "Noor",
    "Okello",
    "Nyathi",
    "Begum",
    "Omari",
    "Yusuf",
    "Salum",
    "Kintu",
    "Hassan",
    "Mwangi",
    "Bwire",
    "Ahmed",
    "Atieno",
    "Niyonsenga",
]


PROGRAM_SPECS = [
    {
        "name": "Resilience Cash Grant",
        "program_type": "Cash Transfer",
        "country": "Kenya",
        "delivery_modality": "Mobile money",
        "regions": {
            "Northern Region": 0.78,
            "River Belt": 0.52,
            "Lake District": 0.41,
        },
        "phase_labels": ["Month 1 onboarding", "Month 3 onboarding", "Month 5 transfer cycle", "Month 6 transfer cycle"],
        "event_type": "payment_collection",
        "risk_notes": ["harvest migration risk", "food insecurity reported", "long travel to payout point"],
        "action_types": ["Call completed", "Cash barrier follow-up", "Field visit queued"],
    },
    {
        "name": "Bridge Scholarship",
        "program_type": "Education",
        "country": "Bangladesh",
        "delivery_modality": "School-based support",
        "regions": {
            "Lake District": 0.44,
            "Urban South": 0.58,
            "Northern Corridor": 0.63,
        },
        "phase_labels": ["Primary to secondary", "Term break", "Exam month", "Re-entry month"],
        "event_type": "attendance",
        "risk_notes": ["fee pressure", "term break absence", "seasonal labor pressure"],
        "action_types": ["Caregiver call", "School visit", "Transition counselor assigned"],
    },
    {
        "name": "Safe Motherhood Continuity",
        "program_type": "Health",
        "country": "Rwanda",
        "delivery_modality": "Clinic follow-up",
        "regions": {
            "Eastern Corridor": 0.72,
            "Coastal Zone": 0.54,
            "Central District": 0.39,
        },
        "phase_labels": ["Visit 2 planned", "Post-visit 2", "Visit 4 planned", "Postnatal follow-up"],
        "event_type": "clinic_visit",
        "risk_notes": ["transport barrier", "illness reported", "relocation noted"],
        "action_types": ["CHW outreach", "Home visit queued", "Midwife phone call"],
    },
]

CASE_WORKERS = [
    "Grace Atieno",
    "Moses Niyonsenga",
    "Amina Owino",
    "Daniel Noor",
    "Ruth Kintu",
    "Samuel Omari",
]


DEMO_USERS = [
    {
        "full_name": "Amina Owino",
        "email": "admin@retainai.local",
        "role": ROLE_ADMIN,
    },
    {
        "full_name": "Daniel Noor",
        "email": "me.officer@retainai.local",
        "role": ROLE_ME_OFFICER,
    },
    {
        "full_name": "Grace Atieno",
        "email": "field.coordinator@retainai.local",
        "role": ROLE_FIELD_COORDINATOR,
    },
    {
        "full_name": "Moses Niyonsenga",
        "email": "country.director@retainai.local",
        "role": ROLE_COUNTRY_DIRECTOR,
    },
]


def ensure_demo_users(db: Session) -> None:
    settings = get_settings()

    for user_payload in DEMO_USERS:
        existing = db.scalar(select(User).where(User.email == normalize_email(user_payload["email"])))
        if existing is not None:
            continue

        db.add(
            User(
                full_name=user_payload["full_name"],
                email=normalize_email(user_payload["email"]),
                role=user_payload["role"],
                password_hash=hash_password(settings.seed_user_password),
                is_active=True,
            )
        )

    db.commit()


def seed_database(db: Session) -> None:
    ensure_demo_users(db)

    existing_programs = db.scalar(select(func.count(Program.id)))
    if existing_programs and existing_programs > 0:
        return

    rng = random.Random(42)
    today = date.today()

    for spec in PROGRAM_SPECS:
        program = Program(
            name=spec["name"],
            program_type=spec["program_type"],
            country=spec["country"],
            delivery_modality=spec["delivery_modality"],
            status="active",
        )
        db.add(program)
        db.flush()

        regions = list(spec["regions"].keys())
        for index in range(32):
            first_name = FIRST_NAMES[index % len(FIRST_NAMES)]
            last_name = LAST_NAMES[(index * 3) % len(LAST_NAMES)]
            full_name = f"{first_name} {last_name}"
            region = regions[index % len(regions)]
            base_risk = spec["regions"][region]
            enrollment_date = today - timedelta(days=rng.randint(55, 230))
            phase = spec["phase_labels"][index % len(spec["phase_labels"])]
            gender = "Female" if index % 2 == 0 else "Male"
            cohort = f"{today.year - 1 + (index % 2)}-{chr(65 + (index % 3))}"
            household_size = rng.randint(3, 9)
            pmt_score = round(rng.uniform(18, 62), 1)
            food_insecurity_index = round(rng.uniform(1, 7), 1)
            distance_km = round(rng.uniform(1, 18), 1)
            assigned_worker = CASE_WORKERS[index % len(CASE_WORKERS)]
            assigned_site = f"{region} Site {(index % 3) + 1}"

            dropout_roll = base_risk + rng.uniform(-0.15, 0.18)
            months_enrolled = max(2, min(7, (today - enrollment_date).days // 30))

            status = "active"
            dropout_date = None
            completion_date = None

            if months_enrolled >= 4 and dropout_roll > 0.78 and rng.random() < 0.45:
                status = "dropped"
                dropout_date = enrollment_date + timedelta(days=rng.randint(35, months_enrolled * 28))
                if dropout_date > today:
                    dropout_date = today - timedelta(days=rng.randint(7, 21))
            elif months_enrolled >= 5 and dropout_roll < 0.42 and rng.random() < 0.3:
                status = "completed"
                completion_date = enrollment_date + timedelta(days=rng.randint(120, months_enrolled * 30))
                if completion_date > today:
                    completion_date = today - timedelta(days=rng.randint(10, 30))

            current_note = None
            if dropout_roll > 0.65 or status == "dropped":
                current_note = rng.choice(spec["risk_notes"])

            beneficiary = Beneficiary(
                program_id=program.id,
                external_id=f"{program.program_type[:3].upper()}-{index + 1:04d}",
                full_name=full_name,
                gender=gender,
                region=region,
                cohort=cohort,
                phase=phase,
                household_type="Female-headed" if index % 4 == 0 else "Standard",
                delivery_modality=program.delivery_modality,
                enrollment_date=enrollment_date,
                dropout_date=dropout_date,
                completion_date=completion_date,
                status=status,
                household_size=household_size,
                pmt_score=pmt_score,
                food_insecurity_index=food_insecurity_index,
                distance_to_service_km=distance_km,
                preferred_contact_phone=f"+25078{index + 10000:05d}",
                preferred_contact_channel="whatsapp" if program.program_type == "Cash Transfer" else "call",
                assigned_case_worker=assigned_worker,
                assigned_site=assigned_site,
                household_stability_signal=5 if dropout_roll > 0.82 else 4 if dropout_roll > 0.7 and rng.random() < 0.6 else None,
                economic_stress_signal=4 if food_insecurity_index >= 5 else 3 if food_insecurity_index >= 4 and rng.random() < 0.5 else None,
                family_support_signal=4 if index % 7 == 0 and dropout_roll > 0.6 else None,
                health_change_signal=4 if program.program_type == "Health" and dropout_roll > 0.66 else None,
                motivation_signal=4 if dropout_roll > 0.72 else 3 if dropout_roll > 0.58 and rng.random() < 0.4 else None,
                current_note=current_note,
                opted_out=index % 19 == 0,
            )
            db.add(beneficiary)
            db.flush()

            event_count = max(4, months_enrolled * 2)
            for event_index in range(event_count):
                event_date = enrollment_date + timedelta(days=14 * event_index)
                if event_date > today:
                    break
                if dropout_date and event_date > dropout_date:
                    break
                if completion_date and event_date > completion_date:
                    break

                event_risk = base_risk + (event_index * 0.04 if status == "dropped" else 0)
                success_probability = max(0.18, min(0.94, 0.92 - event_risk + rng.uniform(-0.08, 0.07)))
                successful = rng.random() < success_probability
                response_received = successful or rng.random() < max(0.2, 0.72 - event_risk)
                note = None

                if not successful and rng.random() < 0.6:
                    note = rng.choice(spec["risk_notes"])
                elif successful and rng.random() < 0.15:
                    note = "beneficiary reached and confirmed next milestone"

                db.add(
                    MonitoringEvent(
                        beneficiary_id=beneficiary.id,
                        event_date=event_date,
                        event_type=spec["event_type"],
                        successful=successful,
                        response_received=response_received,
                        source="seed",
                        notes=note,
                    )
                )

            if status == "active" and dropout_roll > 0.68 and rng.random() < 0.55:
                workflow_status = "queued"
                verification_status = None
                successful = None
                if rng.random() < 0.33:
                    workflow_status = "attempted"
                elif rng.random() < 0.2:
                    workflow_status = "verified"
                    verification_status = "still_enrolled"
                    successful = True
                db.add(
                    Intervention(
                        beneficiary_id=beneficiary.id,
                        action_type=rng.choice(spec["action_types"]),
                        support_channel="whatsapp" if program.program_type == "Cash Transfer" else "call",
                        status=workflow_status,
                        verification_status=verification_status,
                        assigned_to=assigned_worker,
                        assigned_site=assigned_site,
                        due_at=datetime.combine(today + timedelta(days=rng.randint(1, 7)), datetime.min.time()),
                        note=f"Follow-up triggered after {phase.lower()} risk increase.",
                        successful=successful if successful is not None else None,
                        attempt_count=1 if workflow_status in {"attempted", "verified"} else 0,
                        source="seed_risk_queue",
                        risk_level="High" if dropout_roll > 0.78 else "Medium",
                        priority_rank=(index % 8) + 1,
                        logged_at=utc_now() - timedelta(days=rng.randint(1, 18)),
                        completed_at=utc_now() - timedelta(days=rng.randint(0, 9)) if workflow_status in {"attempted", "verified"} else None,
                        verified_at=utc_now() - timedelta(days=rng.randint(0, 4)) if workflow_status == "verified" else None,
                    )
                )

    db.commit()
