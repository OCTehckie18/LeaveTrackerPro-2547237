"""Password hashing (argon2id), session tokens and the password policy."""

import hashlib
import secrets

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError

from app.domain.errors import ValidationFailed

_hasher = PasswordHasher()  # argon2id with the library's recommended defaults


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except (VerifyMismatchError, InvalidHashError):
        return False


# Verified against when the email is unknown, so "no such user" costs the same time as "wrong password".
DUMMY_HASH = hash_password("not-a-real-password-just-for-timing")


def new_token() -> str:
    return secrets.token_urlsafe(32)  # 256 bits


def token_hash(token: str) -> bytes:
    """Only this hash is stored: a database leak must not hand out live sessions."""
    return hashlib.sha256(token.encode()).digest()


_COMMON = {
    "password1234", "123456789012", "qwertyuiop12", "iloveyou1234", "administrator",
    "welcome12345", "letmein12345", "password@123", "changeme1234", "abc123456789",
}  # fmt: skip


def validate_new_password(password: str, email: str) -> None:
    """>= 12 chars, <= 128, not a common password, not the email."""
    low = password.lower()
    if (
        not 12 <= len(password) <= 128
        or low in _COMMON
        or low == email.lower()
        or len(set(password)) < 5
    ):
        raise ValidationFailed(
            {"newPassword": "Choose a longer password (12+ characters) that isn't commonly used."}
        )
