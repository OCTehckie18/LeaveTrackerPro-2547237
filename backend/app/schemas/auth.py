from datetime import date
from uuid import UUID

from pydantic import Field

from app.schemas.common import CamelModel


class LoginIn(CamelModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=1, max_length=128)


class PasswordIn(CamelModel):
    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=1, max_length=128)


class UserOut(CamelModel):
    id: UUID
    email: str
    name: str
    role: str
    is_demo: bool


class Badges(CamelModel):
    pending_approvals: int
    needs_info: int


class AppInfo(CamelModel):
    max_upload_files: int
    max_upload_mb: int
    demo_mode: bool


class MeOut(CamelModel):
    user: UserOut
    org_today: date
    badges: Badges
    app: AppInfo
