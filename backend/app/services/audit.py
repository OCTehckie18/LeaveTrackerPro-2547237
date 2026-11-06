"""Audit trail. `record()` only ADDS a row to the caller's transaction, so the log entry commits (or
rolls back) together with the business change it describes. Never put reason/comment text in details."""

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AuditLog, User
from app.schemas.leave import AuditOut, AuditPage
from app.services.context import CurrentUser, RequestCtx


def record(
    session: Session,
    *,
    action: str,
    entity_type: str,
    entity_id: object | None = None,
    actor: CurrentUser | None = None,
    ctx: RequestCtx | None = None,
    details: dict[str, Any] | None = None,
) -> None:
    session.add(
        AuditLog(
            actor_id=actor.id if actor else None,
            actor_role=actor.role.value if actor else None,
            action=action,
            entity_type=entity_type,
            entity_id=None if entity_id is None else str(entity_id),
            details=details or {},
            ip=ctx.ip if ctx else None,
            request_id=ctx.request_id if ctx else None,
        )
    )


def query(
    session: Session,
    *,
    entity_type: str | None,
    entity_id: str | None,
    actor_id: object | None,
    date_from: object | None,
    date_to: object | None,
    cursor: int | None,
    limit: int = 50,
) -> AuditPage:
    stmt = select(AuditLog, User.name).outerjoin(User, User.id == AuditLog.actor_id)
    if entity_type:
        stmt = stmt.where(AuditLog.entity_type == entity_type)
    if entity_id:
        stmt = stmt.where(AuditLog.entity_id == entity_id)
    if actor_id:
        stmt = stmt.where(AuditLog.actor_id == actor_id)
    if date_from:
        stmt = stmt.where(AuditLog.ts >= date_from)
    if date_to:
        stmt = stmt.where(AuditLog.ts < date_to)
    if cursor:
        stmt = stmt.where(AuditLog.id < cursor)
    rows = session.execute(stmt.order_by(AuditLog.id.desc()).limit(limit + 1)).all()
    items = [
        AuditOut(
            id=a.id,
            ts=a.ts,
            actor_id=a.actor_id,
            actor_name=name,
            actor_role=a.actor_role,
            action=a.action,
            entity_type=a.entity_type,
            entity_id=a.entity_id,
            details=a.details,
            request_id=a.request_id,
        )
        for a, name in rows[:limit]
    ]
    return AuditPage(items=items, next_cursor=items[-1].id if len(rows) > limit else None)
