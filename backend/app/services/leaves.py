"""Leave use-cases. One function = one database transaction (commit at the end, rollback on any error).

Business rules live in app/domain (pure, unit-tested); this layer loads data, calls the rules,
persists the result, and writes the audit row in the same transaction.
"""

import contextlib
import functools
import hashlib
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.adapters.blobstore import BlobStore
from app.adapters.sniff import sanitize_filename, sniff_mime
from app.core.clock import org_today, utcnow
from app.core.config import get_settings
from app.domain.calendar import Span, compute_streak, first_overlap
from app.domain.errors import (
    DocumentRequired,
    NotFound,
    Overlap,
    PayloadTooLarge,
    QuotaExceeded,
    UnsupportedFile,
    ValidationFailed,
)
from app.domain.types import OPEN_STATUSES, Action, Role, Route, Status
from app.domain.validation import check_employee_name, validate_leave_dates, validate_reason
from app.domain.workflow import (
    Actor,
    TransitionResult,
    approver_for,
    initial_status,
    route_for,
    transition,
)
from app.models import Document, LeaveDecision, LeaveRequest, User
from app.repositories import leaves as repo
from app.schemas.common import Page
from app.schemas.leave import (
    ChainSpan,
    DecisionIn,
    LeaveDetail,
    LeaveIn,
    LeaveSummary,
    Permissions,
    PreviewIn,
    PreviewOut,
    RecentLeave,
    RespondIn,
)
from app.services import audit
from app.services.context import CurrentUser, RequestCtx

NOT_FOUND_MSG = "We couldn't find that leave request."
AUDIT_ACTION = {
    Action.SUBMIT: "LEAVE_SUBMITTED",
    Action.APPROVE: "LEAVE_APPROVED",
    Action.REJECT: "LEAVE_REJECTED",
    Action.REQUEST_INFO: "LEAVE_INFO_REQUESTED",
    Action.RESPOND: "LEAVE_INFO_RESPONDED",
    Action.CANCEL: "LEAVE_CANCELLED",
}


def atomic[**P, R](fn: Callable[P, R]) -> Callable[P, R]:
    """Roll back (releasing row locks) when a use-case raises. First argument must be the Session."""

    @functools.wraps(fn)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
        session = args[0]
        assert isinstance(session, Session)
        try:
            return fn(*args, **kwargs)
        except BaseException:
            session.rollback()
            raise

    return wrapper


@dataclass(frozen=True)
class RawFile:
    filename: str | None
    data: bytes


@dataclass(frozen=True)
class CheckedFile:
    name: str
    mime: str
    data: bytes
    sha256: bytes


def _fmt(d: date) -> str:
    return f"{d.day} {d.strftime('%b %Y')}"


# --------------------------------------------------------------------------------------- files ---
def check_files(files: list[RawFile]) -> list[CheckedFile]:
    s = get_settings()
    if len(files) > s.max_upload_files:
        raise PayloadTooLarge(f"You can attach up to {s.max_upload_files} files at a time.")
    limit = s.max_upload_mb * 1024 * 1024
    out: list[CheckedFile] = []
    for f in files:
        label = (f.filename or "That file")[:60]
        if len(f.data) > limit:
            raise PayloadTooLarge(
                f"“{label}” is larger than {s.max_upload_mb} MB. Try a smaller photo or a PDF."
            )
        mime = sniff_mime(f.data) if f.data else None
        if mime is None:
            raise UnsupportedFile(
                f"“{label}” isn't a supported file. Please upload a PDF, PNG, JPG or DOCX."
            )
        out.append(
            CheckedFile(
                sanitize_filename(f.filename, mime), mime, f.data, hashlib.sha256(f.data).digest()
            )
        )
    return out


def _check_quota(session: Session, user: CurrentUser, files: list[CheckedFile]) -> None:
    s = get_settings()
    if s.demo_mode and files:
        used = repo.used_storage_bytes(session, user.id)
        if used + sum(len(f.data) for f in files) > s.demo_quota_mb * 1024 * 1024:
            raise QuotaExceeded(
                f"The shared demo allows {s.demo_quota_mb} MB of uploads per person. "
                "Please try a smaller file."
            )


def _store(blobs: BlobStore, files: list[CheckedFile]) -> list[tuple[str, CheckedFile]]:
    stored: list[tuple[str, CheckedFile]] = []
    try:
        for f in files:
            key = f"docs/{uuid.uuid4()}"
            blobs.put(key, f.data, f.mime)
            stored.append((key, f))
    except BaseException:
        _cleanup(blobs, [k for k, _ in stored])
        raise
    return stored


