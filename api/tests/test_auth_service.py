# /api/tests/test_auth_service.py
"""
AuthService tests - login, session JWT issuance and validation.

Unlike RAGService/SyncService, AuthService raises exceptions instead of
returning a result with the error embedded (see auth_service.py's
docstring) — these tests explicitly verify that contract, including
propagating repository errors (they must not silently turn into
"invalid credentials").
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
    """Logging in with the correct email and password returns the User."""
    user = await auth_service_with_mocks.authenticate("test@example.com", TEST_USER_PASSWORD)

    assert user.email == "test@example.com"
    assert user.id == 1


@pytest.mark.unit
@pytest.mark.asyncio
async def test_authenticate_wrong_password(auth_service_with_mocks):
    """A wrong password raises InvalidCredentialsError."""
    with pytest.raises(InvalidCredentialsError):
        await auth_service_with_mocks.authenticate("test@example.com", "wrong-password")


@pytest.mark.unit
@pytest.mark.asyncio
async def test_authenticate_unknown_email(auth_service_with_mocks):
    """A nonexistent email raises InvalidCredentialsError (not a 500 or None)."""
    with pytest.raises(InvalidCredentialsError):
        await auth_service_with_mocks.authenticate("nobody@example.com", "whatever")


@pytest.mark.unit
@pytest.mark.asyncio
async def test_authenticate_propagates_repository_errors(auth_service_with_mocks, mock_user_repository):
    """
    A connection/DB failure in the repository must propagate as-is,
    NOT turn into InvalidCredentialsError. Conflating the two would
    report a Neon outage as "invalid credentials", which is a security
    bug (see UserRepositoryPort's docstring).
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
    """A token issued for a user decodes back to the same user_id/email."""
    user = await auth_service_with_mocks.authenticate("test@example.com", TEST_USER_PASSWORD)

    token = auth_service_with_mocks.create_access_token(user)
    payload = auth_service_with_mocks.decode_access_token(token)

    assert payload.user_id == user.id
    assert payload.email == user.email


@pytest.mark.unit
def test_decode_expired_token(auth_service_with_mocks):
    """A token whose exp is in the past raises InvalidTokenError."""
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
    """A token signed with a different secret raises InvalidTokenError."""
    now = datetime.now(timezone.utc)
    payload = {
        "sub": "1",
        "email": "test@example.com",
        "iat": now,
        "exp": now + timedelta(minutes=30),
    }
    token_wrong_secret = jwt.encode(payload, "a-different-secret", algorithm=settings.jwt_algorithm)

    with pytest.raises(InvalidTokenError):
        auth_service_with_mocks.decode_access_token(token_wrong_secret)
