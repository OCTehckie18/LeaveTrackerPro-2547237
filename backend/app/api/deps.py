"""FastAPI dependencies: who is calling, what role they need, where they come from."""

import ipaddress
from collections.abc import Callable
from functools import lru_cache
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from app.adapters.blobstore import BlobStore, build_blobstore
from app.core.config import get_settings
from app.core.logging import request_id_var
from app.db import get_session
from app.domain.errors import Forbidden, Unauthenticated
from app.domain.types import Role
from app.services import auth as auth_service
from app.services.context import CurrentUser, RequestCtx

COOKIE_NAME = "lt_session"

SessionDep = Annotated[Session, Depends(get_session)]


def client_ip(request: Request) -> str | None:
    """With N trusted proxy hops in front of us, the client is the Nth entry from the right of
    X-Forwarded-For (anything further left is client-supplied and can be forged)."""
    hops = get_settings().trusted_proxy_hops
    candidate: str | None = request.client.host if request.client else None
    if hops > 0:
        parts = [
            p.strip() for p in request.headers.get("x-forwarded-for", "").split(",") if p.strip()
        ]
        if len(parts) >= hops:
            candidate = parts[-hops]
    try:
        return str(ipaddress.ip_address(candidate)) if candidate else None
    except ValueError:
        return None


def get_ctx(request: Request) -> RequestCtx:
    return RequestCtx(ip=client_ip(request), request_id=request_id_var.get())


CtxDep = Annotated[RequestCtx, Depends(get_ctx)]


def session_token(request: Request) -> str:
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        raise Unauthenticated("Please sign in to continue.")
    return token


TokenDep = Annotated[str, Depends(session_token)]


def current_user(session: SessionDep, token: TokenDep) -> CurrentUser:
    return auth_service.resolve_session(session, token)


UserDep = Annotated[CurrentUser, Depends(current_user)]


def require_role(*roles: Role) -> Callable[[CurrentUser], CurrentUser]:
    """Every route declares who may call it; a test fails for any route that doesn't."""

    def dependency(user: UserDep) -> CurrentUser:
        if user.role not in roles:
            raise Forbidden("You don't have access to that page.")
        return user

    return dependency


@lru_cache
def get_blobstore() -> BlobStore:
    return build_blobstore(get_settings())


BlobDep = Annotated[BlobStore, Depends(get_blobstore)]
