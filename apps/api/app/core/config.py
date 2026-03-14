"""Application configuration and environment parsing.

RetainAI has a wide configuration surface because it spans API auth, model
artifacts, privacy keys, connector execution, queue backends, and deployment
runtime controls. This module keeps those settings in one place so operational
behavior is inspectable and reproducible.
"""

from __future__ import annotations

import base64
import hashlib
import json
from functools import lru_cache
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


BASE_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    app_name: str = "RetainAI API"
    environment: str = "development"
    api_prefix: str = "/api/v1"
    database_url: str = f"sqlite:///{(BASE_DIR / 'retainai.db').as_posix()}"
    model_artifact_dir: str = str(BASE_DIR / "artifacts")
    mlflow_tracking_uri: str = f"file:///{(BASE_DIR / 'mlruns').as_posix()}"
    mlflow_experiment_name: str = "retainai-dropout-models"
    jwt_secret_key: str = "change-me-before-production"
    jwt_secret_key_file: str | None = None
    jwt_active_kid: str = "primary"
    jwt_legacy_keys: list[str] = []
    jwt_issuer: str = "retainai"
    jwt_audience: str = "retainai-api"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 720
    session_idle_timeout_minutes: int = 240
    session_touch_interval_seconds: int = 300
    max_active_sessions_per_user: int = 5
    login_rate_limit_attempts: int = 5
    login_rate_limit_window_minutes: int = 15
    privacy_token_key: str | None = None
    privacy_token_key_file: str | None = None
    privacy_token_key_legacy: list[str] = []
    connector_secret_key: str | None = None
    connector_secret_key_file: str | None = None
    connector_secret_key_legacy: list[str] = []
    connector_request_timeout_seconds: int = 30
    connector_max_pages: int = 20
    connector_default_page_size: int = 500
    worker_poll_interval_seconds: int = 10
    job_backend: str = "db"
    job_max_attempts: int = 3
    job_retry_backoff_seconds: int = 45
    redis_url: str = "redis://localhost:6379/0"
    celery_task_always_eager: bool = False
    allowed_origins: list[str] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ]
    cors_allowed_methods: list[str] = ["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"]
    cors_allowed_headers: list[str] = ["Authorization", "Content-Type", "Accept"]
    trusted_hosts: list[str] = ["localhost", "127.0.0.1", "testserver"]
    auto_seed: bool = True
    seed_user_password: str = "retainai-demo"
    deployment_label: str = "local-dev"
    deployment_region: str = "eu-central"
    huggingface_sentiment_enabled: bool = False
    huggingface_sentiment_model: str = "distilbert-base-uncased-finetuned-sst-2-english"
    sso_enabled: bool = False
    sso_mode: str = "header"
    sso_provider_label: str | None = None
    sso_header_email: str = "X-SSO-Email"
    sso_header_name: str = "X-SSO-Name"
    sso_header_role: str = "X-SSO-Role"
    sso_oidc_issuer_url: str | None = None
    sso_oidc_authorize_url: str | None = None
    sso_oidc_token_url: str | None = None
    sso_oidc_userinfo_url: str | None = None
    sso_oidc_jwks_url: str | None = None
    sso_oidc_client_id: str | None = None
    sso_oidc_client_secret: str | None = None
    sso_oidc_scopes: str = "openid profile email"
    sso_oidc_email_claim: str = "email"
    sso_oidc_name_claim: str = "name"
    sso_oidc_role_claim: str = "role"
    sso_oidc_state_ttl_seconds: int = 600
    sso_oidc_allowed_clock_skew_seconds: int = 60
    bootstrap_admin_name: str | None = None
    bootstrap_admin_email: str | None = None
    bootstrap_admin_password: str | None = None
    federated_secret_key: str | None = None
    federated_secret_key_file: str | None = None
    federated_secret_key_legacy: list[str] = []
    federated_clipping_norm: float = 5.0
    federated_noise_multiplier: float = 0.02
    federated_min_updates: int = 2
    federated_update_max_age_seconds: int = 1800
    federated_encrypt_payloads: bool = True
    enforce_runtime_policy: bool = False
    secret_bundle_path: str | None = None
    security_hsts_enabled: bool = False
    security_hsts_max_age: int = 31536000
    security_referrer_policy: str = "no-referrer"
    security_permissions_policy: str = "geolocation=(), microphone=(), camera=()"
    observability_json_logs: bool = True
    observability_log_level: str = "INFO"
    observability_metrics_enabled: bool = True
    observability_metrics_path: str = "/metrics"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @field_validator("allowed_origins", mode="before")
    @classmethod
    def parse_allowed_origins(cls, value: str | list[str]) -> list[str]:
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value

    @field_validator("cors_allowed_methods", "cors_allowed_headers", "trusted_hosts", mode="before")
    @classmethod
    def parse_list_settings(cls, value: str | list[str]) -> list[str]:
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value

    @field_validator(
        "jwt_legacy_keys",
        "privacy_token_key_legacy",
        "connector_secret_key_legacy",
        "federated_secret_key_legacy",
        mode="before",
    )
    @classmethod
    def parse_key_lists(cls, value: str | list[str] | None) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return [item for item in value if item]

    def _read_secret_bundle(self) -> dict[str, object]:
        if not self.secret_bundle_path:
            return {}
        path = Path(self.secret_bundle_path)
        if not path.exists():
            return {}
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {}
        return payload if isinstance(payload, dict) else {}

    def _resolve_secret(self, explicit: str | None, file_path: str | None, bundle_key: str) -> str | None:
        if explicit and explicit.strip():
            return explicit.strip()
        if file_path:
            path = Path(file_path)
            if path.exists():
                raw = path.read_text(encoding="utf-8").strip()
                if raw:
                    return raw
        bundle = self._read_secret_bundle()
        bundle_value = bundle.get(bundle_key)
        if isinstance(bundle_value, str) and bundle_value.strip():
            return bundle_value.strip()
        return None

    def _derive_keys(self, primary: str | None, legacy: list[str]) -> list[str]:
        resolved = []
        for item in [primary, *legacy]:
            if item and item not in resolved:
                digest = hashlib.sha256(item.encode("utf-8")).digest()
                resolved.append(base64.urlsafe_b64encode(digest).decode("utf-8"))
        return resolved

    @property
    def resolved_jwt_secret_key(self) -> str:
        explicit = None if self.jwt_secret_key == "change-me-before-production" else self.jwt_secret_key
        return self._resolve_secret(explicit, self.jwt_secret_key_file, "JWT_SECRET_KEY") or self.jwt_secret_key

    @property
    def resolved_connector_secret_key(self) -> str:
        return self._resolve_secret(self.connector_secret_key, self.connector_secret_key_file, "CONNECTOR_SECRET_KEY") or self.resolved_jwt_secret_key

    @property
    def resolved_privacy_token_key(self) -> str:
        return self._resolve_secret(self.privacy_token_key, self.privacy_token_key_file, "PRIVACY_TOKEN_KEY") or self.resolved_jwt_secret_key

    @property
    def resolved_federated_secret_key(self) -> str:
        return self._resolve_secret(self.federated_secret_key, self.federated_secret_key_file, "FEDERATED_SECRET_KEY") or self.resolved_jwt_secret_key

    @property
    def jwt_key_ring(self) -> dict[str, str]:
        key_ring = {self.jwt_active_kid: self.resolved_jwt_secret_key}
        for index, key in enumerate(self.jwt_legacy_keys, start=1):
            if key and key not in key_ring.values():
                key_ring[f"legacy-{index}"] = key
        return key_ring

    @property
    def derived_connector_secret_key(self) -> str:
        raw_secret = self.resolved_connector_secret_key
        digest = hashlib.sha256(raw_secret.encode("utf-8")).digest()
        return base64.urlsafe_b64encode(digest).decode("utf-8")

    @property
    def derived_connector_secret_keys(self) -> list[str]:
        return self._derive_keys(self.resolved_connector_secret_key, self.connector_secret_key_legacy)

    @property
    def derived_privacy_token_key(self) -> str:
        raw_secret = self.resolved_privacy_token_key
        digest = hashlib.sha256(raw_secret.encode("utf-8")).digest()
        return base64.urlsafe_b64encode(digest).decode("utf-8")

    @property
    def derived_privacy_token_keys(self) -> list[str]:
        return self._derive_keys(self.resolved_privacy_token_key, self.privacy_token_key_legacy)

    @property
    def derived_federated_secret_key(self) -> str:
        raw_secret = self.resolved_federated_secret_key
        digest = hashlib.sha256(raw_secret.encode("utf-8")).digest()
        return base64.urlsafe_b64encode(digest).decode("utf-8")

    @property
    def derived_federated_secret_keys(self) -> list[str]:
        return self._derive_keys(self.resolved_federated_secret_key, self.federated_secret_key_legacy)


@lru_cache
def get_settings() -> Settings:
    return Settings()
