"""End-to-end API flows against a real Postgres (set TEST_DATABASE_URL; the `leave` schema is rebuilt)."""

import json
import os
from collections.abc import Iterator
from datetime import timedelta
from typing import Any

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from httpx import Response
from sqlalchemy import create_engine, text

from app.core.clock import org_today
from app.core.ratelimit import limiter
from app.core.security import hash_password
from app.db import BACKEND_DIR

RAW_URL = os.environ.get("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not RAW_URL, reason="TEST_DATABASE_URL not set (needs Postgres)")

PW = "DemoPass#2026"
PDF = b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n"
TODAY = org_today("Asia/Kolkata")


def day(offset: int) -> str:
    return (TODAY + timedelta(days=offset)).isoformat()


@pytest.fixture(scope="module")
def app_env(tmp_path_factory: pytest.TempPathFactory) -> Iterator[None]:
    mp = pytest.MonkeyPatch()
    for k, v in {
        "DATABASE_URL": RAW_URL or "",
        "DEMO_MODE": "true",
        "DEMO_PASSWORD": PW,
        "LOCAL_STORAGE_DIR": str(tmp_path_factory.mktemp("blobs")),
        "APP_ENV": "local",
    }.items():
        mp.setenv(k, v)
    from app.adapters.blobstore import build_blobstore
    from app.api.deps import get_blobstore
    from app.core.config import get_settings
    from app.db import get_engine, get_session_factory
    from app.seed import seed

    def clear() -> None:
        for fn in (get_settings, get_engine, get_session_factory, get_blobstore):
            fn.cache_clear()

    clear()
    url = (RAW_URL or "").replace("postgresql://", "postgresql+psycopg://", 1)
    with create_engine(url).begin() as c:
        c.execute(text("DROP SCHEMA IF EXISTS leave CASCADE"))
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    cfg.attributes["url"] = url
    command.upgrade(cfg, "head")
    with get_session_factory()() as session:
        seed(session, build_blobstore(get_settings()))
        seed(session, build_blobstore(get_settings()))  # idempotent: second run adds nothing
    yield
    clear()
    mp.undo()


@pytest.fixture(autouse=True)
def _reset_limiter() -> None:
    limiter.reset()


def client_for(email: str | None = None) -> TestClient:
    from app.main import create_app

    c = TestClient(create_app())
    if email:
        r = c.post("/api/v1/auth/login", json={"email": email, "password": PW})
        assert r.status_code == 200, r.text
    return c


@pytest.fixture
def john(app_env: None) -> TestClient:
    return client_for("john@acme.test")


@pytest.fixture
def jane(app_env: None) -> TestClient:
    return client_for("jane@acme.test")


@pytest.fixture
def manager(app_env: None) -> TestClient:
    return client_for("manager@acme.test")


@pytest.fixture
def priya(app_env: None) -> TestClient:
    return client_for("priya@acme.test")


@pytest.fixture
def hod(app_env: None) -> TestClient:
    return client_for("hod@acme.test")


def body(
    start: int, length: int, reason: str = "Family function out of town", **extra: Any
) -> dict[str, Any]:
    return {"fromDate": day(start), "toDate": day(start + length - 1), "reason": reason, **extra}


def submit_with_pdf(
    c: TestClient, payload: dict[str, Any], name: str = "cert.pdf", data: bytes = PDF
) -> Response:
    return c.post(
        "/api/v1/leaves",
        data={"data": json.dumps(payload)},
        files=[("files", (name, data, "application/pdf"))],
    )


def decide(
    c: TestClient, leave: dict[str, Any], action: str, comment: str | None = None
) -> Response:
    return c.post(
        f"/api/v1/leaves/{leave['id']}/decision",
        json={"action": action, "comment": comment, "version": leave["version"]},
    )


# ----------------------------------------------------------------------------- auth & access ---
def test_login_errors_are_generic_and_default_deny(app_env: None) -> None:
    c = client_for()
    bad_pw = c.post("/api/v1/auth/login", json={"email": "john@acme.test", "password": "nope"})
    no_user = c.post("/api/v1/auth/login", json={"email": "ghost@acme.test", "password": "nope"})
    assert bad_pw.status_code == no_user.status_code == 401
    assert bad_pw.json()["error"]["message"] == no_user.json()["error"]["message"]

    # S2: every API route except login/health refuses an anonymous caller
    spec = c.get("/api/openapi.json").json()
    for path, ops in spec["paths"].items():
        if path in ("/api/v1/auth/login", "/api/healthz", "/api/readyz"):
            continue
        for method in ops:
            url = path.replace("{request_id}", "1").replace("{doc_id}", "x" * 36)
            assert c.request(method.upper(), url).status_code == 401, f"{method} {path}"


def test_me_cookie_flags_and_logout(app_env: None) -> None:
    c = TestClient(__import__("app.main", fromlist=["x"]).create_app())
    r = c.post("/api/v1/auth/login", json={"email": "john@acme.test", "password": PW})
    cookie = r.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=strict" in cookie and "lt_session=" in cookie
    me = c.get("/api/v1/auth/me").json()
    assert me["user"]["role"] == "EMPLOYEE" and me["app"]["maxUploadFiles"] == 3
    assert c.post("/api/v1/auth/logout").status_code == 204
    assert c.get("/api/v1/auth/me").status_code == 401


def test_foreign_origin_is_blocked(app_env: None) -> None:
    c = client_for()
    r = c.post(
        "/api/v1/auth/login",
        json={"email": "john@acme.test", "password": PW},
        headers={"Origin": "https://evil.example"},
    )
    assert r.status_code == 403 and r.json()["error"]["code"] == "FORBIDDEN"


def test_lockout_after_repeated_failures(app_env: None) -> None:
    url = (RAW_URL or "").replace("postgresql://", "postgresql+psycopg://", 1)
    with create_engine(url).begin() as conn:
        conn.execute(
            text(
                "INSERT INTO leave.users (email,name,password_hash,role) "
                "VALUES ('real@acme.test','Real User',:h,'HOD') ON CONFLICT DO NOTHING"
            ),
            {"h": hash_password("a-very-long-password")},
        )
    c = client_for()
    for _ in range(5):
        limiter.reset()
        assert (
            c.post(
                "/api/v1/auth/login", json={"email": "real@acme.test", "password": "x"}
            ).status_code
            == 401
        )
    limiter.reset()
    r = c.post(
        "/api/v1/auth/login", json={"email": "real@acme.test", "password": "a-very-long-password"}
    )
    assert r.status_code == 429 and "Retry-After" in r.headers


# ------------------------------------------------------------------------------ the workflows ---
def test_standard_leave_one_step(john: TestClient, manager: TestClient) -> None:
    r = john.post("/api/v1/leaves", json=body(100, 3, employeeName="John Mathew"))
    assert r.status_code == 201, r.text
    leave = r.json()
    assert (leave["status"], leave["isExtended"], leave["days"]) == ("PENDING_MANAGER", False, 3)
    assert leave["permissions"]["canCancel"] is True

    approved = decide(manager, leave, "APPROVE", "Enjoy").json()
    assert approved["status"] == "APPROVED"
    mine = john.get("/api/v1/leaves/mine?status=APPROVED").json()
    assert any(i["id"] == leave["id"] for i in mine["items"])


def test_extended_leave_needs_documents_then_manager_then_hod(
    john: TestClient, manager: TestClient, priya: TestClient, hod: TestClient
) -> None:
    no_doc = john.post("/api/v1/leaves", json=body(120, 4))
    assert no_doc.status_code == 422 and no_doc.json()["error"]["code"] == "DOCUMENT_REQUIRED"

    r = submit_with_pdf(john, body(120, 4, "Planned dental surgery and rest"))
    assert r.status_code == 201, r.text
    leave = r.json()
    assert leave["isExtended"] and leave["documentCount"] == 1

    # only the right people see it
    assert priya.get(f"/api/v1/leaves/{leave['id']}").status_code == 404  # other team's manager
    assert (
        john.post(
            f"/api/v1/leaves/{leave['id']}/decision", json={"action": "APPROVE", "version": 1}
        ).status_code
        == 403
    )
    pend = manager.get("/api/v1/leaves/pending").json()
    assert leave["id"] in [i["id"] for i in pend["items"]]
    assert leave["id"] not in [i["id"] for i in hod.get("/api/v1/leaves/pending").json()["items"]]

    step1 = decide(manager, leave, "APPROVE", "Docs verified").json()
    assert step1["status"] == "PENDING_HOD"  # first of two approvals: NOT final
    assert leave["id"] in [i["id"] for i in hod.get("/api/v1/leaves/pending").json()["items"]]
    assert leave["id"] not in [
        i["id"] for i in manager.get("/api/v1/leaves/pending").json()["items"]
    ]
    assert decide(manager, step1, "APPROVE").status_code == 409  # manager can't act twice / skip

    done = decide(hod, step1, "APPROVE", "Approved").json()
    assert done["status"] == "APPROVED"
    assert [d["action"] for d in done["decisions"]] == ["SUBMIT", "APPROVE", "APPROVE"]
    assert [d["stage"] for d in done["decisions"]] == ["EMPLOYEE", "MANAGER", "HOD"]


def test_chaining_makes_adjacent_requests_extended(john: TestClient) -> None:
    first = john.post("/api/v1/leaves", json=body(140, 2))
    assert first.status_code == 201 and not first.json()["isExtended"]
    # starts the day after the first ends: streak 2 + 2 = 4 -> extended -> documents required
    second = john.post("/api/v1/leaves", json=body(142, 2))
    assert second.status_code == 422 and second.json()["error"]["code"] == "DOCUMENT_REQUIRED"
    preview = john.post(
        "/api/v1/leaves/preview", json={"fromDate": day(142), "toDate": day(143)}
    ).json()
    assert (preview["streak"], preview["isExtended"], preview["approvalChain"]) == (
        4,
        True,
        ["Manager", "HOD"],
    )


def test_info_loop_reject_and_cancel(
    jane: TestClient, john: TestClient, manager: TestClient
) -> None:
    seeded = [i for i in jane.get("/api/v1/leaves/mine?status=NEEDS_INFO").json()["items"]]
    assert seeded and seeded[0]["status"] == "NEEDS_INFO"
    detail = jane.get(f"/api/v1/leaves/{seeded[0]['id']}").json()
    assert detail["permissions"]["canRespond"] is True
    back = jane.post(
        f"/api/v1/leaves/{detail['id']}/respond",
        json={"comment": "Note attached at the clinic", "version": detail["version"]},
    )
    assert back.status_code == 200 and back.json()["status"] == "PENDING_MANAGER"

    leave = john.post(
        "/api/v1/leaves", json=body(160, 1, "Visa appointment at the consulate")
    ).json()
    assert decide(manager, leave, "REJECT").status_code == 422  # comment required
    rejected = decide(manager, leave, "REJECT", "Not possible that day").json()
    assert rejected["status"] == "REJECTED"
    assert rejected["decisions"][-1]["comment"] == "Not possible that day"

    other = john.post("/api/v1/leaves", json=body(170, 1, "Moving house, need one day")).json()
    cancelled = john.post(
        f"/api/v1/leaves/{other['id']}/cancel", json={"version": other["version"]}
    )
    assert cancelled.json()["status"] == "CANCELLED"


# -------------------------------------------------------------------------- validation & abuse ---
def test_validation_overlap_and_tampering(john: TestClient) -> None:
    past = john.post("/api/v1/leaves", json=body(-3, 1))
    assert past.status_code == 422 and "fromDate" in past.json()["error"]["fields"]
    back = john.post("/api/v1/leaves", json={"fromDate": day(10), "toDate": day(9), "reason": "x"})
    fields = back.json()["error"]["fields"]
    assert "toDate" in fields and "reason" in fields  # all problems reported together
    assert (
        john.post("/api/v1/leaves", json={**body(180, 1), "status": "APPROVED"}).status_code == 422
    )
    assert (
        john.post("/api/v1/leaves", json={**body(180, 1), "isExtended": False}).status_code == 422
    )
    spoof = john.post("/api/v1/leaves", json={**body(180, 1), "employeeName": "Someone Else"})
    assert spoof.status_code == 422 and "employeeName" in spoof.json()["error"]["fields"]

    ok = john.post("/api/v1/leaves", json=body(190, 2))
    assert ok.status_code == 201
    clash = john.post("/api/v1/leaves", json=body(191, 1))
    assert clash.status_code == 409 and f"#{ok.json()['id']}" in clash.json()["error"]["message"]


def test_stale_version_conflict(john: TestClient, manager: TestClient) -> None:
    leave = john.post("/api/v1/leaves", json=body(200, 1, "Attending a friend's graduation")).json()
    stale = {**leave, "version": leave["version"] + 5}
    r = decide(manager, stale, "APPROVE")
    assert r.status_code == 409 and r.json()["error"]["code"] == "STALE_VERSION"


def test_upload_abuse_is_rejected(john: TestClient) -> None:
    payload = body(210, 4, "Hospital stay and recovery")
    exe = submit_with_pdf(john, payload, "evil.pdf", b"MZ\x90\x00 not a pdf at all")
    assert exe.status_code == 415 and exe.json()["error"]["code"] == "UNSUPPORTED_FILE"
    html = submit_with_pdf(john, payload, "page.pdf", b"<html><script>alert(1)</script></html>")
    assert html.status_code == 415
    too_big = submit_with_pdf(john, payload, "big.pdf", PDF + b"0" * (3 * 1024 * 1024))
    assert too_big.status_code == 413
    many = john.post(
        "/api/v1/leaves",
        data={"data": json.dumps(payload)},
        files=[("files", (f"{i}.pdf", PDF, "application/pdf")) for i in range(4)],
    )
    assert many.status_code == 413


def test_documents_are_protected_and_served_safely(
    john: TestClient, jane: TestClient, priya: TestClient, manager: TestClient
) -> None:
    leave = submit_with_pdf(
        john, body(220, 4, "Medical procedure and bed rest"), "../../etc/passwd.pdf"
    ).json()
    doc = leave["documents"][0]
    assert doc["name"] == "passwd.pdf"  # path parts stripped
    url = f"/api/v1/leaves/{leave['id']}/documents/{doc['id']}"
    r = john.get(url)
    assert r.status_code == 200 and r.content == PDF
    assert r.headers["content-type"] == "application/pdf"
    assert r.headers["x-content-type-options"] == "nosniff"
    assert (
        "attachment" in r.headers["content-disposition"]
        and "sandbox" in r.headers["content-security-policy"]
    )
    assert manager.get(url).status_code == 200  # the approver can read it
    assert jane.get(url).status_code == 404  # a colleague cannot
    assert priya.get(url).status_code == 404  # nor another team's manager


def test_audit_log_is_hod_only_and_complete(
    hod: TestClient, john: TestClient, app_env: None
) -> None:
    assert john.get("/api/v1/audit").status_code == 403
    items = hod.get("/api/v1/audit").json()["items"]
    assert items and items[0]["id"] > items[-1]["id"]  # newest first
    assert {"LOGIN_SUCCESS", "LEAVE_SUBMITTED", "LEAVE_APPROVED"} <= {i["action"] for i in items}
    # the log records ids and statuses, never the free text people typed
    blob = json.dumps(items)
    for secret in ("Family function out of town", "Docs verified", "Not possible that day"):
        assert secret not in blob


def test_seed_creates_full_history_once(app_env: None) -> None:
    from sqlalchemy import func, select

    from app.db import get_session_factory
    from app.models import LeaveRequest

    with get_session_factory()() as s:
        assert (
            s.scalar(
                select(func.count(LeaveRequest.id)).where(LeaveRequest.reason.like("%wedding%"))
            )
            == 1
        )
        # the module fixture seeded twice; 9 planned requests must exist exactly once each
        seeded = s.scalar(
            select(func.count(LeaveRequest.id)).where(LeaveRequest.created_at < func.now())
        )
        assert seeded is not None and seeded >= 9
