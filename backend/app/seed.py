"""Idempotent demo data (PRD section 8): demo users plus a request history that shows every status.

Runs only when DEMO_MODE=true. Safe to run on every container start: users are upserted by email and
history is only added for users who have none.
"""

import hashlib
import uuid
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.adapters.blobstore import BlobStore
from app.core.clock import org_today, utcnow
from app.core.config import get_settings
from app.core.security import hash_password, verify_password
from app.domain.types import Role
from app.models import AuditLog, Document, LeaveDecision, LeaveRequest, User

DEMO_USERS = [
    # email, name, role, manager email
    ("hod@acme.test", "Harish Rao", Role.HOD, None),
    ("manager@acme.test", "Meera Nair", Role.MANAGER, "hod@acme.test"),
    ("priya@acme.test", "Priya Sharma", Role.MANAGER, "hod@acme.test"),
    ("john@acme.test", "John Mathew", Role.EMPLOYEE, "manager@acme.test"),
    ("jane@acme.test", "Jane Dsouza", Role.EMPLOYEE, "manager@acme.test"),
    ("raj@acme.test", "Raj Kapoor", Role.EMPLOYEE, "priya@acme.test"),
]

_PDF = (
    b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
    b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
    b"3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 300 120]/Contents 4 0 R"
    b"/Resources<</Font<</F1 5 0 R>>>>>>endobj\n"
    b"4 0 obj<</Length 62>>stream\nBT /F1 14 Tf 20 60 Td (Sample medical certificate - demo) Tj ET\n"
    b"endstream endobj\n5 0 obj<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>endobj\n"
    b"trailer<</Root 1 0 R>>\n%%EOF\n"
)


@dataclass
class Step:
    actor: str  # email
    action: str  # SUBMIT | APPROVE | REJECT | REQUEST_INFO | RESPOND
    stage: str  # EMPLOYEE | MANAGER | HOD
    to_status: str
    comment: str | None = None


@dataclass
class Plan:
    employee: str
    start: int  # days from today
    length: int
    reason: str
    leave_type: str
    route: str
    steps: list[Step]
    resume: str | None = None
    with_doc: bool = False


def _plans() -> list[Plan]:
    s = Step
    return [
        Plan("john@acme.test", 14, 3, "Cousin's wedding out of town", "ANNUAL", "MANAGER_ONLY", [
            s("john@acme.test", "SUBMIT", "EMPLOYEE", "PENDING_MANAGER"),
            s("manager@acme.test", "APPROVE", "MANAGER", "APPROVED", "Enjoy the wedding!"),
        ]),
        Plan("john@acme.test", 30, 5, "Planned surgery and recovery period", "SICK",
             "MANAGER_THEN_HOD", [
            s("john@acme.test", "SUBMIT", "EMPLOYEE", "PENDING_MANAGER"),
            s("manager@acme.test", "APPROVE", "MANAGER", "PENDING_HOD",
              "Documents verified. Forwarding to HOD."),
        ], with_doc=True),
        Plan("john@acme.test", 21, 2, "Short trip with friends", "CASUAL", "MANAGER_ONLY", [
            s("john@acme.test", "SUBMIT", "EMPLOYEE", "PENDING_MANAGER"),
            s("manager@acme.test", "REJECT", "MANAGER", "REJECTED",
              "Release week - the team needs everyone present."),
        ]),
        Plan("john@acme.test", 45, 2, "Personal errands and paperwork", "CASUAL", "MANAGER_ONLY", [
            s("john@acme.test", "SUBMIT", "EMPLOYEE", "PENDING_MANAGER"),
        ]),
        Plan("jane@acme.test", 10, 3, "Not feeling well, doctor visit", "SICK", "MANAGER_ONLY", [
            s("jane@acme.test", "SUBMIT", "EMPLOYEE", "PENDING_MANAGER"),
            s("manager@acme.test", "REQUEST_INFO", "MANAGER", "NEEDS_INFO",
              "Please share the doctor's note."),
        ], resume="PENDING_MANAGER"),
        Plan("jane@acme.test", 40, 5, "Family emergency, travelling abroad", "OTHER",
             "MANAGER_THEN_HOD", [
            s("jane@acme.test", "SUBMIT", "EMPLOYEE", "PENDING_MANAGER"),
        ], with_doc=True),
        Plan("jane@acme.test", 60, 5, "Annual family vacation, tickets attached", "ANNUAL",
             "MANAGER_THEN_HOD", [
            s("jane@acme.test", "SUBMIT", "EMPLOYEE", "PENDING_MANAGER"),
            s("manager@acme.test", "APPROVE", "MANAGER", "PENDING_HOD", "Looks fine."),
            s("hod@acme.test", "APPROVE", "HOD", "APPROVED", "Approved. Have a great trip."),
        ], with_doc=True),
        Plan("raj@acme.test", 12, 2, "Bank and property registration work", "CASUAL",
             "MANAGER_ONLY", [s("raj@acme.test", "SUBMIT", "EMPLOYEE", "PENDING_MANAGER")]),
        Plan("manager@acme.test", 25, 2, "Personal work, will be reachable by phone", "CASUAL",
             "HOD_ONLY", [s("manager@acme.test", "SUBMIT", "EMPLOYEE", "PENDING_HOD")]),
    ]  # fmt: skip