def _cleanup(blobs: BlobStore, keys: list[str]) -> None:
    for key in keys:
        with contextlib.suppress(Exception):  # an orphan blob is harmless (never referenced)
            blobs.delete(key)


def _add_documents(
    session: Session, request_id: int, user: CurrentUser, stored: list[tuple[str, CheckedFile]]
) -> None:
    for key, f in stored:
        session.add(
            Document(
                request_id=request_id,
                uploaded_by=user.id,
                original_name=f.name,
                storage_key=key,
                mime=f.mime,
                size_bytes=len(f.data),
                sha256=f.sha256,
            )
        )


# -------------------------------------------------------------------------------------- queries ---
def _permissions(c: repo.LeaveCtx, user: CurrentUser) -> Permissions:
    state = repo.to_state(c)
    owner = user.id == c.req.employee_id
    status = state.status
    waiting_for: str | None = None
    can_decide = False
    if status is Status.PENDING_MANAGER or status is Status.PENDING_HOD:
        waiting_for = "MANAGER" if status is Status.PENDING_MANAGER else "HOD"
        need = Role.MANAGER if status is Status.PENDING_MANAGER else Role.HOD
        can_decide = not owner and user.id == approver_for(state, status) and user.role is need
    return Permissions(
        can_decide=can_decide,
        can_respond=owner and status is Status.NEEDS_INFO,
        can_cancel=owner and status in OPEN_STATUSES,
        waiting_for=waiting_for,
    )


def get_detail(
    session: Session, user: CurrentUser, request_id: int, ctx: RequestCtx | None = None
) -> LeaveDetail:
    c = repo.load(session, request_id)
    if c is None or not repo.visible_to(c, user.id):
        if ctx is not None:
            audit.record(session, action="AUTHZ_DENIED", entity_type="leave_request",
                         entity_id=request_id, actor=user, ctx=ctx)  # fmt: skip
            session.commit()
        raise NotFound(NOT_FOUND_MSG)  # same answer for "missing" and "not yours"
    summary = repo.to_summary(c.req, c.employee_name, c.document_count)
    recent: list[RecentLeave] = (
        [] if user.id == c.req.employee_id
        else repo.recent_for_employee(session, c.req.employee_id, c.req.id)
    )  # fmt: skip
    return LeaveDetail(
        **summary.model_dump(),
        resume_status=c.req.resume_status,
        decisions=repo.timeline(session, request_id),
        documents=repo.documents(session, request_id),
        recent_leave=recent,
        permissions=_permissions(c, user),
    )


def list_mine(
    session: Session, user: CurrentUser, status: str | None, page: int, size: int
) -> Page[LeaveSummary]:
    size = max(1, min(size, 50))
    page = max(1, page)
    items, total = repo.summaries(
        session,
        repo.mine_conds(user.id, status),
        [LeaveRequest.created_at.desc(), LeaveRequest.id.desc()],
        (page - 1) * size,
        size,
    )
    return Page[LeaveSummary](items=items, total=total, page=page, size=size)


def list_pending(session: Session, user: CurrentUser, page: int, size: int) -> Page[LeaveSummary]:
    size = max(1, min(size, 50))
    page = max(1, page)
    items, total = repo.summaries(
        session,
        [repo.pending_cond(user)],
        [LeaveRequest.created_at.asc(), LeaveRequest.id.asc()],  # oldest first
        (page - 1) * size,
        size,
    )
    return Page[LeaveSummary](items=items, total=total, page=page, size=size)


