"""Single sign-on helpers for optional enterprise-style deployments.

The project supports local username/password auth by default, but larger NGO or
government deployments may require SSO. This module contains the OIDC exchange
helpers and claim mapping logic so that authentication policy remains isolated
from the rest of the route layer.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode

import httpx
from jose import JWTError, jwt

from app.core.config import get_settings
from app.core.time import utc_now
from app.models import User, generate_uuid
from app.services.auth import ALL_ROLES, upsert_sso_user


settings = get_settings()


class SSOConfigurationError(RuntimeError):
    pass


class SSOAuthenticationError(RuntimeError):
    pass


@dataclass
class OIDCMetadata:
    issuer: str
    authorization_endpoint: str
    token_endpoint: str
    userinfo_endpoint: str | None
    jwks_uri: str | None


def _issuer_url() -> str:
    if not settings.sso_oidc_issuer_url:
        raise SSOConfigurationError("OIDC issuer URL is not configured.")
    return settings.sso_oidc_issuer_url.rstrip("/")


def oidc_enabled() -> bool:
    return settings.sso_enabled and settings.sso_mode == "oidc"


def _load_metadata() -> OIDCMetadata:
    if not oidc_enabled():
        raise SSOConfigurationError("OIDC SSO is not enabled for this deployment.")

    explicit_authorize = settings.sso_oidc_authorize_url
    explicit_token = settings.sso_oidc_token_url
    explicit_userinfo = settings.sso_oidc_userinfo_url
    explicit_jwks = settings.sso_oidc_jwks_url
    if explicit_authorize and explicit_token:
        return OIDCMetadata(
            issuer=_issuer_url(),
            authorization_endpoint=explicit_authorize,
            token_endpoint=explicit_token,
            userinfo_endpoint=explicit_userinfo,
            jwks_uri=explicit_jwks,
        )

    with httpx.Client(timeout=15.0) as client:
        response = client.get(f"{_issuer_url()}/.well-known/openid-configuration")
        response.raise_for_status()
        payload = response.json()
    return OIDCMetadata(
        issuer=str(payload["issuer"]),
        authorization_endpoint=str(payload["authorization_endpoint"]),
        token_endpoint=str(payload["token_endpoint"]),
        userinfo_endpoint=str(payload.get("userinfo_endpoint")) if payload.get("userinfo_endpoint") else None,
        jwks_uri=str(payload.get("jwks_uri")) if payload.get("jwks_uri") else None,
    )


def build_sso_config() -> dict[str, Any]:
    mode = settings.sso_mode if settings.sso_enabled else "disabled"
    interactive = settings.sso_enabled and settings.sso_mode == "oidc"
    provider_label = settings.sso_provider_label or ("OIDC" if mode == "oidc" else "SSO")
    return {
        "enabled": settings.sso_enabled,
        "mode": mode,
        "provider_label": provider_label,
        "interactive": interactive,
        "start_path": f"{settings.api_prefix}/auth/sso/oidc/start" if interactive else (
            f"{settings.api_prefix}/auth/sso/header-login" if settings.sso_enabled else None
        ),
        "callback_supported": interactive,
    }


def build_oidc_state(redirect_uri: str) -> str:
    if not settings.sso_oidc_client_id:
        raise SSOConfigurationError("OIDC client ID is not configured.")
    now = utc_now()
    payload = {
        "iss": "retainai",
        "aud": settings.sso_oidc_client_id,
        "iat": int(now.timestamp()),
        "exp": int(now.timestamp()) + settings.sso_oidc_state_ttl_seconds,
        "nonce": generate_uuid(),
        "redirect_uri": redirect_uri,
        "mode": "oidc",
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def build_oidc_authorization_url(redirect_uri: str) -> dict[str, str]:
    metadata = _load_metadata()
    if not settings.sso_oidc_client_id:
        raise SSOConfigurationError("OIDC client ID is not configured.")
    state = build_oidc_state(redirect_uri)
    query = urlencode(
        {
            "client_id": settings.sso_oidc_client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": settings.sso_oidc_scopes,
            "state": state,
        }
    )
    return {
        "authorization_url": f"{metadata.authorization_endpoint}?{query}",
        "state": state,
        "provider_label": settings.sso_provider_label or "OIDC",
    }


def _verify_state(state_token: str, redirect_uri: str) -> None:
    try:
        payload = jwt.decode(
            state_token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
            audience=settings.sso_oidc_client_id,
        )
    except JWTError as exc:
        raise SSOAuthenticationError("OIDC state token is invalid or expired.") from exc

    if payload.get("mode") != "oidc" or payload.get("redirect_uri") != redirect_uri:
        raise SSOAuthenticationError("OIDC state validation failed.")


def _resolve_signing_key(metadata: OIDCMetadata, id_token: str) -> dict[str, Any] | None:
    if not metadata.jwks_uri:
        return None
    header = jwt.get_unverified_header(id_token)
    key_id = header.get("kid")
    with httpx.Client(timeout=15.0) as client:
        response = client.get(metadata.jwks_uri)
        response.raise_for_status()
        jwks_payload = response.json()
    for key in jwks_payload.get("keys", []):
        if key.get("kid") == key_id:
            return key
    return None


def _claim_value(claims: dict[str, Any], primary: str, fallbacks: list[str]) -> Any:
    if claims.get(primary) not in (None, ""):
        return claims.get(primary)
    for item in fallbacks:
        if claims.get(item) not in (None, ""):
            return claims.get(item)
    return None


def _resolve_identity_claims(metadata: OIDCMetadata, token_payload: dict[str, Any]) -> dict[str, str | None]:
    claims = token_payload
    id_token = token_payload.get("id_token")
    if isinstance(id_token, str):
        signing_key = _resolve_signing_key(metadata, id_token)
        try:
            claims = jwt.decode(
                id_token,
                signing_key or "",
                algorithms=["RS256", "HS256"],
                audience=settings.sso_oidc_client_id,
                issuer=metadata.issuer,
                options={"verify_aud": True},
            )
        except JWTError as exc:
            raise SSOAuthenticationError("OIDC identity token validation failed.") from exc
    elif metadata.userinfo_endpoint and token_payload.get("access_token"):
        with httpx.Client(timeout=15.0) as client:
            response = client.get(
                metadata.userinfo_endpoint,
                headers={"Authorization": f"Bearer {token_payload['access_token']}"},
            )
            response.raise_for_status()
            claims = response.json()
    else:
        raise SSOAuthenticationError("OIDC response did not include a usable identity token or userinfo endpoint.")

    email = _claim_value(claims, settings.sso_oidc_email_claim, ["email", "preferred_username", "upn"])
    if not isinstance(email, str) or "@" not in email:
        raise SSOAuthenticationError("OIDC identity claims did not include a valid email address.")
    name = _claim_value(claims, settings.sso_oidc_name_claim, ["name", "given_name", "preferred_username"])
    role_claim = _claim_value(claims, settings.sso_oidc_role_claim, ["role", "roles"])
    if isinstance(role_claim, list):
        role = next((item for item in role_claim if isinstance(item, str) and item in ALL_ROLES), None)
    else:
        role = role_claim if isinstance(role_claim, str) and role_claim in ALL_ROLES else None
    return {
        "email": email,
        "full_name": name if isinstance(name, str) else None,
        "role": role,
    }


def exchange_oidc_code(db, *, code: str, state_token: str, redirect_uri: str) -> User:
    metadata = _load_metadata()
    if not settings.sso_oidc_client_id or not settings.sso_oidc_client_secret:
        raise SSOConfigurationError("OIDC client credentials are not fully configured.")

    _verify_state(state_token, redirect_uri)
    with httpx.Client(timeout=20.0) as client:
        response = client.post(
            metadata.token_endpoint,
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": redirect_uri,
                "client_id": settings.sso_oidc_client_id,
                "client_secret": settings.sso_oidc_client_secret,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        response.raise_for_status()
        token_payload = response.json()

    identity = _resolve_identity_claims(metadata, token_payload)
    return upsert_sso_user(
        db,
        email=str(identity["email"]),
        full_name=identity["full_name"],
        role=identity["role"],
    )
