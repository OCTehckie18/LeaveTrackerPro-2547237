"""Login, sessions, lockout and password change (docs/SECURITY.md sections 2-3)."""

from datetime import timedelta

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.clock import utcnow
from app.core.config import get_settings
from app.core.security import (
    DUMMY_HASH,
    hash_password,
    new_token,
    token_hash,
    validate_new_password,
    verify_password,
)
from app.domain.errors import Forbidden, RateLimited, Unauthenticated, ValidationFailed
from app.domain.types import Role
from app.models import User, UserSession
from app.services import audit
from app.services.context import CurrentUser, RequestCtx

MAX_FAILED = 5
LOCK_MINUTES = 15
_BAD_LOGIN = "Email or password is incorrect."  # same text for unknown user / wrong password


def _to_current(user: User) -> CurrentUser:
    return CurrentUser(user.id, user.email, user.name, Role(user.role), user.is_demo)


def login(session: Session, email: str, password: str, ctx: RequestCtx) -> tuple[CurrentUser, str]:
    settings = get_settings()
    now = utcnow()
    user = session.scalar(select(User).where(User.email == email.strip()))

    if user is None or not user.is_active:
        verify_password(DUMMY_HASH, password)  # equalise timing
        audit.record(session, action="LOGIN_FAILURE", entity_type="user", ctx=ctx,
                     details={"reason": "unknown_or_inactive"})  # fmt: skip
        session.commit()
        raise Unauthenticated(_BAD_LOGIN)

    if user.locked_until and user.locked_until > now and not user.is_demo:
        minutes = max(1, int((user.locked_until - now).total_seconds() // 60) + 1)
        raise RateLimited(
            f"Too many sign-in attempts. Please try again in {minutes} minute(s).",
            retry_after=minutes * 60,
        )

    if not verify_password(user.password_hash, password):
        if not user.is_demo:  # demo accounts are exempt, so nobody can lock out the shared logins
            user.failed_logins += 1
            if user.failed_logins >= MAX_FAILED:
                user.locked_until = now + timedelta(minutes=LOCK_MINUTES)
                user.failed_logins = 0
                audit.record(session, action="LOGIN_LOCKOUT", entity_type="user",
                             entity_id=user.id, ctx=ctx)  # fmt: skip
        audit.record(session, action="LOGIN_FAILURE", entity_type="user", entity_id=user.id,
                     ctx=ctx, details={"reason": "bad_password"})  # fmt: skip
        session.commit()
        raise Unauthenticated(_BAD_LOGIN)

    user.failed_logins = 0
    user.locked_until = None
    token = new_token()
    session.add(
        UserSession(
            id_hash=token_hash(token),
            user_id=user.id,
            created_at=now,
            last_seen_at=now,
            idle_expires_at=now + timedelta(minutes=settings.session_idle_min),
            absolute_expires_at=now + timedelta(hours=settings.session_absolute_h),
        )
    )
    current = _to_current(user)
    audit.record(session, action="LOGIN_SUCCESS", entity_type="user", entity_id=user.id,
                 actor=current, ctx=ctx)  # fmt: skip
    session.commit()
    return current, token


def resolve_session(session: Session, token: str) -> CurrentUser:
    settings = get_settings()
    now = utcnow()
    row = session.execute(
        select(UserSession, User)
        .join(User, User.id == UserSession.user_id)
        .where(UserSession.id_hash == token_hash(token))
    ).first()
    if row is None:
        raise Unauthenticated("Your session has expired. Please sign in again.")
    sess, user = row
    if now > sess.idle_expires_at or now > sess.absolute_expires_at or not user.is_active:
        session.delete(sess)
        session.commit()
        raise Unauthenticated("Your session has expired. Please sign in again.")
    if (now - sess.last_seen_at).total_seconds() > 60:  # sliding idle window, at most 1 write/min
        sess.last_seen_at = now
        sess.idle_expires_at = min(
            now + timedelta(minutes=settings.session_idle_min), sess.absolute_expires_at
        )
        session.commit()
    return _to_current(user)


def logout(session: Session, token: str, user: CurrentUser, ctx: RequestCtx) -> None:
    session.execute(delete(UserSession).where(UserSession.id_hash == token_hash(token)))
    audit.record(
        session, action="LOGOUT", entity_type="user", entity_id=user.id, actor=user, ctx=ctx
    )
    session.commit()


def change_password(
    session: Session,
    user: CurrentUser,
    token: str,
    current_password: str,
    new_password: str,
    ctx: RequestCtx,
) -> None:
    if user.is_demo:
        raise Forbidden("Demo accounts can't change their password.")
    row = session.get(User, user.id)
    assert row is not None
    if not verify_password(row.password_hash, current_password):
        raise ValidationFailed({"currentPassword": "That isn't your current password."})
    validate_new_password(new_password, user.email)
    row.password_hash = hash_password(new_password)
    # revoke every other session of this user
    session.execute(
        delete(UserSession).where(
            UserSession.user_id == user.id, UserSession.id_hash != token_hash(token)
        )
    )
    audit.record(session, action="PASSWORD_CHANGED", entity_type="user", entity_id=user.id,
                 actor=user, ctx=ctx)  # fmt: skip
    session.commit()
