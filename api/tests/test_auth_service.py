# /api/tests/test_auth_service.py
"""
Tests de AuthService - login, emisión y validación de JWT de sesión.

A diferencia de RAGService/SyncService, AuthService lanza excepciones en
vez de devolver un resultado con el error embebido (ver docstring de
auth_service.py) — estos tests verifican explícitamente ese contrato,
incluida la propagación de errores del repositorio (no deben
convertirse silenciosamente en "credenciales inválidas").
"""

from datetime import datetime, timedelta, timezone

import jwt
import pytest

from app.core.services.auth_service import InvalidCredentialsError, InvalidTokenError
from app.config.settings import settings
from tests.conftest import TEST_USER_PASSWORD


# ============================================================================
# authenticate()
# ============================================================================

@pytest.mark.unit
@pytest.mark.asyncio
async def test_authenticate_success(auth_service_with_mocks):
    """Login con email y contraseña correctos devuelve el User."""
    user = await auth_service_with_mocks.authenticate("test@example.com", TEST_USER_PASSWORD)

    assert user.email == "test@example.com"
    assert user.id == 1


@pytest.mark.unit
@pytest.mark.asyncio
async def test_authenticate_wrong_password(auth_service_with_mocks):
    """Contraseña incorrecta lanza InvalidCredentialsError."""
    with pytest.raises(InvalidCredentialsError):
        await auth_service_with_mocks.authenticate("test@example.com", "wrong-password")


@pytest.mark.unit
@pytest.mark.asyncio
async def test_authenticate_unknown_email(auth_service_with_mocks):
    """Email inexistente lanza InvalidCredentialsError (no un 500 ni None)."""
    with pytest.raises(InvalidCredentialsError):
        await auth_service_with_mocks.authenticate("nadie@example.com", "cualquier-cosa")


@pytest.mark.unit
@pytest.mark.asyncio
async def test_authenticate_propagates_repository_errors(auth_service_with_mocks, mock_user_repository):
    """
    Un fallo de conexión/DB en el repositorio debe propagarse tal cual,
    NO convertirse en InvalidCredentialsError. Confundir ambos casos
    reportaría un fallo de Neon como "credenciales inválidas", que es
    un bug de seguridad (ver docstring de UserRepositoryPort).
    """
    async def broken_get_by_email(email: str):
        raise ConnectionError("Postgres unavailable")

    mock_user_repository.get_by_email.side_effect = broken_get_by_email

    with pytest.raises(ConnectionError):
        await auth_service_with_mocks.authenticate("test@example.com", TEST_USER_PASSWORD)


# ============================================================================
# create_access_token() / decode_access_token()
# ============================================================================

@pytest.mark.unit
@pytest.mark.asyncio
async def test_token_roundtrip(auth_service_with_mocks):
    """Un token emitido para un usuario se decodifica de vuelta al mismo user_id/email."""
    user = await auth_service_with_mocks.authenticate("test@example.com", TEST_USER_PASSWORD)

    token = auth_service_with_mocks.create_access_token(user)
    payload = auth_service_with_mocks.decode_access_token(token)

    assert payload.user_id == user.id
    assert payload.email == user.email


@pytest.mark.unit
def test_decode_expired_token(auth_service_with_mocks):
    """Un token con exp en el pasado lanza InvalidTokenError."""
    now = datetime.now(timezone.utc)
    expired_payload = {
        "sub": "1",
        "email": "test@example.com",
        "iat": now - timedelta(hours=2),
        "exp": now - timedelta(hours=1),
    }
    expired_token = jwt.encode(expired_payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)

    with pytest.raises(InvalidTokenError):
        auth_service_with_mocks.decode_access_token(expired_token)


@pytest.mark.unit
def test_decode_token_wrong_secret(auth_service_with_mocks):
    """Un token firmado con un secreto distinto lanza InvalidTokenError."""
    now = datetime.now(timezone.utc)
    payload = {
        "sub": "1",
        "email": "test@example.com",
        "iat": now,
        "exp": now + timedelta(minutes=30),
    }
    token_wrong_secret = jwt.encode(payload, "otro-secreto-distinto", algorithm=settings.jwt_algorithm)

    with pytest.raises(InvalidTokenError):
        auth_service_with_mocks.decode_access_token(token_wrong_secret)
