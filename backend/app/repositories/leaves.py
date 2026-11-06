"""All leave-related SQL. Authorisation lives IN the queries (docs/SECURITY.md section 5): a request a
user may not see is simply never returned."""

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy import ColumnElement, Select, and_, func, or_, select
from sqlalchemy.orm import Session, aliased

from app.domain.calendar import Span
from app.domain.types import ACTIVE_STATUSES, Role, Route, Status
from app.domain.workflow import RequestState
from app.models import Document, LeaveDecision, LeaveRequest, User
from app.schemas.leave import DecisionOut, DocumentOut, LeaveSummary, RecentLeave
from app.services.context import CurrentUser

e = aliased(User, name="e")  # the employee
m = aliased(User, name="m")  # the employee's manager


@dataclass
class LeaveCtx:
    """A request plus the approval chain around it."""

    req: LeaveRequest
    employee_name: str
    manager_id: UUID | None  # employee's direct manager (a manager's own leave: the HOD)
    hod_id: UUID | None  # the manager's manager; None for HOD_ONLY requests
    document_count: int


def _doc_count() -> Any:
    return (
        select(func.count(Document.id))
        .where(Document.request_id == LeaveRequest.id)
        .correlate(LeaveRequest)
        .scalar_subquery()
    )


def _joined(*cols: Any) -> Select[Any]:
    return (
        select(*cols)
        .select_from(LeaveRequest)
        .join(e, e.id == LeaveRequest.employee_id)
        .outerjoin(m, m.id == e.manager_id)
    )


def load(session: Session, request_id: int, *, lock: bool = False) -> LeaveCtx | None:
    stmt = _joined(LeaveRequest, e.name, e.manager_id, m.manager_id, _doc_count()).where(
        LeaveRequest.id == request_id
    )
    if lock:
        stmt = stmt.with_for_update(of=LeaveRequest)  # serialises concurrent decisions
    row = session.execute(stmt).first()
    if row is None:
        return None
    req, ename, manager_id, hod_id, docs = row
    if req.approver_route == Route.HOD_ONLY.value:
        hod_id = None
    return LeaveCtx(req, ename, manager_id, hod_id, docs)


def to_state(c: LeaveCtx) -> RequestState:
    r = c.req
    return RequestState(
        employee_id=r.employee_id,
        status=Status(r.status),
        resume_status=Status(r.resume_status) if r.resume_status else None,
        route=Route(r.approver_route),
        is_extended=r.is_extended,
        version=r.version,
        manager_id=c.manager_id,
        hod_id=c.hod_id,
        document_count=c.document_count,
    )


def visible_to(c: LeaveCtx, user_id: UUID) -> bool:
    return user_id in {c.req.employee_id, c.manager_id, c.hod_id}


def to_summary(r: LeaveRequest, employee_name: str, document_count: int) -> LeaveSummary:
    return LeaveSummary(
        id=r.id,
        employee_id=r.employee_id,
        employee_name=employee_name,
        from_date=r.from_date,
        to_date=r.to_date,
        days=r.days,
        streak=r.streak,
        leave_type=r.leave_type,
        reason=r.reason,
        is_extended=r.is_extended,
        status=r.status,
        approver_route=r.approver_route,
        version=r.version,
        document_count=document_count,
        created_at=r.created_at,
        updated_at=r.updated_at,
    )


def summaries(
    session: Session, conds: list[ColumnElement[bool]], order: list[Any], offset: int, limit: int
) -> tuple[list[LeaveSummary], int]:
    total = session.scalar(_joined(func.count(LeaveRequest.id)).where(*conds)) or 0
    rows = session.execute(
        _joined(LeaveRequest, e.name, _doc_count())
        .where(*conds)
        .order_by(*order)
        .offset(offset)
        .limit(limit)
    ).all()
    return [to_summary(r, name, dc) for r, name, dc in rows], total


def mine_conds(user_id: UUID, status: str | None) -> list[ColumnElement[bool]]:
    conds = [LeaveRequest.employee_id == user_id]
    if status:
        conds.append(LeaveRequest.status == status)
    return conds


def pending_cond(user: CurrentUser) -> ColumnElement[bool]:
    """Requests awaiting THIS user's decision. Authorisation is part of the SQL."""
    if user.role is Role.MANAGER:
        return and_(LeaveRequest.status == Status.PENDING_MANAGER.value, e.manager_id == user.id)
    if user.role is Role.HOD:
        return and_(
            LeaveRequest.status == Status.PENDING_HOD.value,
            or_(
                and_(
                    LeaveRequest.approver_route == Route.MANAGER_THEN_HOD.value,
                    m.manager_id == user.id,
                ),
                and_(LeaveRequest.approver_route == Route.HOD_ONLY.value, e.manager_id == user.id),
            ),
        )
    return LeaveRequest.id < 0  # employees never have an approval queue


def count_pending(session: Session, user: CurrentUser) -> int:
    if user.role is Role.EMPLOYEE:
        return 0
    return session.scalar(_joined(func.count(LeaveRequest.id)).where(pending_cond(user))) or 0


def count_needs_info(session: Session, user_id: UUID) -> int:
    return (
        session.scalar(
            select(func.count(LeaveRequest.id)).where(
                LeaveRequest.employee_id == user_id,
                LeaveRequest.status == Status.NEEDS_INFO.value,
            )
        )
        or 0
    )


def active_spans(session: Session, employee_id: UUID) -> list[tuple[int, Span]]:
    rows = session.execute(
        select(LeaveRequest.id, LeaveRequest.from_date, LeaveRequest.to_date).where(
            LeaveRequest.employee_id == employee_id,
            LeaveRequest.status.in_([s.value for s in ACTIVE_STATUSES]),
        )
    ).all()
    return [(rid, Span(f, t)) for rid, f, t in rows]


def timeline(session: Session, request_id: int) -> list[DecisionOut]:
    rows = session.execute(
        select(LeaveDecision, User.name, User.role)
        .join(User, User.id == LeaveDecision.actor_id)
        .where(LeaveDecision.request_id == request_id)
        .order_by(LeaveDecision.id)
    ).all()
    return [
        DecisionOut(
            id=d.id,
            stage=d.stage,
            action=d.action,
            actor_name=name,
            actor_role=role,
            from_status=d.from_status,
            to_status=d.to_status,
            comment=d.comment,
            created_at=d.created_at,
        )
        for d, name, role in rows
    ]


def documents(session: Session, request_id: int) -> list[DocumentOut]:
    docs = session.scalars(
        select(Document).where(Document.request_id == request_id).order_by(Document.created_at)
    ).all()
    return [
        DocumentOut(
            id=d.id,
            name=d.original_name,
            mime=d.mime,
            size_bytes=d.size_bytes,
            uploaded_by=d.uploaded_by,
            created_at=d.created_at,
        )
        for d in docs
    ]


def recent_for_employee(session: Session, employee_id: UUID, exclude_id: int) -> list[RecentLeave]:
    rows = session.scalars(
        select(LeaveRequest)
        .where(LeaveRequest.employee_id == employee_id, LeaveRequest.id != exclude_id)
        .order_by(LeaveRequest.from_date.desc())
        .limit(5)
    ).all()
    return [
        RecentLeave(id=r.id, from_date=r.from_date, to_date=r.to_date, days=r.days, status=r.status)
        for r in rows
    ]


def used_storage_bytes(session: Session, user_id: UUID) -> int:
    return (
        session.scalar(
            select(func.coalesce(func.sum(Document.size_bytes), 0)).where(
                Document.uploaded_by == user_id
            )
        )
        or 0
    )
