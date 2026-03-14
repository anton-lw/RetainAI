"""Authentication, authorization, and session lifecycle helpers.

This module is the backend security entrypoint used by the FastAPI routes. It
owns:

- password hashing and login verification
- JWT issuance and validation
- session creation, revocation, and last-seen tracking
- role-based access helpers shared across routes

Maintainers debugging access-control behavior should usually start here, then
follow into ``app.main`` for route-level policy usage.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4
from typing import Callable

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.time import utc_now
from app.db import get_db
from app.models import AuditLog, User, UserSession


ROLE_ADMIN = "admin"
ROLE_ME_OFFICER = "me_officer"
ROLE_FIELD_COORDINATOR = "field_coordinator"
ROLE_COUNTRY_DIRECTOR = "country_director"
ALL_ROLES = (
    ROLE_ADMIN,
    ROLE_ME_OFFICER,
    ROLE_FIELD_COORDINATOR,
    ROLE_COUNTRY_DIRECTOR,
)


settings = get_settings()
pwd_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")
bearer_scheme = HTTPBearer(auto_error=False)


def normalize_email(email: str) -> str:
    return email.strip().lower()


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    return pwd_context.verify(password, password_hash)


def get_user_by_email(db: Session, email: str) -> User | None:
    normalized_email = normalize_email(email)
    return db.scalar(select(User).where(User.email == normalized_email))


def authenticate_user(db: Session, email: str, password: str) -> User | None:
    user = get_user_by_email(db, email)
    if user is None or not user.is_active:
        return None
    if not verify_password(password, user.password_hash):
        return None
    return user


def create_access_token(user: User, session: UserSession) -> str:
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=settings.access_token_expire_minutes)
    payload = {
        "sub": user.id,
        "sid": session.id,
        "jti": session.token_jti,
        "email": user.email,
        "role": user.role,
        "iss": settings.jwt_issuer,
        "aud": settings.jwt_audience,
        "iat": int(utc_now().timestamp()),
        "nbf": int(utc_now().timestamp()),
        "exp": expires_at,
    }
    return jwt.encode(
        payload,
        settings.jwt_key_ring[settings.jwt_active_kid],
        algorithm=settings.jwt_algorithm,
        headers={"kid": settings.jwt_active_kid},
    )


def mark_login_success(db: Session, user: User) -> None:
    user.last_login_at = utc_now()
    db.add(user)
    db.commit()
    db.refresh(user)


def ensure_bootstrap_admin(db: Session) -> User | None:
    if not settings.bootstrap_admin_email or not settings.bootstrap_admin_password:
        return None

    existing = get_user_by_email(db, settings.bootstrap_admin_email)
    if existing is not None:
        return existing

    user = User(
        full_name=settings.bootstrap_admin_name or "RetainAI Administrator",
        email=normalize_email(settings.bootstrap_admin_email),
        role=ROLE_ADMIN,
        password_hash=hash_password(settings.bootstrap_admin_password),
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def upsert_sso_user(
    db: Session,
    *,
    email: str,
    full_name: str | None,
    role: str | None = None,
) -> User:
    normalized_email = normalize_email(email)
    user = get_user_by_email(db, normalized_email)
    resolved_role = role if role in ALL_ROLES else ROLE_COUNTRY_DIRECTOR
    if user is None:
        user = User(
            full_name=full_name or normalized_email.split("@")[0].replace(".", " ").title(),
            email=normalized_email,
            role=resolved_role,
            password_hash=hash_password(settings.resolved_jwt_secret_key),
            is_active=True,
        )
    else:
        if full_name:
            user.full_name = full_name
        if role in ALL_ROLES:
            user.role = resolved_role
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _session_idle_deadline(session: UserSession) -> datetime:
    return _coerce_utc(session.last_seen_at) + timedelta(minutes=settings.session_idle_timeout_minutes)


def _coerce_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def create_user_session(
    db: Session,
    *,
    user: User,
    auth_method: str,
    request: Request | None = None,
) -> UserSession:
    now = utc_now()
    session = UserSession(
        user_id=user.id,
        token_jti=str(uuid4()),
        token_key_id=settings.jwt_active_kid,
        auth_method=auth_method,
        source_ip=request.client.host if request and request.client else None,
        user_agent=(request.headers.get("user-agent")[:255] if request and request.headers.get("user-agent") else None),
        issued_at=now,
        expires_at=now + timedelta(minutes=settings.access_token_expire_minutes),
        last_seen_at=now,
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    enforce_session_limit(db, user)
    return session


def enforce_session_limit(db: Session, user: User) -> None:
    active_sessions = db.scalars(
        select(UserSession)
        .where(
            UserSession.user_id == user.id,
            UserSession.revoked_at.is_(None),
            UserSession.expires_at > utc_now(),
        )
        .order_by(UserSession.issued_at.asc())
    ).all()
    if len(active_sessions) <= settings.max_active_sessions_per_user:
        return
    for session in active_sessions[: len(active_sessions) - settings.max_active_sessions_per_user]:
        session.revoked_at = utc_now()
        session.revoked_reason = "session_limit_exceeded"
        db.add(session)
    db.commit()


def revoke_user_session(
    db: Session,
    session: UserSession,
    *,
    reason: str,
) -> UserSession:
    if session.revoked_at is None:
        session.revoked_at = utc_now()
        session.revoked_reason = reason
        db.add(session)
        db.commit()
        db.refresh(session)
    return session


def list_active_sessions(db: Session, user: User) -> list[UserSession]:
    return db.scalars(
        select(UserSession)
        .where(
            UserSession.user_id == user.id,
            UserSession.expires_at > utc_now(),
        )
        .order_by(UserSession.issued_at.desc())
    ).all()


def login_allowed(db: Session, *, email: str, source_ip: str | None) -> tuple[bool, str | None]:
    window_start = utc_now() - timedelta(minutes=settings.login_rate_limit_window_minutes)
    clauses = [AuditLog.actor_email == normalize_email(email)]
    if source_ip:
        clauses.append(AuditLog.ip_address == source_ip)
    statement = select(func.count(AuditLog.id)).where(
        AuditLog.action == "auth.login_failed",
        AuditLog.created_at >= window_start,
        or_(*clauses),
    )
    failures = db.scalar(statement) or 0
    if failures >= settings.login_rate_limit_attempts:
        return False, "Too many recent failed sign-in attempts. Wait before retrying."
    return True, None


def _decode_access_token(token: str) -> dict[str, object]:
    key_ring = settings.jwt_key_ring
    try:
        header = jwt.get_unverified_header(token)
    except JWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid access token header",
        ) from exc
    kid = header.get("kid")
    candidate_keys: list[tuple[str, str]] = []
    if isinstance(kid, str) and kid in key_ring:
        candidate_keys.append((kid, key_ring[kid]))
    candidate_keys.extend((key_id, key) for key_id, key in key_ring.items() if key_id != kid)

    last_error: JWTError | None = None
    for _, secret in candidate_keys:
        try:
            return jwt.decode(
                token,
                secret,
                algorithms=[settings.jwt_algorithm],
                issuer=settings.jwt_issuer,
                audience=settings.jwt_audience,
            )
        except JWTError as exc:
            last_error = exc
            continue
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired access token",
    ) from last_error


def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )

    try:
        payload = _decode_access_token(credentials.credentials)
    except HTTPException:
        raise

    user_id = payload.get("sub")
    session_id = payload.get("sid")
    token_jti = payload.get("jti")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid access token payload",
        )
    if not isinstance(session_id, str) or not isinstance(token_jti, str):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Access token is missing session claims",
        )

    user = db.get(User, user_id)
    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User account is inactive",
        )
    session = db.get(UserSession, session_id)
    if session is None or session.user_id != user.id or session.token_jti != token_jti:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session has been revoked",
        )
    now = utc_now()
    if session.revoked_at is not None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session has been revoked",
        )
    if _coerce_utc(session.expires_at) <= now:
        revoke_user_session(db, session, reason="expired")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session has expired",
        )
    if _session_idle_deadline(session) <= now:
        revoke_user_session(db, session, reason="idle_timeout")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session has timed out due to inactivity",
        )
    if (now - _coerce_utc(session.last_seen_at)).total_seconds() >= settings.session_touch_interval_seconds:
        session.last_seen_at = now
        session.source_ip = request.client.host if request.client else session.source_ip
        if request.headers.get("user-agent"):
            session.user_agent = request.headers.get("user-agent")[:255]
        db.add(session)
        db.commit()
    return user


def get_current_active_user(current_user: User = Depends(get_current_user)) -> User:
    return current_user


def get_current_user_session(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> UserSession:
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )
    payload = _decode_access_token(credentials.credentials)
    session_id = payload.get("sid")
    token_jti = payload.get("jti")
    if not isinstance(session_id, str) or not isinstance(token_jti, str):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Access token is missing session claims",
        )
    session = db.get(UserSession, session_id)
    if session is None or session.token_jti != token_jti:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session has been revoked",
        )
    now = utc_now()
    if session.revoked_at is not None or _coerce_utc(session.expires_at) <= now or _session_idle_deadline(session) <= now:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session is no longer active",
        )
    if (now - _coerce_utc(session.last_seen_at)).total_seconds() >= settings.session_touch_interval_seconds:
        session.last_seen_at = now
        session.source_ip = request.client.host if request.client else session.source_ip
        if request.headers.get("user-agent"):
            session.user_agent = request.headers.get("user-agent")[:255]
        db.add(session)
        db.commit()
        db.refresh(session)
    return session


def require_roles(*roles: str) -> Callable[[User], User]:
    allowed_roles = set(roles)

    def dependency(current_user: User = Depends(get_current_active_user)) -> User:
        if current_user.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have access to this resource",
            )
        return current_user

    return dependency
