from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db import alembic_head, database_revision, get_session

router = APIRouter(prefix="/api", tags=["health"])


@router.get("/healthz")
def healthz() -> dict[str, str]:
    """Liveness: no I/O, so a database outage never gets the container restarted."""
    return {"status": "ok"}


@router.get("/readyz", response_model=None)
def readyz(session: Annotated[Session, Depends(get_session)]) -> JSONResponse | dict[str, str]:
    """Readiness: the database answers AND it is at the migration revision this code expects."""
    version = get_settings().app_version
    try:
        current = database_revision(session)
    except Exception:  # DB down, or migrations never ran (no version table)
        return JSONResponse({"status": "unavailable", "version": version}, status_code=503)
    if current != alembic_head():
        return JSONResponse({"status": "migrating", "version": version}, status_code=503)
    return {"status": "ready", "version": version}
