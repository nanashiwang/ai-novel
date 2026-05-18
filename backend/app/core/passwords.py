"""密码哈希工具。

使用 bcrypt 算法，避免在仓库中存放明文密码。
"""
from __future__ import annotations

from passlib.context import CryptContext

from app.core.config import get_settings

_settings = get_settings()

# 单例 CryptContext，bcrypt 轮数从 settings 注入（生产建议 ≥12）
_pwd_context = CryptContext(
    schemes=["bcrypt"],
    deprecated="auto",
    bcrypt__rounds=_settings.bcrypt_rounds,
)


def hash_password(plain_password: str) -> str:
    """返回 bcrypt 哈希后的密码串。"""
    if not plain_password or len(plain_password) < 6:
        raise ValueError("password_too_short")
    return _pwd_context.hash(plain_password)


def verify_password(plain_password: str, hashed_password: str | None) -> bool:
    """校验明文密码与哈希值是否匹配。"""
    if not hashed_password:
        return False
    try:
        return _pwd_context.verify(plain_password, hashed_password)
    except ValueError:
        return False
