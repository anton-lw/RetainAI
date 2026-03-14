"""Connector and integration secret management helpers.

RetainAI stores external-system credentials in encrypted form rather than plain
text. This module provides the small set of primitives used to encrypt,
decrypt, rotate, and mask those values before they appear in UI responses or
connector lifecycle operations.
"""

from __future__ import annotations

from cryptography.fernet import Fernet, MultiFernet

from app.core.config import get_settings


settings = get_settings()
fernets = [Fernet(key.encode("utf-8")) for key in settings.derived_connector_secret_keys]
fernet = MultiFernet(fernets)


def encrypt_secret(value: str | None) -> str | None:
    if value is None or not value.strip():
        return None
    return fernet.encrypt(value.strip().encode("utf-8")).decode("utf-8")


def decrypt_secret(value: str | None) -> str | None:
    if value is None or not value.strip():
        return None
    return fernet.decrypt(value.encode("utf-8")).decode("utf-8")


def mask_secret(value: str | None) -> str | None:
    if value is None or not value.strip():
        return None
    visible_tail = value[-4:] if len(value) > 4 else value
    return f"{'*' * max(len(value) - len(visible_tail), 4)}{visible_tail}"
