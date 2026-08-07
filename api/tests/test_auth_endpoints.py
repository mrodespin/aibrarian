# /api/tests/test_auth_endpoints.py
"""
Tests for the /auth/* endpoints and for the rest of the API's protection.

Important note for anyone adding tests here: there are TWO different
mocking techniques in this file, because /auth/login doesn't go through Depends().

- Endpoints protected by Depends(get_current_user) (/auth/me, /ask, etc.):
  uses app.dependency_overrides[get_current_user] — FastAPI's standard mechanism.
- POST /auth/login calls auth_service.authenticate(), and auth_service
  is a global module-level variable in main.py (same manual DI pattern
  as rag_service/sync_service), NOT something injected via Depends().
  dependency_overrides has no effect there — you have to monkeypatch
  app.main.user_repository (or app.main.auth_service directly) before
  making the request.
"""

import pytest

import app.main as main_module
from app.main import app, get_current_user
from app.core.services.auth_service import AuthService, TokenPayload
from tests.conftest import TEST_USER_PASSWORD


@pytest.fixture
def client():
    from fastapi.testclient import TestClient
    return TestClient(app)


@pytest.fixture(autouse=True)
def _clear_dependency_overrides():
    """Prevents one test's overrides from leaking into the next."""
    yield
    app.dependency_overrides.clear()


@pytest.fixture(autouse=True)
def _clear_login_rate_limit():
    """Prevents one test's login attempts from counting toward the next test's rate limit."""
    main_module._login_attempts.clear()
    yield


# ============================================================================
# POST /auth/login — uses monkeypatch on main.py's globals, not
# dependency_overrides (see the module's docstring).
# ============================================================================

@pytest.mark.unit
def test_login_success_returns_access_token(client, monkeypatch, mock_user_repository):
    monkeypatch.setattr("app.main.auth_service", AuthService(user_repository=mock_user_repository))

    response = client.post(
        "/auth/login",
        json={"email": "test@example.com", "password": TEST_USER_PASSWORD},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == 1
    assert body["email"] == "test@example.com"
    assert body["token_type"] == "bearer"
    assert body["access_token"]


@pytest.mark.unit
def test_login_wrong_password(client, monkeypatch, mock_user_repository):
    monkeypatch.setattr("app.main.auth_service", AuthService(user_repository=mock_user_repository))

    response = client.post(
        "/auth/login",
        json={"email": "test@example.com", "password": "wrong-password"},
    )

    assert response.status_code == 401


@pytest.mark.unit
def test_login_rate_limited_after_too_many_attempts(client, monkeypatch, mock_user_repository):
    """Basic brute-force protection: N attempts per IP and window."""
    monkeypatch.setattr("app.main.auth_service", AuthService(user_repository=mock_user_repository))

    for _ in range(main_module._LOGIN_RATE_LIMIT):
        response = client.post(
            "/auth/login",
            json={"email": "test@example.com", "password": "wrong-password"},
        )
        assert response.status_code == 401

    response = client.post(
        "/auth/login",
        json={"email": "test@example.com", "password": "wrong-password"},
    )
    assert response.status_code == 429


@pytest.mark.unit
def test_logout_returns_success(client):
    response = client.post("/auth/logout")

    assert response.status_code == 200
    assert response.json() == {"status": "success"}


# ============================================================================
# GET /auth/me and endpoint protection — via dependency_overrides
# ============================================================================

@pytest.mark.unit
def test_me_without_auth_header_returns_401(client):
    response = client.get("/auth/me")
    assert response.status_code == 401


@pytest.mark.unit
def test_me_with_valid_session_returns_user(client):
    app.dependency_overrides[get_current_user] = lambda: TokenPayload(user_id=1, email="test@example.com")

    response = client.get("/auth/me")

    assert response.status_code == 200
    assert response.json() == {"id": 1, "email": "test@example.com"}


@pytest.mark.unit
def test_protected_endpoint_without_auth_returns_401(client):
    response = client.post("/ask", json={"question": "hello"})
    assert response.status_code == 401


@pytest.mark.unit
def test_list_documents_without_auth_returns_401(client):
    response = client.get("/documents")
    assert response.status_code == 401


@pytest.mark.unit
def test_protected_endpoint_with_auth_is_not_blocked_by_auth_layer(client):
    """
    With a valid session, /ask stops returning 401 for lack of auth. We
    don't mock rag_service here (out of scope for this test) — we're
    only verifying the auth layer is no longer what's blocking it.
    """
    app.dependency_overrides[get_current_user] = lambda: TokenPayload(user_id=1, email="test@example.com")

    response = client.post("/ask", json={"question": "hello"})

    assert response.status_code != 401


@pytest.mark.unit
def test_health_check_does_not_require_auth():
    """
    Regression test: render.yaml uses healthCheckPath: / — if this
    endpoint started requiring auth, Render would mark the service unhealthy.
    """
    from fastapi.testclient import TestClient
    client = TestClient(app)

    response = client.get("/")

    assert response.status_code == 200
