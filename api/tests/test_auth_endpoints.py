# /api/tests/test_auth_endpoints.py
"""
Tests de los endpoints /auth/* y de la protección del resto de la API.

Nota importante para quien añada tests aquí: hay DOS técnicas de mock
distintas en este fichero, porque /auth/login no pasa por Depends().

- Endpoints protegidos por Depends(get_current_user) (/auth/me, /ask, etc.):
  se usa app.dependency_overrides[get_current_user] — el mecanismo
  estándar de FastAPI.
- POST /auth/login llama a auth_service.authenticate(), y auth_service
  es una variable global de módulo en main.py (mismo patrón manual de
  DI que rag_service/sync_service), NO algo inyectado vía Depends().
  dependency_overrides no tiene ningún efecto ahí — hay que hacer
  monkeypatch sobre app.main.user_repository (o sobre app.main.auth_service
  directamente) antes de la petición.
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
    """Evita que overrides de un test se filtren al siguiente."""
    yield
    app.dependency_overrides.clear()


@pytest.fixture(autouse=True)
def _clear_login_rate_limit():
    """Evita que los intentos de login de un test cuenten para el rate limit del siguiente."""
    main_module._login_attempts.clear()
    yield


# ============================================================================
# POST /auth/login — usa monkeypatch sobre los globals de main.py, no
# dependency_overrides (ver docstring del módulo).
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
    """Protección básica contra fuerza bruta: N intentos por IP y ventana."""
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
# GET /auth/me y protección de endpoints — vía dependency_overrides
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
    response = client.post("/ask", json={"question": "hola"})
    assert response.status_code == 401


@pytest.mark.unit
def test_protected_endpoint_with_auth_is_not_blocked_by_auth_layer(client):
    """
    Con una sesión válida, /ask deja de devolver 401 por falta de auth.
    No mockeamos rag_service aquí (fuera de alcance de este test) — solo
    verificamos que la capa de autenticación ya no es la que bloquea.
    """
    app.dependency_overrides[get_current_user] = lambda: TokenPayload(user_id=1, email="test@example.com")

    response = client.post("/ask", json={"question": "hola"})

    assert response.status_code != 401


@pytest.mark.unit
def test_health_check_does_not_require_auth():
    """
    Regresión: render.yaml usa healthCheckPath: / — si este endpoint
    empezara a exigir auth, Render marcaría el servicio unhealthy.
    """
    from fastapi.testclient import TestClient
    client = TestClient(app)

    response = client.get("/")

    assert response.status_code == 200
