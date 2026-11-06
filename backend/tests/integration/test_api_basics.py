"""Health, error envelope and security headers. Runs without a database."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel, ValidationError

from app.api.errors import register_error_handlers
from app.api.middleware import RequestContextMiddleware
from app.core.config import Settings
from app.domain.errors import Overlap, StaleVersion, ValidationFailed
from app.main import create_app


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app(Settings(app_env="local")), raise_server_exceptions=False)


def test_healthz_is_ok_without_touching_the_database(client: TestClient) -> None:
    r = client.get("/api/healthz")
    assert r.status_code == 200 and r.json() == {"status": "ok"}


def test_security_headers_and_request_id(client: TestClient) -> None:
    r = client.get("/api/healthz")
    assert r.headers["x-content-type-options"] == "nosniff"
    assert r.headers["x-frame-options"] == "DENY"
    assert r.headers["referrer-policy"] == "no-referrer"
    assert r.headers["cache-control"] == "no-store"
    assert len(r.headers["x-request-id"]) == 32
    assert "server" not in r.headers


def test_unknown_route_uses_friendly_envelope(client: TestClient) -> None:
    r = client.get("/api/v1/nope")
    body = r.json()["error"]
    assert r.status_code == 404
    assert body["code"] == "NOT_FOUND" and body["requestId"] == r.headers["x-request-id"]


def test_api_docs_only_exist_locally() -> None:
    local = TestClient(create_app(Settings(app_env="local")))
    assert local.get("/api/docs").status_code == 200
    prod = Settings(
        app_env="production",
        cookie_secure=True,
        database_url="postgresql://u:p@h/db?sslmode=verify-full",
        allowed_origins="https://x.vercel.app",
    )
    assert TestClient(create_app(prod)).get("/api/docs").status_code == 404


def test_domain_and_validation_errors_map_to_status_and_envelope() -> None:
    app = FastAPI()
    app.add_middleware(RequestContextMiddleware)
    register_error_handlers(app)

    class Body(BaseModel):
        fromDate: str
        reason: str

    @app.get("/overlap")
    def overlap() -> None:
        raise Overlap("You already have leave from 1 Nov to 3 Nov (#12).")

    @app.get("/stale")
    def stale() -> None:
        raise StaleVersion("This request was just updated by someone else. Please refresh.")

    @app.get("/invalid")
    def invalid() -> None:
        raise ValidationFailed({"toDate": "End date must be on or after the start date."})

    @app.post("/body")
    def body(b: Body) -> Body:
        return b

    @app.get("/boom")
    def boom() -> None:
        raise RuntimeError("secret internal detail")

    c = TestClient(app, raise_server_exceptions=False)
    assert c.get("/overlap").status_code == 409
    assert c.get("/stale").status_code == 409
    r = c.get("/invalid")
    assert r.status_code == 422 and r.json()["error"]["fields"]["toDate"].startswith("End date")

    r = c.post("/body", json={"fromDate": 5})  # wrong type + missing field
    err = r.json()["error"]
    assert r.status_code == 422 and err["code"] == "VALIDATION_FAILED"
    assert err["fields"]["fromDate"] == "Please pick a valid start date."
    assert err["fields"]["reason"].startswith("Please describe the reason")

    r = c.get("/boom")
    assert r.status_code == 500
    assert "secret internal detail" not in r.text  # never leak internals
    assert r.json()["error"]["code"] == "INTERNAL"


# --- production configuration guards -------------------------------------------------------------
GOOD = dict(
    app_env="production",
    cookie_secure=True,
    database_url="postgresql://u:p@h/db?sslmode=verify-full",
    allowed_origins="https://leavetrackerpro.vercel.app",
)


def test_production_config_accepts_a_safe_setup() -> None:
    assert Settings(**GOOD).is_production  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("override", "needle"),
    [
        ({"cookie_secure": False}, "COOKIE_SECURE"),
        ({"database_url": "postgresql://u:p@h/db"}, "verify-full"),
        ({"allowed_origins": "http://insecure.example"}, "https://"),
        ({"demo_mode": True}, "DEMO_PASSWORD"),
    ],
)
def test_production_config_refuses_unsafe_setups(override: dict[str, object], needle: str) -> None:
    with pytest.raises(ValidationError, match=needle):
        Settings(**{**GOOD, **override})  # type: ignore[arg-type]


def test_database_url_is_forced_to_psycopg3() -> None:
    assert (
        Settings(database_url="postgres://u:p@h/db").sqlalchemy_url
        == "postgresql+psycopg://u:p@h/db"
    )
    assert Settings(database_url="postgresql://u:p@h/db").sqlalchemy_url.startswith(
        "postgresql+psycopg://"
    )
