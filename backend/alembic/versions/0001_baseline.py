"""Baseline: schema, tables, RLS, append-only audit log.

Revision ID: 0001
Revises:
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import CITEXT, INET, JSONB

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

S = "leave"
NOW = sa.text("now()")
TABLES = ["users", "sessions", "leave_requests", "leave_decisions", "documents", "audit_log"]


def _ts(name: str, **kw) -> sa.Column:  # type: ignore[no-untyped-def]
    return sa.Column(name, sa.DateTime(timezone=True), **kw)


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS citext")

    op.create_table(
        "users",
        sa.Column("id", sa.Uuid, primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("email", CITEXT, nullable=False),
        sa.Column("name", sa.Text, nullable=False),
        sa.Column("password_hash", sa.Text, nullable=False),
        sa.Column("role", sa.Text, nullable=False),
        sa.Column("manager_id", sa.Uuid, sa.ForeignKey(f"{S}.users.id")),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("is_demo", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("failed_logins", sa.Integer, nullable=False, server_default=sa.text("0")),
        _ts("locked_until"),
        _ts("created_at", nullable=False, server_default=NOW),
        sa.UniqueConstraint("email"),
        sa.CheckConstraint("char_length(name) BETWEEN 1 AND 100", name="name_len"),
        sa.CheckConstraint("role IN ('EMPLOYEE','MANAGER','HOD')", name="role_valid"),
        sa.CheckConstraint("manager_id IS DISTINCT FROM id", name="manager_not_self"),
        schema=S,
    )
    op.create_index("ix_users_manager_id", "users", ["manager_id"], schema=S)

    op.create_table(
        "sessions",
        sa.Column("id_hash", sa.LargeBinary, primary_key=True),
        sa.Column(
            "user_id", sa.Uuid, sa.ForeignKey(f"{S}.users.id", ondelete="CASCADE"), nullable=False
        ),
        _ts("created_at", nullable=False, server_default=NOW),
        _ts("last_seen_at", nullable=False, server_default=NOW),
        _ts("idle_expires_at", nullable=False),
        _ts("absolute_expires_at", nullable=False),
        schema=S,
    )
    op.create_index("ix_sessions_user_id", "sessions", ["user_id"], schema=S)

    op.create_table(
        "leave_requests",
        sa.Column("id", sa.BigInteger, sa.Identity(always=True), primary_key=True),
        sa.Column("employee_id", sa.Uuid, sa.ForeignKey(f"{S}.users.id"), nullable=False),
        sa.Column("from_date", sa.Date, nullable=False),
        sa.Column("to_date", sa.Date, nullable=False),
        sa.Column("days", sa.SmallInteger, nullable=False),
        sa.Column("streak", sa.SmallInteger, nullable=False),
        sa.Column("leave_type", sa.Text, nullable=False, server_default="ANNUAL"),
        sa.Column("reason", sa.Text, nullable=False),
        sa.Column("is_extended", sa.Boolean, nullable=False),
        sa.Column("status", sa.Text, nullable=False),
        sa.Column("resume_status", sa.Text),
        sa.Column("approver_route", sa.Text, nullable=False),
        sa.Column("version", sa.Integer, nullable=False, server_default=sa.text("1")),
        _ts("created_at", nullable=False, server_default=NOW),
        _ts("updated_at", nullable=False, server_default=NOW),
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
        schema=S,
    )
    op.create_index(
        "ix_leave_requests_employee_dates",
        "leave_requests",
        ["employee_id", "from_date", "to_date"],
        schema=S,
    )
    op.create_index(
        "ix_leave_requests_status_employee", "leave_requests", ["status", "employee_id"], schema=S
    )
    op.create_index(
        "ix_leave_requests_employee_created",
        "leave_requests",
        ["employee_id", "created_at"],
        schema=S,
    )

    op.create_table(
        "leave_decisions",
        sa.Column("id", sa.BigInteger, sa.Identity(always=True), primary_key=True),
        sa.Column("request_id", sa.BigInteger, sa.ForeignKey(f"{S}.leave_requests.id"), nullable=False),
        sa.Column("stage", sa.Text, nullable=False),
        sa.Column("actor_id", sa.Uuid, sa.ForeignKey(f"{S}.users.id"), nullable=False),
        sa.Column("action", sa.Text, nullable=False),
        sa.Column("from_status", sa.Text),
        sa.Column("to_status", sa.Text, nullable=False),
        sa.Column("comment", sa.Text),
        _ts("created_at", nullable=False, server_default=NOW),
        sa.CheckConstraint("stage IN ('MANAGER','HOD','EMPLOYEE')", name="stage_valid"),
        sa.CheckConstraint(
            "action IN ('SUBMIT','APPROVE','REJECT','REQUEST_INFO','RESPOND','CANCEL')",
            name="action_valid",
        ),
        sa.CheckConstraint("char_length(comment) <= 1000", name="comment_len"),
        schema=S,
    )
    op.create_index("ix_leave_decisions_request_id", "leave_decisions", ["request_id"], schema=S)
    op.create_index("ix_leave_decisions_actor_id", "leave_decisions", ["actor_id"], schema=S)

    op.create_table(
        "documents",
        sa.Column("id", sa.Uuid, primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("request_id", sa.BigInteger, sa.ForeignKey(f"{S}.leave_requests.id"), nullable=False),
        sa.Column("uploaded_by", sa.Uuid, sa.ForeignKey(f"{S}.users.id"), nullable=False),
        sa.Column("original_name", sa.Text, nullable=False),
        sa.Column("storage_key", sa.Text, nullable=False),
        sa.Column("mime", sa.Text, nullable=False),
        sa.Column("size_bytes", sa.Integer, nullable=False),
        sa.Column("sha256", sa.LargeBinary, nullable=False),
        _ts("created_at", nullable=False, server_default=NOW),
        sa.UniqueConstraint("storage_key"),
        sa.CheckConstraint("char_length(original_name) <= 120", name="original_name_len"),
        sa.CheckConstraint(
            "mime IN ('application/pdf','image/png','image/jpeg',"
            "'application/vnd.openxmlformats-officedocument.wordprocessingml.document')",
            name="mime_valid",
        ),
        sa.CheckConstraint("size_bytes BETWEEN 1 AND 3145728", name="size_range"),
        schema=S,
    )
    op.create_index("ix_documents_request_id", "documents", ["request_id"], schema=S)
    op.create_index("ix_documents_uploaded_by", "documents", ["uploaded_by"], schema=S)

    op.create_table(
        "audit_log",
        sa.Column("id", sa.BigInteger, sa.Identity(always=True), primary_key=True),
        _ts("ts", nullable=False, server_default=NOW),
        sa.Column("actor_id", sa.Uuid),
        sa.Column("actor_role", sa.Text),
        sa.Column("action", sa.Text, nullable=False),
        sa.Column("entity_type", sa.Text, nullable=False),
        sa.Column("entity_id", sa.Text),
        sa.Column("details", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("ip", INET),
        sa.Column("request_id", sa.Text),
        schema=S,
    )
    op.create_index(
        "ix_audit_log_entity", "audit_log", ["entity_type", "entity_id", "id"], schema=S
    )
    op.create_index("ix_audit_log_actor", "audit_log", ["actor_id", "id"], schema=S)

    # --- Append-only audit log: privilege + trigger backstop (docs/SECURITY.md) -----------------
    op.execute(
        f"""
        CREATE FUNCTION {S}.audit_log_immutable() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            RAISE EXCEPTION 'audit_log is append-only (% blocked)', TG_OP;
        END $$
        """
    )
    op.execute(
        f"CREATE TRIGGER audit_log_no_update_delete BEFORE UPDATE OR DELETE ON {S}.audit_log "
        f"FOR EACH ROW EXECUTE FUNCTION {S}.audit_log_immutable()"
    )
    op.execute(
        f"CREATE TRIGGER audit_log_no_truncate BEFORE TRUNCATE ON {S}.audit_log "
        f"FOR EACH STATEMENT EXECUTE FUNCTION {S}.audit_log_immutable()"
    )
    # Privilege layer. No effect if the role is a superuser, which is why the triggers exist too.
    op.execute(
        f"""
        DO $$ BEGIN
            EXECUTE format('REVOKE UPDATE, DELETE, TRUNCATE ON {S}.audit_log FROM %I', current_user);
        END $$
        """
    )

    # --- Row-level security: deny-by-default for every role except the owner (our API) ---------
    for table in TABLES:
        op.execute(f"ALTER TABLE {S}.{table} ENABLE ROW LEVEL SECURITY")
    op.execute(f"REVOKE ALL ON SCHEMA {S} FROM PUBLIC")
    op.execute(f"REVOKE ALL ON ALL TABLES IN SCHEMA {S} FROM PUBLIC")
    op.execute(
        f"""
        DO $$ DECLARE r text; BEGIN
            FOREACH r IN ARRAY ARRAY['anon', 'authenticated'] LOOP
                IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = r) THEN
                    EXECUTE format('REVOKE ALL ON SCHEMA {S} FROM %I', r);
                    EXECUTE format('REVOKE ALL ON ALL TABLES IN SCHEMA {S} FROM %I', r);
                END IF;
            END LOOP;
        END $$
        """
    )


def downgrade() -> None:
    op.execute(f"DROP TABLE IF EXISTS {S}.audit_log CASCADE")  # triggers go with the table
    op.execute(f"DROP FUNCTION IF EXISTS {S}.audit_log_immutable()")
    for table in ["documents", "leave_decisions", "leave_requests", "sessions", "users"]:
        op.execute(f"DROP TABLE IF EXISTS {S}.{table} CASCADE")
