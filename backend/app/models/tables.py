"""All tables (docs/ARCHITECTURE.md section 4). The Alembic baseline migration is hand-reviewed to match."""

import uuid
from datetime import date, datetime
from typing import Any

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import CITEXT, INET, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import SCHEMA, Base

_NOW = sa.text("now()")


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        sa.CheckConstraint("char_length(name) BETWEEN 1 AND 100", name="name_len"),
        sa.CheckConstraint("role IN ('EMPLOYEE','MANAGER','HOD')", name="role_valid"),
        sa.CheckConstraint("manager_id IS DISTINCT FROM id", name="manager_not_self"),
        sa.Index("ix_users_manager_id", "manager_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid, primary_key=True, server_default=sa.text("gen_random_uuid()")
    )
    email: Mapped[str] = mapped_column(CITEXT, unique=True)
    name: Mapped[str] = mapped_column(sa.Text)
    password_hash: Mapped[str] = mapped_column(sa.Text)  # argon2id
    role: Mapped[str] = mapped_column(sa.Text)
    manager_id: Mapped[uuid.UUID | None] = mapped_column(sa.ForeignKey(f"{SCHEMA}.users.id"))
    is_active: Mapped[bool] = mapped_column(server_default=sa.true())
    is_demo: Mapped[bool] = mapped_column(server_default=sa.false())
    failed_logins: Mapped[int] = mapped_column(server_default=sa.text("0"))
    locked_until: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), server_default=_NOW)


class UserSession(Base):
    __tablename__ = "sessions"
    __table_args__ = (sa.Index("ix_sessions_user_id", "user_id"),)

    id_hash: Mapped[bytes] = mapped_column(sa.LargeBinary, primary_key=True)  # sha256(token)
    user_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey(f"{SCHEMA}.users.id", ondelete="CASCADE")
    )
    created_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), server_default=_NOW)
    last_seen_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), server_default=_NOW)
    idle_expires_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True))
    absolute_expires_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True))


class LeaveRequest(Base):
    __tablename__ = "leave_requests"
    __table_args__ = (
        sa.CheckConstraint("days BETWEEN 1 AND 60", name="days_range"),
        sa.CheckConstraint("streak >= days", name="streak_ge_days"),
        sa.CheckConstraint(
            "leave_type IN ('ANNUAL','SICK','CASUAL','OTHER')", name="leave_type_valid"
        ),
        sa.CheckConstraint("char_length(reason) BETWEEN 10 AND 500", name="reason_len"),
        sa.CheckConstraint(
            "status IN ('PENDING_MANAGER','PENDING_HOD','NEEDS_INFO','APPROVED',"
            "'REJECTED','CANCELLED')",
            name="status_valid",
        ),
        sa.CheckConstraint(
            "resume_status IN ('PENDING_MANAGER','PENDING_HOD')", name="resume_status_valid"
        ),
        sa.CheckConstraint(
            "approver_route IN ('MANAGER_THEN_HOD','MANAGER_ONLY','HOD_ONLY')",
            name="approver_route_valid",
        ),
        sa.CheckConstraint("to_date >= from_date", name="date_order"),
        sa.CheckConstraint("days = to_date - from_date + 1", name="days_formula"),
        sa.CheckConstraint(
            "(status = 'NEEDS_INFO') = (resume_status IS NOT NULL)", name="needs_info_resume"
        ),
        sa.CheckConstraint("is_extended = (streak > 3)", name="extended_matches_streak"),
        sa.Index("ix_leave_requests_employee_dates", "employee_id", "from_date", "to_date"),
        sa.Index("ix_leave_requests_status_employee", "status", "employee_id"),
        sa.Index("ix_leave_requests_employee_created", "employee_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(sa.BigInteger, sa.Identity(always=True), primary_key=True)
    employee_id: Mapped[uuid.UUID] = mapped_column(sa.ForeignKey(f"{SCHEMA}.users.id"))
    from_date: Mapped[date] = mapped_column(sa.Date)
    to_date: Mapped[date] = mapped_column(sa.Date)
    days: Mapped[int] = mapped_column(sa.SmallInteger)
    streak: Mapped[int] = mapped_column(sa.SmallInteger)
    leave_type: Mapped[str] = mapped_column(sa.Text, server_default="ANNUAL")
    reason: Mapped[str] = mapped_column(sa.Text)
    is_extended: Mapped[bool]
    status: Mapped[str] = mapped_column(sa.Text)
    resume_status: Mapped[str | None] = mapped_column(sa.Text)
    approver_route: Mapped[str] = mapped_column(sa.Text)
    version: Mapped[int] = mapped_column(server_default=sa.text("1"))
    created_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), server_default=_NOW)
    updated_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), server_default=_NOW)


