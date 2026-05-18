"""JWT 双 Token 工具。

- access_token：15 分钟，携带 sub + organization_id，无状态校验
- refresh_token：7 天，仅携带 sub + jti，黑名单存 Redis
- 所有 token 都带 iss/aud 防跨环境复用
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

from fastapi import HTTPException, status
from jose import JWTError, jwt

from app.core.config import get_settings


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _build_payload(sub: str, ttl: timedelta, token_type: str, **extra: Any) -> dict[str, Any]:
    settings = get_settings()
    return {
        "sub": sub,
        "type": token_type,
        "jti": uuid4().hex,
        "iss": settings.jwt_issuer,
        "aud": settings.jwt_audience,
        "iat": int(_now().timestamp()),
        "exp": int((_now() + ttl).timestamp()),
        **extra,
    }


def create_access_token(
    *,
    user_id: str,
    organization_id: str | None = None,
) -> tuple[str, datetime]:
    """生成 access token，返回 (token, expires_at)。"""
    settings = get_settings()
    ttl = timedelta(minutes=settings.access_token_ttl_minutes)
    payload = _build_payload(
        sub=user_id,
        ttl=ttl,
        token_type="access",
        organization_id=organization_id,
    )
    token = jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)
    return token, datetime.fromtimestamp(payload["exp"], tz=timezone.utc)


def create_refresh_token(*, user_id: str) -> tuple[str, str, datetime]:
    """生成 refresh token，返回 (token, jti, expires_at)。"""
    settings = get_settings()
    ttl = timedelta(days=settings.refresh_token_ttl_days)
    payload = _build_payload(sub=user_id, ttl=ttl, token_type="refresh")
    token = jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)
    return token, payload["jti"], datetime.fromtimestamp(payload["exp"], tz=timezone.utc)


def decode_token(token: str, *, expected_type: str | None = None) -> dict[str, Any]:
    """解析并校验 JWT。失败抛 HTTPException(401)。"""
    settings = get_settings()
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
            issuer=settings.jwt_issuer,
            audience=settings.jwt_audience,
        )
    except JWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid_token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc
    if expected_type and payload.get("type") != expected_type:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid_token_type",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return payload
