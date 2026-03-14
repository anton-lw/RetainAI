"""Federated-learning update exchange and aggregation helpers.

RetainAI's federated path is designed for deployments that want to share model
improvements without pooling raw beneficiary records. This module manages the
mechanics of exchange:

- round creation and metadata
- encrypted payload handling
- signature and replay protections
- aggregation of submitted updates into a reusable prior

It is a pragmatic implementation rather than a full secure-aggregation system,
so maintainers should read it together with the governance and threat-model
documentation before extending it.
"""

from __future__ import annotations

from collections import defaultdict
import json
from datetime import datetime, timezone
import hashlib
import hmac
from statistics import mean

from cryptography.fernet import Fernet, InvalidToken, MultiFernet
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app import schemas
from app.core.config import get_settings
from app.core.time import utc_now
from app.models import FederatedLearningRound, FederatedModelUpdate, ModelVersion, Program, generate_uuid


settings = get_settings()
federated_fernets = [Fernet(key.encode("utf-8")) for key in settings.derived_federated_secret_keys]
fernet = MultiFernet(federated_fernets)


def _sign_payload(payload: dict[str, object], *, round_nonce: str) -> str:
    body = json.dumps(
        {
            "round_nonce": round_nonce,
            "payload": payload,
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hmac.new(
        settings.derived_federated_secret_key.encode("utf-8"),
        body,
        hashlib.sha256,
    ).hexdigest()


def _update_fingerprint(round_nonce: str, deployment_label: str, source_program_id: str | None, source_nonce: str) -> str:
    return hmac.new(
        settings.derived_federated_secret_key.encode("utf-8"),
        f"{round_nonce}:{deployment_label}:{source_program_id or 'deployment'}:{source_nonce}".encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def _signature_valid(signature: str, payload: dict[str, object], *, round_nonce: str) -> bool:
    body = json.dumps(
        {
            "round_nonce": round_nonce,
            "payload": payload,
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    for key in settings.derived_federated_secret_keys:
        candidate = hmac.new(key.encode("utf-8"), body, hashlib.sha256).hexdigest()
        if hmac.compare_digest(candidate, signature):
            return True
    return False


def _serialize_timestamp(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _parse_timestamp(value: str) -> datetime:
    normalized = value.replace("Z", "+00:00")
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _encrypt_secure_update(payload: dict[str, object]) -> str:
    return fernet.encrypt(json.dumps(payload, sort_keys=True).encode("utf-8")).decode("utf-8")


def _decrypt_secure_update(token: str) -> dict[str, object]:
    try:
        raw = fernet.decrypt(token.encode("utf-8")).decode("utf-8")
    except InvalidToken as exc:
        raise ValueError("Federated secure update could not be decrypted.") from exc
    parsed = json.loads(raw)
    if not isinstance(parsed, dict):
        raise ValueError("Federated secure update payload is invalid.")
    return parsed


def _serialize_update(update: FederatedModelUpdate) -> schemas.FederatedModelUpdateRead:
    return schemas.FederatedModelUpdateRead(
        id=update.id,
        round_id=update.round_id,
        source_program_id=update.source_program_id,
        model_version_id=update.model_version_id,
        deployment_label=update.deployment_label,
        source_nonce=update.source_nonce,
        update_fingerprint=update.update_fingerprint,
        training_rows=update.training_rows,
        positive_rows=update.positive_rows,
        payload=update.payload or {},
        created_at=update.created_at,
        verified_at=update.verified_at,
    )


def _serialize_round(round_record: FederatedLearningRound) -> schemas.FederatedLearningRoundRead:
    return schemas.FederatedLearningRoundRead(
        id=round_record.id,
        round_name=round_record.round_name,
        round_nonce=round_record.round_nonce,
        status=round_record.status,
        aggregation_note=round_record.aggregation_note,
        aggregated_payload=round_record.aggregated_payload,
        created_at=round_record.created_at,
        completed_at=round_record.completed_at,
        updates=[_serialize_update(item) for item in round_record.updates],
    )


def _ensure_round(db: Session, round_name: str) -> FederatedLearningRound:
    round_record = db.scalar(
        select(FederatedLearningRound)
        .options(selectinload(FederatedLearningRound.updates))
        .where(FederatedLearningRound.round_name == round_name)
    )
    if round_record is not None:
        return round_record

    round_record = FederatedLearningRound(round_name=round_name, status="collecting")
    db.add(round_record)
    db.commit()
    db.refresh(round_record)
    return db.scalar(
        select(FederatedLearningRound)
        .options(selectinload(FederatedLearningRound.updates))
        .where(FederatedLearningRound.id == round_record.id)
    ) or round_record


def export_federated_update(
    db: Session,
    *,
    round_name: str,
    deployment_label: str,
    source_program_id: str | None = None,
) -> schemas.FederatedModelUpdateRead:
    round_record = _ensure_round(db, round_name)
    if source_program_id:
        source_program = db.get(Program, source_program_id)
        if source_program is not None and source_program.data_policy is not None and not source_program.data_policy.federated_learning_enabled:
            raise ValueError("Federated learning is disabled for the selected program by data policy.")
    model_version = db.scalar(
        select(ModelVersion).where(ModelVersion.status == "deployed").order_by(ModelVersion.trained_at.desc()).limit(1)
    )
    if model_version is None:
        raise ValueError("A deployed model is required before exporting a federated update.")

    top_driver_weights = {driver["name"]: driver["weight"] for driver in (model_version.top_drivers or []) if "name" in driver}
    metrics = model_version.metrics or {}
    now = utc_now()
    source_nonce = generate_uuid()
    payload = {
        "algorithm": model_version.algorithm,
        "feature_count": len(model_version.features or []),
        "metrics": metrics,
        "top_driver_weights": top_driver_weights,
        "training_profile_keys": sorted((model_version.training_profile or {}).keys())[:20],
        "round_nonce": round_record.round_nonce,
    }
    secure_update = {
        "round_nonce": round_record.round_nonce,
        "source_nonce": source_nonce,
        "issued_at": _serialize_timestamp(now),
        "gradient_sketch": [
            max(
                -settings.federated_clipping_norm,
                min(settings.federated_clipping_norm, float(value)),
            )
            for value in list(top_driver_weights.values())[:20]
        ],
        "clipping_norm": settings.federated_clipping_norm,
        "noise_multiplier": settings.federated_noise_multiplier,
    }
    payload["secure_update_format"] = "fernet_json" if settings.federated_encrypt_payloads else "json"
    payload["secure_update"] = _encrypt_secure_update(secure_update) if settings.federated_encrypt_payloads else secure_update
    payload["signature"] = _sign_payload(secure_update, round_nonce=round_record.round_nonce)
    payload["issued_at"] = secure_update["issued_at"]
    fingerprint = _update_fingerprint(round_record.round_nonce, deployment_label, source_program_id, source_nonce)
    payload["update_fingerprint"] = fingerprint
    update = FederatedModelUpdate(
        round_id=round_record.id,
        source_program_id=source_program_id,
        model_version_id=model_version.id,
        deployment_label=deployment_label,
        source_nonce=source_nonce,
        update_fingerprint=fingerprint,
        training_rows=model_version.training_rows,
        positive_rows=model_version.positive_rows,
        payload=payload,
    )
    db.add(update)
    db.commit()
    db.refresh(update)
    return _serialize_update(update)


def _participant_key(update: FederatedModelUpdate) -> str:
    return f"{update.deployment_label}:{update.source_program_id or 'deployment'}"


def _load_secure_update(round_record: FederatedLearningRound, update: FederatedModelUpdate) -> dict[str, object]:
    payload = update.payload or {}
    if payload.get("round_nonce") != round_record.round_nonce:
        raise ValueError("Round nonce mismatch.")
    secure_raw = payload.get("secure_update")
    secure_format = payload.get("secure_update_format")
    if secure_format == "fernet_json":
        if not isinstance(secure_raw, str):
            raise ValueError("Encrypted federated update is missing.")
        secure_update = _decrypt_secure_update(secure_raw)
    elif isinstance(secure_raw, dict):
        secure_update = secure_raw
    else:
        raise ValueError("Federated secure update payload is invalid.")

    signature = payload.get("signature")
    if not isinstance(signature, str) or not _signature_valid(signature, secure_update, round_nonce=round_record.round_nonce):
        raise ValueError("Federated update signature validation failed.")
    if secure_update.get("round_nonce") != round_record.round_nonce:
        raise ValueError("Federated secure update round nonce does not match.")
    if update.source_nonce and secure_update.get("source_nonce") != update.source_nonce:
        raise ValueError("Federated secure update source nonce does not match.")
    if update.update_fingerprint:
        expected = _update_fingerprint(
            round_record.round_nonce,
            update.deployment_label,
            update.source_program_id,
            str(secure_update.get("source_nonce") or ""),
        )
        if expected != update.update_fingerprint:
            raise ValueError("Federated update fingerprint validation failed.")
    issued_at = secure_update.get("issued_at")
    if not isinstance(issued_at, str):
        raise ValueError("Federated secure update is missing an issue timestamp.")
    issued_dt = _parse_timestamp(issued_at)
    if (utc_now() - issued_dt).total_seconds() > settings.federated_update_max_age_seconds:
        raise ValueError("Federated secure update is too old for aggregation.")
    return secure_update


def aggregate_federated_round(db: Session, round_name: str, *, close_round: bool = True) -> schemas.FederatedLearningRoundRead:
    round_record = db.scalar(
        select(FederatedLearningRound)
        .options(selectinload(FederatedLearningRound.updates))
        .where(FederatedLearningRound.round_name == round_name)
    )
    if round_record is None:
        raise ValueError("Federated learning round not found.")
    if not round_record.updates:
        raise ValueError("No updates have been submitted for this federated learning round.")

    if len(round_record.updates) < settings.federated_min_updates:
        raise ValueError(
            f"At least {settings.federated_min_updates} signed updates are required before aggregation."
        )
    if round_record.status == "completed":
        raise ValueError("This federated learning round has already been completed.")

    algorithm_counter: defaultdict[str, int] = defaultdict(int)
    weighted_metrics: defaultdict[str, list[float]] = defaultdict(list)
    driver_weights: defaultdict[str, list[float]] = defaultdict(list)
    secure_vectors: list[list[float]] = []
    rejected_updates: list[dict[str, str]] = []
    participant_keys: set[str] = set()
    total_rows = 0
    total_positive = 0

    for update in round_record.updates:
        participant_key = _participant_key(update)
        if participant_key in participant_keys:
            rejected_updates.append({"update_id": update.id, "reason": "Duplicate deployment submission"})
            continue
        payload = update.payload or {}
        try:
            secure_update = _load_secure_update(round_record, update)
        except ValueError as exc:
            rejected_updates.append({"update_id": update.id, "reason": str(exc)})
            continue
        participant_keys.add(participant_key)
        algorithm_counter[str(payload.get("algorithm", "unknown"))] += 1
        total_rows += update.training_rows
        total_positive += update.positive_rows
        metrics = payload.get("metrics", {})
        if isinstance(metrics, dict):
            for key, value in metrics.items():
                if isinstance(value, (int, float)):
                    weighted_metrics[key].append(float(value))
        top_driver_weights = payload.get("top_driver_weights", {})
        if isinstance(top_driver_weights, dict):
            for key, value in top_driver_weights.items():
                if isinstance(value, (int, float)):
                    driver_weights[str(key)].append(float(value))
        gradient_sketch = secure_update.get("gradient_sketch", [])
        if isinstance(gradient_sketch, list):
            secure_vectors.append([float(value) for value in gradient_sketch if isinstance(value, (int, float))])
        update.verified_at = utc_now()
        db.add(update)

    if len(secure_vectors) < settings.federated_min_updates:
        raise ValueError("Not enough verified federated updates remain after signature and replay checks.")

    aggregated_payload = {
        "preferred_algorithm": max(algorithm_counter, key=algorithm_counter.get),
        "participant_updates": len(round_record.updates),
        "verified_updates": len(secure_vectors),
        "rejected_updates": rejected_updates,
        "total_training_rows": total_rows,
        "total_positive_rows": total_positive,
        "mean_metrics": {key: round(mean(values), 4) for key, values in weighted_metrics.items()},
        "driver_priors": {key: round(mean(values), 4) for key, values in sorted(driver_weights.items())[:12]},
        "secure_gradient_prior": [
            round(mean(values), 6) for values in zip(*secure_vectors, strict=False)
        ] if secure_vectors else [],
    }
    round_record.aggregated_payload = aggregated_payload
    round_record.aggregation_note = (
        f"Aggregated {len(round_record.updates)} deployment updates for {round_name}. "
        f"Preferred algorithm: {aggregated_payload['preferred_algorithm']}."
    )
    if close_round:
        round_record.status = "completed"
        round_record.completed_at = utc_now()
    else:
        round_record.status = "aggregated"
    db.add(round_record)
    db.commit()
    db.refresh(round_record)
    return _serialize_round(
        db.scalar(
            select(FederatedLearningRound)
            .options(selectinload(FederatedLearningRound.updates))
            .where(FederatedLearningRound.id == round_record.id)
        ) or round_record
    )


def list_federated_rounds(db: Session, limit: int = 10) -> list[schemas.FederatedLearningRoundRead]:
    rounds = db.scalars(
        select(FederatedLearningRound)
        .options(selectinload(FederatedLearningRound.updates))
        .order_by(FederatedLearningRound.created_at.desc())
        .limit(limit)
    ).all()
    return [_serialize_round(item) for item in rounds]


def latest_federated_prior(db: Session) -> dict[str, object] | None:
    round_record = db.scalar(
        select(FederatedLearningRound)
        .where(FederatedLearningRound.aggregated_payload.is_not(None))
        .order_by(FederatedLearningRound.completed_at.desc(), FederatedLearningRound.created_at.desc())
        .limit(1)
    )
    return round_record.aggregated_payload if round_record is not None else None


def build_federated_status(db: Session) -> dict[str, object]:
    rounds = list_federated_rounds(db, limit=5)
    return {
        "enabled": True,
        "deployment_label": settings.deployment_label,
        "recent_rounds": [round_record.model_dump() for round_record in rounds],
        "latest_prior": latest_federated_prior(db),
    }