def preview(session: Session, user: CurrentUser, payload: PreviewIn) -> PreviewOut:
    """Dry run for the live "this will need documents + HOD approval" hint. Writes nothing."""
    s = get_settings()
    route_for(is_extended=False, employee_role=user.role)  # HODs can't apply
    days = validate_leave_dates(payload.from_date, payload.to_date, org_today(s.org_tz))
    spans = repo.active_spans(session, user.id)
    streak = compute_streak(payload.from_date, payload.to_date, [sp for _, sp in spans])
    hit = first_overlap(Span(payload.from_date, payload.to_date), spans)
    route = route_for(is_extended=streak.is_extended, employee_role=user.role)
    chain = {
        Route.MANAGER_ONLY: ["Manager"],
        Route.MANAGER_THEN_HOD: ["Manager", "HOD"],
        Route.HOD_ONLY: ["HOD"],
    }[route]
    conflict = None
    if hit:
        rid, sp = hit
        other = session.get(LeaveRequest, rid)
        conflict = RecentLeave(
            id=rid,
            from_date=sp.from_date,
            to_date=sp.to_date,
            days=sp.days,
            status=other.status if other else "PENDING_MANAGER",
        )
    return PreviewOut(
        days=days,
        streak=streak.streak,
        is_extended=streak.is_extended,
        chain=[ChainSpan(from_date=sp.from_date, to_date=sp.to_date) for sp in streak.chain],
        requires_documents=streak.is_extended,
        approval_chain=chain,
        conflict=conflict,
    )


# ------------------------------------------------------------------------------------- commands ---
@atomic
def submit(
    session: Session,
    blobs: BlobStore,
    user: CurrentUser,
    payload: LeaveIn,
    raw_files: list[RawFile],
    ctx: RequestCtx,
) -> LeaveDetail:
    s = get_settings()
    route_for(is_extended=False, employee_role=user.role)  # HOD: friendly "can't apply" error

    # Collect every form problem at once so the user can fix them in one go.
    errors: dict[str, str] = {}
    try:
        check_employee_name(payload.employee_name, user.name)
    except ValidationFailed as exc:
        errors.update(exc.fields)
        audit.record(session, action="VALIDATION_ABUSE", entity_type="leave_request", actor=user,
                     ctx=ctx, details={"field": "employeeName"})  # fmt: skip
        session.commit()
    try:
        validate_leave_dates(payload.from_date, payload.to_date, org_today(s.org_tz))
    except ValidationFailed as exc:
        errors.update(exc.fields)
    reason = ""
    try:
        reason = validate_reason(payload.reason)
    except ValidationFailed as exc:
        errors.update(exc.fields)
    if errors:
        raise ValidationFailed(errors)

    files = check_files(raw_files)
    _check_quota(session, user, files)

    # Serialise this employee's submissions: two simultaneous requests run one after the other,
    # so the overlap check below always sees the first one.
    emp = session.execute(select(User.manager_id).where(User.id == user.id).with_for_update()).one()
    if emp.manager_id is None:
        raise ValidationFailed(
            {
                "fromDate": "Your account has no approver assigned. Please contact your administrator."
            }
        )
    spans = repo.active_spans(session, user.id)
    new_span = Span(payload.from_date, payload.to_date)
    hit = first_overlap(new_span, spans)
    if hit:
        rid, other = hit
        raise Overlap(
            f"You already have leave from {_fmt(other.from_date)} to {_fmt(other.to_date)} (#{rid})."
        )
    streak = compute_streak(payload.from_date, payload.to_date, [sp for _, sp in spans])
    if streak.is_extended and not files:
        raise DocumentRequired(
            "Leave over 3 days needs at least one supporting document (e.g. medical certificate)."
        )
    route = route_for(is_extended=streak.is_extended, employee_role=user.role)
    status = initial_status(route)

    stored = _store(blobs, files)
    try:
        req = LeaveRequest(
            employee_id=user.id,
            from_date=payload.from_date,
            to_date=payload.to_date,
            days=streak.days,
            streak=streak.streak,
            leave_type=payload.leave_type.value,
            reason=reason,
            is_extended=streak.is_extended,
            status=status.value,
            approver_route=route.value,
            version=1,
        )
        session.add(req)
        session.flush()  # assigns req.id
        session.add(
            LeaveDecision(request_id=req.id, stage="EMPLOYEE", actor_id=user.id,
                          action=Action.SUBMIT.value, from_status=None, to_status=status.value,
                          comment=None)
        )  # fmt: skip
        _add_documents(session, req.id, user, stored)
        audit.record(session, action=AUDIT_ACTION[Action.SUBMIT], entity_type="leave_request",
                     entity_id=req.id, actor=user, ctx=ctx,
                     details={"days": streak.days, "streak": streak.streak,
                              "extended": streak.is_extended, "route": route.value,
                              "documents": len(stored)})  # fmt: skip
        for _key, f in stored:
            audit.record(session, action="DOC_UPLOADED", entity_type="leave_request",
                         entity_id=req.id, actor=user, ctx=ctx,
                         details={"mime": f.mime, "bytes": len(f.data)})  # fmt: skip
        session.commit()
    except BaseException:
        _cleanup(blobs, [k for k, _ in stored])
        raise
    return get_detail(session, user, req.id)


