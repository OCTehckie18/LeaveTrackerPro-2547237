"""MG1-MG3: the baseline migration against a REAL Postgres.

Set TEST_DATABASE_URL to an empty, disposable database, e.g.
    postgresql://postgres:postgres@localhost:5432/leavetracker_test
The schema `leave` is dropped and rebuilt, so never point this at real data.
"""

import os
import uuid

import pytest
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import Connection, create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import DBAPIError, IntegrityError

from app.db import BACKEND_DIR

RAW_URL = os.environ.get("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not RAW_URL, reason="TEST_DATABASE_URL not set (needs Postgres)")


def _sa_url(url: str) -> str:
    return (
        url.replace("postgresql://", "postgresql+psycopg://", 1)
        if url.startswith("postgresql://")
        else url
    )


def _config() -> Config:
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    cfg.attributes["url"] = _sa_url(RAW_URL or "")
    return cfg


@pytest.fixture(scope="module")
def engine() -> Engine:
    eng = create_engine(_sa_url(RAW_URL or ""))
    with eng.begin() as c:
        c.execute(text("DROP SCHEMA IF EXISTS leave CASCADE"))
    command.upgrade(_config(), "head")
    return eng


def _user(c: Connection, role: str = "EMPLOYEE", manager: uuid.UUID | None = None) -> uuid.UUID:
    uid = uuid.uuid4()
    c.execute(
        text(
            "INSERT INTO leave.users (id, email, name, password_hash, role, manager_id) "
            "VALUES (:i, :e, 'Test', 'x', :r, :m)"
        ),
        {"i": uid, "e": f"{uid}@x.test", "r": role, "m": manager},
    )
    return uid


def _leave(c: Connection, emp: uuid.UUID, **over: object) -> None:
    row: dict[str, object] = {
        "e": emp,
        "f": "2026-11-10",
        "t": "2026-11-12",
        "d": 3,
        "s": 3,
        "x": False,
        "st": "PENDING_MANAGER",
        "rs": None,
        "reason": "Family function",
        "route": "MANAGER_ONLY",
    }
    row.update(over)
    c.execute(
        text(
            "INSERT INTO leave.leave_requests (employee_id, from_date, to_date, days, streak, "
            "is_extended, status, resume_status, reason, approver_route) "
            "VALUES (:e,:f,:t,:d,:s,:x,:st,:rs,:reason,:route)"
        ),
        row,
    )


def test_mg1_migration_is_at_head_and_matches_models(engine: Engine) -> None:
    head = ScriptDirectory.from_config(_config()).get_current_head()
    with engine.connect() as c:
        assert c.execute(text("SELECT version_num FROM leave.alembic_version")).scalar() == head
    command.check(_config())  # raises if models and migrations have drifted


def test_mg2_upgrade_downgrade_upgrade_roundtrip() -> None:
    command.downgrade(_config(), "base")
    command.upgrade(_config(), "head")


def test_rls_enabled_on_every_table(engine: Engine) -> None:
    with engine.connect() as c:
        rows = c.execute(
            text(
                "SELECT c.relname, c.relrowsecurity FROM pg_class c JOIN pg_namespace n "
                "ON n.oid = c.relnamespace WHERE n.nspname = 'leave' AND c.relkind = 'r' "
                "AND c.relname <> 'alembic_version'"
            )
        ).all()
    assert len(rows) == 6 and all(enabled for _, enabled in rows)


@pytest.mark.parametrize(
    "bad",
    [
        {"d": 4, "s": 4, "t": "2026-11-12"},  # days formula: 10..12 is 3 days, not 4
        {"t": "2026-11-09", "d": -1},  # to < from
        {"d": 3, "s": 2},  # streak < days
        {"x": True},  # extended flag must equal streak > 3
        {"st": "NEEDS_INFO", "rs": None},  # NEEDS_INFO needs resume_status
        {"st": "PENDING_HOD", "rs": "PENDING_HOD"},  # resume_status only valid in NEEDS_INFO
        {"st": "WHATEVER"},  # status enum
        {"reason": "short"},  # reason length
        {"route": "NOBODY"},  # route enum
    ],
)
def test_mg3_check_constraints_reject_invalid_rows(engine: Engine, bad: dict[str, object]) -> None:
    with pytest.raises(IntegrityError), engine.begin() as c:
        _leave(c, _user(c), **bad)


def test_valid_rows_are_accepted(engine: Engine) -> None:
    with engine.begin() as c:
        emp = _user(c)
        _leave(c, emp)
        _leave(c, emp, f="2026-12-01", t="2026-12-05", d=5, s=5, x=True)
        _leave(c, emp, f="2026-12-10", t="2026-12-10", d=1, s=1, st="NEEDS_INFO", rs="PENDING_HOD")


def test_a_user_cannot_be_their_own_manager(engine: Engine) -> None:
    with pytest.raises(IntegrityError), engine.begin() as c:
        uid = uuid.uuid4()
        c.execute(
            text(
                "INSERT INTO leave.users (id,email,name,password_hash,role,manager_id) "
                "VALUES (:i,'self@x.test','S','x','MANAGER',:i)"
            ),
            {"i": uid},
        )


def test_email_is_case_insensitive_unique(engine: Engine) -> None:
    with engine.begin() as c:
        c.execute(
            text(
                "INSERT INTO leave.users (email,name,password_hash,role) "
                "VALUES ('Case@X.test','A','x','EMPLOYEE')"
            )
        )
    with pytest.raises(IntegrityError), engine.begin() as c:
        c.execute(
            text(
                "INSERT INTO leave.users (email,name,password_hash,role) "
                "VALUES ('case@x.TEST','B','x','EMPLOYEE')"
            )
        )


def test_audit_log_is_append_only(engine: Engine) -> None:
    with engine.begin() as c:
        c.execute(text("INSERT INTO leave.audit_log (action, entity_type) VALUES ('T','test')"))
    for statement in (
        "UPDATE leave.audit_log SET action = 'X'",
        "DELETE FROM leave.audit_log",
        "TRUNCATE leave.audit_log",
    ):
        with pytest.raises(DBAPIError), engine.begin() as c:  # privilege error or trigger error
            c.execute(text(statement))
    with engine.connect() as c:
        assert c.execute(text("SELECT count(*) FROM leave.audit_log")).scalar_one() >= 1


def test_readyz_reports_ready_against_a_migrated_database(
    engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    from fastapi.testclient import TestClient

    from app.core.config import get_settings
    from app.db import get_engine, get_session_factory
    from app.main import create_app

    monkeypatch.setenv("DATABASE_URL", RAW_URL or "")
    for fn in (get_settings, get_engine, get_session_factory):
        fn.cache_clear()
    try:
        with TestClient(create_app()) as client:
            r = client.get("/api/readyz")
            assert r.status_code == 200 and r.json()["status"] == "ready"
            with engine.begin() as c:
                c.execute(text("UPDATE leave.alembic_version SET version_num = '0000'"))
            assert client.get("/api/readyz").status_code == 503  # behind on migrations
            with engine.begin() as c:
                c.execute(text("UPDATE leave.alembic_version SET version_num = '0001'"))
    finally:
        for fn in (get_settings, get_engine, get_session_factory):
            fn.cache_clear()
