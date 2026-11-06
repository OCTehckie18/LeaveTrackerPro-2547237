from datetime import date, datetime, time, timedelta
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query

from app.api.deps import SessionDep, require_role
from app.domain.types import Role
from app.schemas.leave import AuditPage
from app.services import audit as audit_service
from app.services.context import CurrentUser

router = APIRouter(prefix="/api/v1/audit", tags=["audit"])

HodOnly = Annotated[CurrentUser, Depends(require_role(Role.HOD))]


@router.get("")
def list_audit(
    session: SessionDep,
    _user: HodOnly,
    entity: Annotated[str | None, Query(max_length=40)] = None,
    entity_id: Annotated[str | None, Query(alias="entityId", max_length=64)] = None,
    actor: UUID | None = None,
    date_from: Annotated[date | None, Query(alias="from")] = None,
    date_to: Annotated[date | None, Query(alias="to")] = None,
    cursor: int | None = None,
) -> AuditPage:
    """Read-only. There is deliberately no API that writes or edits audit rows."""
    return audit_service.query(
        session,
        entity_type=entity,
        entity_id=entity_id,
        actor_id=actor,
        date_from=datetime.combine(date_from, time.min) if date_from else None,
        date_to=datetime.combine(date_to + timedelta(days=1), time.min) if date_to else None,
        cursor=cursor,
    )
