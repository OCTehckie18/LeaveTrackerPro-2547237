from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import Field

from app.domain.types import LeaveType
from app.schemas.common import CamelModel

# ---- input ----------------------------------------------------------------------------------------


class LeaveIn(CamelModel):
    """The mandated shape: employeeName, fromDate, toDate, reason (+ optional leaveType)."""

    employee_name: str | None = Field(default=None, max_length=100)
    from_date: date
    to_date: date
    reason: str = Field(max_length=2000)  # business rule (10-500 after trim) enforced in the domain
    leave_type: LeaveType = LeaveType.ANNUAL


class PreviewIn(CamelModel):
    from_date: date
    to_date: date


class DecisionIn(CamelModel):
    action: Literal["APPROVE", "REJECT", "REQUEST_INFO"]
    comment: str | None = Field(default=None, max_length=5000)
    version: int


class RespondIn(CamelModel):
    comment: str | None = Field(default=None, max_length=5000)
    version: int


class CancelIn(CamelModel):
    version: int


# ---- output ---------------------------------------------------------------------------------------


class DocumentOut(CamelModel):
    id: UUID
    name: str
    mime: str
    size_bytes: int
    uploaded_by: UUID
    created_at: datetime


class DecisionOut(CamelModel):
    id: int
    stage: str
    action: str
    actor_name: str
    actor_role: str
    from_status: str | None
    to_status: str
    comment: str | None
    created_at: datetime


class LeaveSummary(CamelModel):
    id: int
    employee_id: UUID
    employee_name: str
    from_date: date
    to_date: date
    days: int
    streak: int
    leave_type: str
    reason: str
    is_extended: bool
    status: str
    approver_route: str
    version: int
    document_count: int
    created_at: datetime
    updated_at: datetime


class RecentLeave(CamelModel):
    id: int
    from_date: date
    to_date: date
    days: int
    status: str


class Permissions(CamelModel):
    can_decide: bool
    can_respond: bool
    can_cancel: bool
    waiting_for: str | None  # "MANAGER" | "HOD" | None


class LeaveDetail(LeaveSummary):
    resume_status: str | None
    decisions: list[DecisionOut]
    documents: list[DocumentOut]
    recent_leave: list[RecentLeave]  # employee's other recent requests (approver view only)
    permissions: Permissions


class ChainSpan(CamelModel):
    from_date: date
    to_date: date


class PreviewOut(CamelModel):
    days: int
    streak: int
    is_extended: bool
    chain: list[ChainSpan]
    requires_documents: bool
    approval_chain: list[str]
    conflict: RecentLeave | None


class AuditOut(CamelModel):
    id: int
    ts: datetime
    actor_id: UUID | None
    actor_name: str | None
    actor_role: str | None
    action: str
    entity_type: str
    entity_id: str | None
    details: dict[str, object]
    request_id: str | None


class AuditPage(CamelModel):
    items: list[AuditOut]
    next_cursor: int | None
