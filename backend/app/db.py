"""Engine and session factory (sync SQLAlchemy 2.0 + psycopg 3)."""

from collections.abc import Iterator
from functools import lru_cache
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import Engine, create_engine, event, text
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings

BACKEND_DIR = Path(__file__).resolve().parents[1]


@lru_cache
def get_engine() -> Engine:
    settings = get_settings()
    engine = create_engine(
        settings.sqlalchemy_url,
        pool_size=settings.db_pool_size,
        max_overflow=2,
        pool_pre_ping=True,  # survive the pooler dropping idle connections
        pool_recycle=1800,
    )

    @event.listens_for(engine, "connect")
    def _on_connect(dbapi_conn, _record) -> None:  # type: ignore[no-untyped-def]
        with dbapi_conn.cursor() as cur:
            cur.execute("SET statement_timeout = 5000")  # 5 s: nothing here should be slower
            cur.execute("SET TIME ZONE 'UTC'")
        dbapi_conn.commit()

    return engine


@lru_cache
def get_session_factory() -> sessionmaker[Session]:
    return sessionmaker(bind=get_engine(), expire_on_commit=False)


def get_session() -> Iterator[Session]:
    """FastAPI dependency. Services open their own `with session.begin():` block."""
    with get_session_factory()() as session:
        yield session


@lru_cache
def alembic_head() -> str:
    """The migration revision this code expects the database to be at."""
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    head = ScriptDirectory.from_config(cfg).get_current_head()
    return head or ""


def database_revision(session: Session) -> str | None:
    row = session.execute(text("SELECT version_num FROM leave.alembic_version")).first()
    return row[0] if row else None
