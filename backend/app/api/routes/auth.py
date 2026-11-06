from fastapi import APIRouter, Response

from app.api.deps import COOKIE_NAME, CtxDep, SessionDep, TokenDep, UserDep
from app.core.clock import org_today
from app.core.config import get_settings
from app.core.ratelimit import limiter
from app.schemas.auth import AppInfo, Badges, LoginIn, MeOut, PasswordIn, UserOut
from app.services import auth as auth_service
from app.services.context import CurrentUser

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


def _user_out(u: CurrentUser) -> UserOut:
    return UserOut(id=u.id, email=u.email, name=u.name, role=u.role.value, is_demo=u.is_demo)


@router.post("/login")
def login(body: LoginIn, response: Response, session: SessionDep, ctx: CtxDep) -> UserOut:
    limiter.check(
        f"login:{ctx.ip}", limit=10, window_s=60,
        message="Too many sign-in attempts. Please wait a minute and try again.",
    )  # fmt: skip
    settings = get_settings()
    user, token = auth_service.login(session, body.email, body.password, ctx)
    response.set_cookie(
        COOKIE_NAME,
        token,
        max_age=settings.session_absolute_h * 3600,
        httponly=True,  # JavaScript can never read the session
        secure=settings.cookie_secure,
        samesite="strict",
        path="/",
    )
    return _user_out(user)


@router.post("/logout", status_code=204)
def logout(
    response: Response, session: SessionDep, token: TokenDep, user: UserDep, ctx: CtxDep
) -> None:
    auth_service.logout(session, token, user, ctx)
    response.delete_cookie(COOKIE_NAME, path="/")


@router.get("/me")
def me(session: SessionDep, user: UserDep) -> MeOut:
    s = get_settings()
    pending, needs_info = 0, 0  # real counts arrive with the leave API (next branch)
    return MeOut(
        user=_user_out(user),
        org_today=org_today(s.org_tz),
        badges=Badges(pending_approvals=pending, needs_info=needs_info),
        app=AppInfo(
            max_upload_files=s.max_upload_files,
            max_upload_mb=s.max_upload_mb,
            demo_mode=s.demo_mode,
        ),
    )


@router.post("/password", status_code=204)
def change_password(
    body: PasswordIn, session: SessionDep, token: TokenDep, user: UserDep, ctx: CtxDep
) -> None:
    auth_service.change_password(
        session, user, token, body.current_password, body.new_password, ctx
    )
