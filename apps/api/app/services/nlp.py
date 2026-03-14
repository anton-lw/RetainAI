"""Field-note sentiment helpers with graceful fallback behavior.

Free-text notes are often sparse and deployment environments cannot always
support heavier transformer dependencies. This module therefore offers a small
abstraction that prefers a HuggingFace sentiment pipeline when enabled and
available, but safely falls back to a lightweight lexicon approach so scoring
and training remain usable in constrained installs.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any

from app.core.config import get_settings


settings = get_settings()

POSITIVE_TERMS = {
    "improving",
    "reengaged",
    "stable",
    "attending",
    "collected",
    "recovered",
    "supportive",
    "completed",
    "confirmed",
}
NEGATIVE_TERMS = {
    "missed",
    "barrier",
    "displaced",
    "illness",
    "transport",
    "food insecurity",
    "fees",
    "dropout",
    "conflict",
    "flood",
    "migration",
    "absent",
}


@lru_cache(maxsize=1)
def _load_huggingface_pipeline() -> Any | None:
    if not settings.huggingface_sentiment_enabled:
        return None
    try:  # pragma: no cover - optional runtime dependency
        from transformers import pipeline

        return pipeline(
            "sentiment-analysis",
            model=settings.huggingface_sentiment_model,
        )
    except Exception:
        return None


def _lexicon_sentiment(text: str) -> tuple[float, str]:
    normalized = text.lower()
    positive_hits = sum(1 for token in POSITIVE_TERMS if token in normalized)
    negative_hits = sum(1 for token in NEGATIVE_TERMS if token in normalized)
    total_hits = positive_hits + negative_hits
    if total_hits == 0:
        return 0.0, "neutral"
    score = round((positive_hits - negative_hits) / total_hits, 3)
    if score > 0.15:
        return score, "positive"
    if score < -0.15:
        return score, "negative"
    return score, "neutral"


def analyze_note_sentiment(text: str | None) -> tuple[float, str]:
    if not text or not text.strip():
        return 0.0, "neutral"

    pipeline = _load_huggingface_pipeline()
    if pipeline is not None:
        try:  # pragma: no cover - dependent on local model availability
            result = pipeline(text[:512])[0]
            label = str(result.get("label", "neutral")).lower()
            raw_score = float(result.get("score", 0.0))
            if "neg" in label:
                return round(-raw_score, 3), "negative"
            if "pos" in label:
                return round(raw_score, 3), "positive"
            return round(raw_score - 0.5, 3), "neutral"
        except Exception:
            pass

    return _lexicon_sentiment(text)
