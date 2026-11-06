"""One friendly error envelope for every failure (docs/ARCHITECTURE.md section 6)."""

import logging
from collections.abc import Sequence
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.logging import request_id_var
from app.domain.errors import DomainError, RateLimited

log = logging.getLogger("app.errors")

HTTP_STATUS: dict[str, int] = {
    "VALIDATION_FAILED": 422,
    "DOCUMENT_REQUIRED": 422,
    "OVERLAP": 409,
    "STALE_VERSION": 409,
    "INVALID_TRANSITION": 409,
    "UNAUTHENTICATED": 401,
    "FORBIDDEN": 403,
    "NOT_FOUND": 404,
    "PAYLOAD_TOO_LARGE": 413,
    "QUOTA_EXCEEDED": 413,
    "UNSUPPORTED_FILE": 415,
    "RATE_LIMITED": 429,
    "SERVICE_UNAVAILABLE": 503,
    "INTERNAL": 500,
}

# Friendly text for the type/format failures Pydantic catches before our rules run.
FIELD_MESSAGES: dict[str, str] = {
    "employeeName": "Please enter your name.",
    "fromDate": "Please pick a valid start date.",
    "toDate": "Please pick a valid end date.",
    "reason": "Please describe the reason (10–500 characters).",
    "leaveType": "Choose a leave type.",
    "comment": "Please check your comment.",
    "action": "Choose Approve, Reject or Ask for information.",
    "version": "Please refresh the page and try again.",
    "email": "Please enter a valid email address.",
    "password": "Please enter your password.",
}


def error_response(
    code: str,
    message: str,
    *,
    fields: dict[str, str] | None = None,
    status: int | None = None,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    body: dict[str, Any] = {
        "error": {
            "code": code,
            "message": message,
            "fields": fields or {},
            "requestId": request_id_var.get(),
        }
    }
    return JSONResponse(body, status_code=status or HTTP_STATUS.get(code, 500), headers=headers)


def _domain_handler(_: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, DomainError)
    headers = {"Retry-After": str(exc.retry_after)} if isinstance(exc, RateLimited) else None
    return error_response(exc.code, exc.message, fields=exc.fields, headers=headers)


def fields_from_pydantic(errors: Sequence[Any]) -> dict[str, str]:
    """Turn Pydantic error dicts into {camelCaseField: friendly message}."""
    fields: dict[str, str] = {}
    for err in errors:
        loc = [str(p) for p in err["loc"] if p not in ("body", "query", "path")]
        name = loc[-1] if loc else "request"
        fields.setdefault(name, FIELD_MESSAGES.get(name, "This value isn't valid."))
    return fields


def _validation_handler(_: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, RequestValidationError)
    fields = fields_from_pydantic(exc.errors())
    message = (
        "Please fix the highlighted fields." if fields else "We couldn't understand that request."
    )
    return error_response("VALIDATION_FAILED", message, fields=fields)


def _http_handler(_: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, StarletteHTTPException)
    if exc.status_code == 404:
        return error_response("NOT_FOUND", "We couldn't find what you were looking for.")
    if exc.status_code == 405:
        return error_response("NOT_FOUND", "That action isn't available here.", status=405)
    return error_response("INTERNAL", "Something went wrong.", status=exc.status_code)


def _unhandled_handler(_: Request, exc: Exception) -> JSONResponse:
    # Details go to the log only, never to the client.
    log.error("unhandled exception", exc_info=exc)
    rid = request_id_var.get()
    return error_response(
        "INTERNAL",
        "Something went wrong on our side. Please try again"
        + (f" (reference: {rid})." if rid else "."),
    )


def register_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(DomainError, _domain_handler)
    app.add_exception_handler(RequestValidationError, _validation_handler)
    app.add_exception_handler(StarletteHTTPException, _http_handler)
    app.add_exception_handler(Exception, _unhandled_handler)
