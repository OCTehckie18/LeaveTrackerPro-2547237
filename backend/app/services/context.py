from dataclasses import dataclass
from uuid import UUID

from app.domain.types import Role


@dataclass(frozen=True)
class CurrentUser:
    id: UUID
    email: str
    name: str
    role: Role
    is_demo: bool


@dataclass(frozen=True)
class RequestCtx:
    ip: str | None
    request_id: str | None
