import json
from typing import Annotated, Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import Response
from pydantic import BaseModel, ValidationError
from starlette.datastructures import UploadFile

from app.adapters.sniff import INLINE_OK
from app.api.deps import BlobDep, CtxDep, SessionDep, UserDep, require_role
from app.api.errors import fields_from_pydantic
from app.core.config import get_settings
from app.core.ratelimit import limiter
from app.domain.errors import PayloadTooLarge, UnsupportedFile, ValidationFailed
from app.domain.types import Role
from app.schemas.common import Page
from app.schemas.leave import (
    CancelIn,
    DecisionIn,
    LeaveDetail,
    LeaveIn,
    LeaveSummary,
    PreviewIn,
    PreviewOut,
    RespondIn,
)
from app.services import leaves as svc
from app.services.context import CurrentUser

router = APIRouter(prefix="/api/v1/leaves", tags=["leaves"])

CanApply = Annotated[CurrentUser, Depends(require_role(Role.EMPLOYEE, Role.MANAGER, Role.HOD))]
Approver = Annotated[CurrentUser, Depends(require_role(Role.MANAGER, Role.HOD))]


async def parse_body[M: BaseModel](request: Request, model: type[M]) -> tuple[M, list[svc.RawFile]]:
    """Accept plain JSON, or multipart with the same JSON in a `data` part plus `files`."""
    settings = get_settings()
    ctype = request.headers.get("content-type", "").split(";")[0].strip().lower()
    raw: Any
    files: list[svc.RawFile] = []
    try:
        if ctype == "application/json":
            raw = await request.json()
        elif ctype == "multipart/form-data":
            form = await request.form(max_files=settings.max_upload_files + 5, max_fields=10)
            raw = json.loads(str(form.get("data") or "{}"))
            uploads = [f for f in form.getlist("files") if isinstance(f, UploadFile)]
            if len(uploads) > settings.max_upload_files:
                raise PayloadTooLarge(
                    f"You can attach up to {settings.max_upload_files} files at a time."
                )
            limit = settings.max_upload_mb * 1024 * 1024
            for up in uploads:
                data = await up.read(limit + 1)  # never buffer more than limit + 1 bytes
                files.append(svc.RawFile(up.filename, data))
        else:
            raise UnsupportedFile("Please send the request as JSON or a form with files.")
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ValidationFailed({"request": "We couldn't read that request."}) from exc
    try:
        return model.model_validate(raw), files
    except ValidationError as exc:
        raise ValidationFailed(fields_from_pydantic(exc.errors())) from exc


@router.post("/preview")
def preview(body: PreviewIn, session: SessionDep, user: CanApply) -> PreviewOut:
    return svc.preview(session, user, body)


@router.post("", status_code=201)
async def create_leave(
    request: Request, session: SessionDep, blobs: BlobDep, user: CanApply, ctx: CtxDep
) -> LeaveDetail:
    limiter.check(f"submit:{user.id}", limit=20, window_s=60,
                  message="You're submitting too quickly. Please wait a moment.")  # fmt: skip
    payload, files = await parse_body(request, LeaveIn)
    return await run_in_threadpool(svc.submit, session, blobs, user, payload, files, ctx)


@router.get("/mine")
def mine(
    session: SessionDep,
    user: UserDep,
    status: Literal[
        "PENDING_MANAGER", "PENDING_HOD", "NEEDS_INFO", "APPROVED", "REJECTED", "CANCELLED"
    ]
    | None = None,
    page: Annotated[int, Query(ge=1)] = 1,
    size: Annotated[int, Query(ge=1, le=50)] = 20,
) -> Page[LeaveSummary]:
    return svc.list_mine(session, user, status, page, size)


@router.get("/pending")
def pending(
    session: SessionDep,
    user: Approver,
    page: Annotated[int, Query(ge=1)] = 1,
    size: Annotated[int, Query(ge=1, le=50)] = 20,
) -> Page[LeaveSummary]:
    return svc.list_pending(session, user, page, size)


@router.get("/{request_id}")
def detail(request_id: int, session: SessionDep, user: UserDep, ctx: CtxDep) -> LeaveDetail:
    return svc.get_detail(session, user, request_id, ctx)


@router.post("/{request_id}/decision")
def decision(
    request_id: int, body: DecisionIn, session: SessionDep, user: Approver, ctx: CtxDep
) -> LeaveDetail:
    return svc.decide(session, user, request_id, body, ctx)


@router.post("/{request_id}/respond")
async def respond(
    request_id: int,
    request: Request,
    session: SessionDep,
    blobs: BlobDep,
    user: UserDep,
    ctx: CtxDep,
) -> LeaveDetail:
    payload, files = await parse_body(request, RespondIn)
    return await run_in_threadpool(
        svc.respond, session, blobs, user, request_id, payload, files, ctx
    )


@router.post("/{request_id}/cancel")
def cancel(
    request_id: int, body: CancelIn, session: SessionDep, user: UserDep, ctx: CtxDep
) -> LeaveDetail:
    return svc.cancel(session, user, request_id, body.version, ctx)


@router.get("/{request_id}/documents/{doc_id}")
def download(
    request_id: int,
    doc_id: UUID,
    session: SessionDep,
    blobs: BlobDep,
    user: UserDep,
    ctx: CtxDep,
    disposition: Literal["attachment", "inline"] = "attachment",
) -> Response:
    doc, data = svc.fetch_document(session, blobs, user, request_id, doc_id, ctx)
    inline = disposition == "inline" and doc.mime in INLINE_OK
    safe_name = doc.original_name.encode("ascii", "replace").decode().replace('"', "")
    headers = {
        "Content-Disposition": f"{'inline' if inline else 'attachment'}; "
        f"filename=\"{safe_name}\"; filename*=UTF-8''{_quote(doc.original_name)}",
        "X-Content-Type-Options": "nosniff",
        # attachments can't run anything; inline PDFs/images keep the strict default-src 'none'
        "Content-Security-Policy": "default-src 'none'; frame-ancestors 'none'"
        + ("" if inline else "; sandbox"),
        "Cache-Control": "private, no-store",
    }
    return Response(content=data, media_type=doc.mime, headers=headers)


def _quote(name: str) -> str:
    from urllib.parse import quote

    return quote(name, safe="")