class LeaveDecision(Base):
    """The request's timeline. Rows are only ever inserted."""

    __tablename__ = "leave_decisions"
    __table_args__ = (
        sa.CheckConstraint("stage IN ('MANAGER','HOD','EMPLOYEE')", name="stage_valid"),
        sa.CheckConstraint(
            "action IN ('SUBMIT','APPROVE','REJECT','REQUEST_INFO','RESPOND','CANCEL')",
            name="action_valid",
        ),
        sa.CheckConstraint("char_length(comment) <= 1000", name="comment_len"),
        sa.Index("ix_leave_decisions_request_id", "request_id"),
        sa.Index("ix_leave_decisions_actor_id", "actor_id"),
    )

    id: Mapped[int] = mapped_column(sa.BigInteger, sa.Identity(always=True), primary_key=True)
    request_id: Mapped[int] = mapped_column(sa.ForeignKey(f"{SCHEMA}.leave_requests.id"))
    stage: Mapped[str] = mapped_column(sa.Text)
    actor_id: Mapped[uuid.UUID] = mapped_column(sa.ForeignKey(f"{SCHEMA}.users.id"))
    action: Mapped[str] = mapped_column(sa.Text)
    from_status: Mapped[str | None] = mapped_column(sa.Text)
    to_status: Mapped[str] = mapped_column(sa.Text)
    comment: Mapped[str | None] = mapped_column(sa.Text)
    created_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), server_default=_NOW)


class Document(Base):
    __tablename__ = "documents"
    __table_args__ = (
        sa.CheckConstraint("char_length(original_name) <= 120", name="original_name_len"),
        sa.CheckConstraint(
            "mime IN ('application/pdf','image/png','image/jpeg',"
            "'application/vnd.openxmlformats-officedocument.wordprocessingml.document')",
            name="mime_valid",
        ),
        sa.CheckConstraint("size_bytes BETWEEN 1 AND 3145728", name="size_range"),
        sa.Index("ix_documents_request_id", "request_id"),
        sa.Index("ix_documents_uploaded_by", "uploaded_by"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid, primary_key=True, server_default=sa.text("gen_random_uuid()")
    )
    request_id: Mapped[int] = mapped_column(sa.ForeignKey(f"{SCHEMA}.leave_requests.id"))
    uploaded_by: Mapped[uuid.UUID] = mapped_column(sa.ForeignKey(f"{SCHEMA}.users.id"))
    original_name: Mapped[str] = mapped_column(sa.Text)
    storage_key: Mapped[str] = mapped_column(sa.Text, unique=True)  # 'docs/<uuid4>'
    mime: Mapped[str] = mapped_column(sa.Text)
    size_bytes: Mapped[int]
    sha256: Mapped[bytes] = mapped_column(sa.LargeBinary)
    created_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), server_default=_NOW)


class AuditLog(Base):
    """Append-only (see the baseline migration: REVOKE + blocking triggers)."""

    __tablename__ = "audit_log"
    __table_args__ = (
        sa.Index("ix_audit_log_entity", "entity_type", "entity_id", "id"),
        sa.Index("ix_audit_log_actor", "actor_id", "id"),
    )

    id: Mapped[int] = mapped_column(sa.BigInteger, sa.Identity(always=True), primary_key=True)
    ts: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), server_default=_NOW)
    actor_id: Mapped[uuid.UUID | None] = mapped_column(sa.Uuid)
    actor_role: Mapped[str | None] = mapped_column(sa.Text)
    action: Mapped[str] = mapped_column(sa.Text)
    entity_type: Mapped[str] = mapped_column(sa.Text)
    entity_id: Mapped[str | None] = mapped_column(sa.Text)
    # ids and before/after status only; never reason or comment text
    details: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default=sa.text("'{}'::jsonb"))
    ip: Mapped[str | None] = mapped_column(INET)
    request_id: Mapped[str | None] = mapped_column(sa.Text)
