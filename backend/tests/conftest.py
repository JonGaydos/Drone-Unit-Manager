"""Shared pytest fixtures for the backend test suite.

Each test runs against a fresh pair of temporary SQLite *file* databases (one
primary, one telemetry) created under pytest's ``tmp_path``. Temp files are used
rather than ``:memory:`` because TestClient runs requests on a separate thread
and a file-backed SQLite DB is shared across connections cleanly.

The harness handles both ways application code obtains a session:

* via the FastAPI dependencies ``get_db`` / ``get_telemetry_db`` — overridden
  through ``app.dependency_overrides``;
* via ``app.database.SessionLocal()`` called directly (e.g. ``main.seed_defaults``
  and the health check) — the module-level engine/sessionmaker objects are
  monkeypatched to point at the temp engines.

The app's real ``lifespan`` (which runs Alembic migrations and starts the
background scheduler) is intentionally NOT triggered: ``TestClient(app)`` is used
without entering it as a context manager, and the schema is built here with
``create_all``. Schema parity (create_all == alembic head) is verified elsewhere.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

import app.database as database
from app.database import Base, get_db, get_telemetry_db
import app.models  # noqa: F401 - register all ORM models on Base.metadata
from app.models.telemetry import TelemetryBase
from app.models.user import User
from app.main import app
from app.routers.auth import hash_password, create_token


def _make_engine(path):
    """Create a SQLite file engine with the same pragmas the app uses."""
    engine = create_engine(
        f"sqlite:///{path}",
        connect_args={"check_same_thread": False},
        echo=False,
    )

    @event.listens_for(engine, "connect")
    def _set_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    return engine


@pytest.fixture()
def _engines(tmp_path, monkeypatch):
    """Build temp main + telemetry engines, create schema, and rebind the app.

    Yields ``(SessionLocal, TelemetrySessionLocal)`` bound to the temp engines.
    Monkeypatches the module-level engine/sessionmaker objects so direct
    ``SessionLocal()`` use inside the app also targets the temp DBs.
    """
    main_engine = _make_engine(tmp_path / "test_main.db")
    telemetry_engine = _make_engine(tmp_path / "test_telemetry.db")

    Base.metadata.create_all(bind=main_engine)
    TelemetryBase.metadata.create_all(bind=telemetry_engine)

    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=main_engine)
    TestingTelemetrySessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=telemetry_engine)

    # Rebind module-level objects for any code path that calls SessionLocal()
    # directly instead of going through the FastAPI dependency.
    monkeypatch.setattr(database, "engine", main_engine)
    monkeypatch.setattr(database, "telemetry_engine", telemetry_engine)
    monkeypatch.setattr(database, "SessionLocal", TestingSessionLocal)
    monkeypatch.setattr(database, "TelemetrySessionLocal", TestingTelemetrySessionLocal)

    yield TestingSessionLocal, TestingTelemetrySessionLocal

    main_engine.dispose()
    telemetry_engine.dispose()


@pytest.fixture()
def db(_engines):
    """A Session bound to the temp main engine, for seeding and assertions."""
    TestingSessionLocal, _ = _engines
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def telemetry_db(_engines):
    """A Session bound to the temp telemetry engine, for seeding and assertions.

    Telemetry rows live in a SEPARATE engine from the main DB; mirrors the
    ``db`` fixture but bound to the telemetry sessionmaker.
    """
    _, TestingTelemetrySessionLocal = _engines
    session = TestingTelemetrySessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def client(_engines):
    """TestClient with get_db / get_telemetry_db overridden to the temp DBs."""
    TestingSessionLocal, TestingTelemetrySessionLocal = _engines

    def override_get_db():
        session = TestingSessionLocal()
        try:
            yield session
        finally:
            session.close()

    def override_get_telemetry_db():
        session = TestingTelemetrySessionLocal()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_telemetry_db] = override_get_telemetry_db
    # Instantiate WITHOUT the context-manager form so the app lifespan (Alembic
    # migrations + background scheduler) does not run; schema is built via
    # create_all in the _engines fixture instead.
    test_client = TestClient(app)
    yield test_client
    app.dependency_overrides.clear()


def _seed_user(session, *, username, role, password):
    """Insert a User with a properly hashed password and return it."""
    user = User(
        username=username,
        password_hash=hash_password(password),
        display_name=username.title(),
        role=role,
        is_active=True,
    )
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


# Plaintext passwords satisfy the app's policy (>=12 chars, upper, digit) so the
# same credentials can be reused for live login tests.
ADMIN_PASSWORD = "AdminPassw0rd!"
PILOT_PASSWORD = "PilotPassw0rd!"


@pytest.fixture()
def admin_user(db):
    return _seed_user(db, username="admin", role="admin", password=ADMIN_PASSWORD)


@pytest.fixture()
def pilot_user(db):
    return _seed_user(db, username="pilot", role="pilot", password=PILOT_PASSWORD)


@pytest.fixture()
def admin_headers(admin_user):
    token = create_token(admin_user.id)
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture()
def pilot_headers(pilot_user):
    token = create_token(pilot_user.id)
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(autouse=True)
def _reset_login_rate_limiter():
    """Clear the auth module's in-memory login rate limiter before each test.

    ``app.routers.auth`` keeps a process-global per-IP login attempt counter
    (``_login_attempts``, limit 5 per 60s window, plus a ``_last_sweep``
    timestamp). TestClient sends every request from the same host, so without
    a reset the 6th login POST suite-wide would 429 and poison later modules.
    """
    from app.routers import auth

    auth._login_attempts.clear()
    auth._last_sweep = 0.0
    yield


@pytest.fixture()
def mock_httpx(monkeypatch):
    """Intercept outbound httpx calls so app code never hits the network.

    Covers BOTH ways the app makes HTTP requests:

    * module-level ``httpx.get`` / ``httpx.post`` (geocode router,
      sync_manager);
    * ``httpx.Client(...).get(...)`` / ``.post(...)`` and the context-manager
      form ``with httpx.Client(...) as c:`` (weather and adsb routers,
      skydio integration).

    Both paths are routed through a single ``httpx.MockTransport`` driven by a
    handler you supply. The handler takes an ``httpx.Request`` and returns an
    ``httpx.Response``.

    Usage in a test::

        def test_x(mock_httpx):
            def handler(request):
                assert "nominatim" in str(request.url)
                return httpx.Response(200, json=[{"lat": "1.0", "lon": "2.0"}])
            mock_httpx(handler)
    """
    import httpx

    real_client_cls = httpx.Client

    def install(handler):
        transport = httpx.MockTransport(handler)

        class _MockClient(real_client_cls):
            def __init__(self, *args, **kwargs):
                kwargs["transport"] = transport
                super().__init__(*args, **kwargs)

        def _request(method, url, **kwargs):
            with _MockClient() as c:
                return c.request(method, url, **kwargs)

        monkeypatch.setattr(httpx, "Client", _MockClient)
        monkeypatch.setattr(httpx, "get", lambda url, **kw: _request("GET", url, **kw))
        monkeypatch.setattr(httpx, "post", lambda url, **kw: _request("POST", url, **kw))
        return transport

    return install


@pytest.fixture()
def patch_httpx_get(monkeypatch):
    """Patch module-level ``httpx.get`` only (geocode router, sync_manager).

    Does NOT cover ``httpx.Client(...).get(...)`` (weather/adsb/skydio); use
    the ``mock_httpx`` fixture for those or for full coverage of both paths.

    Usage in a test::

        def test_x(patch_httpx_get):
            patch_httpx_get(lambda *a, **k: FakeResponse(...))
    """
    import httpx

    def install(fake_get):
        monkeypatch.setattr(httpx, "get", fake_get)

    return install