def _upsert_users(session: Session, password: str) -> dict[str, User]:
    users: dict[str, User] = {}
    for email, name, role, mgr in DEMO_USERS:
        user = session.scalar(select(User).where(User.email == email))
        if user is None:
            user = User(email=email, name=name, role=role.value, password_hash="x", is_demo=True)
            session.add(user)
        user.name, user.role, user.is_demo, user.is_active = name, role.value, True, True
        user.manager_id = users[mgr].id if mgr else None
        if not verify_password(user.password_hash, password):
            user.password_hash = hash_password(password)
        user.failed_logins, user.locked_until = 0, None
        session.flush()
        users[email] = user
    return users


def _add_history(session: Session, blobs: BlobStore, users: dict[str, User], today: date) -> int:
    created = 0
    now = utcnow()
    already_seeded = _seeded_user_ids(session)  # computed once, before we add anything
    for plan in _plans():
        emp = users[plan.employee]
        if emp.id in already_seeded:
            continue
        start = today + timedelta(days=plan.start)
        end = start + timedelta(days=plan.length - 1)
        final = plan.steps[-1].to_status
        req = LeaveRequest(
            employee_id=emp.id, from_date=start, to_date=end, days=plan.length, streak=plan.length,
            leave_type=plan.leave_type, reason=plan.reason, is_extended=plan.length > 3,
            status=final, resume_status=plan.resume, approver_route=plan.route,
            version=len(plan.steps),
        )  # fmt: skip
        session.add(req)
        session.flush()
        prev: str | None = None
        for i, step in enumerate(plan.steps):
            at: datetime = now - timedelta(days=len(plan.steps) - i, hours=i)
            actor = users[step.actor]
            session.add(LeaveDecision(
                request_id=req.id, stage=step.stage, actor_id=actor.id, action=step.action,
                from_status=prev, to_status=step.to_status, comment=step.comment, created_at=at,
            ))  # fmt: skip
            session.add(AuditLog(
                ts=at, actor_id=actor.id, actor_role=actor.role,
                action={"SUBMIT": "LEAVE_SUBMITTED", "APPROVE": "LEAVE_APPROVED",
                        "REJECT": "LEAVE_REJECTED", "REQUEST_INFO": "LEAVE_INFO_REQUESTED"}[step.action],
                entity_type="leave_request", entity_id=str(req.id),
                details={"stage": step.stage, "from": prev, "to": step.to_status, "seed": True},
            ))  # fmt: skip
            prev = step.to_status
        if plan.with_doc:
            key = f"docs/{uuid.uuid4()}"
            blobs.put(key, _PDF, "application/pdf")
            session.add(Document(
                request_id=req.id, uploaded_by=emp.id, original_name="medical-certificate.pdf",
                storage_key=key, mime="application/pdf", size_bytes=len(_PDF),
                sha256=hashlib.sha256(_PDF).digest(),
            ))  # fmt: skip
        created += 1
    return created


def _seeded_user_ids(session: Session) -> set[uuid.UUID]:
    """Users who already received demo history (their seed audit rows are flagged seed=true)."""
    rows = session.scalars(
        select(AuditLog.actor_id).where(AuditLog.details["seed"].astext == "true").distinct()
    )
    return {r for r in rows if r is not None}


def seed(session: Session, blobs: BlobStore) -> str:
    settings = get_settings()
    if not settings.demo_mode or settings.demo_password is None:
        raise SystemExit("Refusing to seed: set DEMO_MODE=true and DEMO_PASSWORD.")
    users = _upsert_users(session, settings.demo_password.get_secret_value())
    created = _add_history(session, blobs, users, org_today(settings.org_tz))
    session.commit()
    return f"Seeded {len(users)} demo users and {created} leave requests."