def _apply(
    session: Session,
    req: LeaveRequest,
    result: TransitionResult,
    user: CurrentUser,
    ctx: RequestCtx,
) -> None:
    req.status = result.to_status.value
    req.resume_status = result.resume_status.value if result.resume_status else None
    req.version += 1
    req.updated_at = utcnow()
    session.add(
        LeaveDecision(request_id=req.id, stage=result.stage.value, actor_id=user.id,
                      action=result.action.value, from_status=result.from_status.value,
                      to_status=result.to_status.value, comment=result.comment)
    )  # fmt: skip
    audit.record(session, action=AUDIT_ACTION[result.action], entity_type="leave_request",
                 entity_id=req.id, actor=user, ctx=ctx,
                 details={"stage": result.stage.value, "from": result.from_status.value,
                          "to": result.to_status.value})  # fmt: skip


@atomic
def decide(
    session: Session, user: CurrentUser, request_id: int, payload: DecisionIn, ctx: RequestCtx
) -> LeaveDetail:
    c = repo.load(session, request_id, lock=True)
    if c is None:
        raise NotFound(NOT_FOUND_MSG)
    result = transition(
        repo.to_state(c),
        Actor(user.id, user.role),
        Action(payload.action),
        expected_version=payload.version,
        comment=payload.comment,
    )
    _apply(session, c.req, result, user, ctx)
    session.commit()
    return get_detail(session, user, request_id)


@atomic
def respond(
    session: Session,
    blobs: BlobStore,
    user: CurrentUser,
    request_id: int,
    payload: RespondIn,
    raw_files: list[RawFile],
    ctx: RequestCtx,
) -> LeaveDetail:
    files = check_files(raw_files)
    _check_quota(session, user, files)
    c = repo.load(session, request_id, lock=True)
    if c is None:
        raise NotFound(NOT_FOUND_MSG)
    result = transition(
        repo.to_state(c),
        Actor(user.id, user.role),
        Action.RESPOND,
        expected_version=payload.version,
        comment=payload.comment,
        new_document_count=len(files),
    )
    stored = _store(blobs, files)
    try:
        _apply(session, c.req, result, user, ctx)
        _add_documents(session, c.req.id, user, stored)
        for _key, f in stored:
            audit.record(session, action="DOC_UPLOADED", entity_type="leave_request",
                         entity_id=c.req.id, actor=user, ctx=ctx,
                         details={"mime": f.mime, "bytes": len(f.data)})  # fmt: skip
        session.commit()
    except BaseException:
        _cleanup(blobs, [k for k, _ in stored])
        raise
    return get_detail(session, user, request_id)


@atomic
def cancel(
    session: Session, user: CurrentUser, request_id: int, version: int, ctx: RequestCtx
) -> LeaveDetail:
    c = repo.load(session, request_id, lock=True)
    if c is None:
        raise NotFound(NOT_FOUND_MSG)
    result = transition(
        repo.to_state(c), Actor(user.id, user.role), Action.CANCEL, expected_version=version
    )
    _apply(session, c.req, result, user, ctx)
    session.commit()
    return get_detail(session, user, request_id)


@atomic
def fetch_document(
    session: Session,
    blobs: BlobStore,
    user: CurrentUser,
    request_id: int,
    doc_id: uuid.UUID,
    ctx: RequestCtx,
) -> tuple[Document, bytes]:
    c = repo.load(session, request_id)
    doc = None
    if c is not None and repo.visible_to(c, user.id):
        doc = session.scalar(
            select(Document).where(Document.id == doc_id, Document.request_id == request_id)
        )
    if doc is None:
        audit.record(session, action="AUTHZ_DENIED", entity_type="document",
                     entity_id=doc_id, actor=user, ctx=ctx)  # fmt: skip
        session.commit()
        raise NotFound("We couldn't find that document.")
    data = blobs.get(doc.storage_key)
    audit.record(session, action="DOC_DOWNLOADED", entity_type="leave_request",
                 entity_id=request_id, actor=user, ctx=ctx, details={"document": str(doc.id)})  # fmt: skip
    session.commit()
    return doc, data


def badges(session: Session, user: CurrentUser) -> tuple[int, int]:
    return repo.count_pending(session, user), repo.count_needs_info(session, user.id)
