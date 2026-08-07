# /api/app/core/services/auth_service.py
"""
Authentication Service - Bibliotecario-IA

Verifies credentials and issues/validates the session JWTs that protect
the API. It's the only service in the project without a signup UI:
users are created with scripts/create_user.py.

Deliberate difference from RAGService/SyncService:
Those two services do NOT raise exceptions — they catch errors and
return a domain result with the error embedded (QueryResult.answer with
a message, SyncResult.success=False). This service DOES raise
exceptions (InvalidCredentialsError, InvalidTokenError). That's
intentional: login is a binary control-flow decision (401 vs 200), not
a degradable pipeline that can "answer with whatever it has" — main.py
catches these exceptions and translates them into an HTTPException.

TypeScript equivalent:
    class AuthService {
        constructor(private userRepository: UserRepositoryPort) {}
        async authenticate(email: string, password: string): Promise<User> { ... }
        createAccessToken(user: User): string { ... }
        decodeAccessToken(token: string): TokenPayload { ... }
    }
"""

from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from pydantic import BaseModel

from app.core.ports.user_repository_port import UserRepositoryPort
from app.core.domain.models import User
from app.config.settings import settings
import logging

logger = logging.getLogger(__name__)


class InvalidCredentialsError(Exception):
    """Nonexistent email, wrong password, or inactive user."""
    pass


class InvalidTokenError(Exception):
    """The JWT isn't valid: wrong signature, invalid format, or expired."""
    pass


class TokenPayload(BaseModel):
    """
    Data carried inside the JWT, already decoded.

    This is what get_current_user() (in main.py) receives and injects
    into protected endpoints — deliberately NOT the full User, so
    password_hash never crosses into the request-handling layer.
    """
    user_id: int
    email: str


class AuthService:
    """
    Authentication service: verifies credentials and manages JWTs.

    Only needs one port (UserRepositoryPort) to query users. Issuing/
    validating JWTs doesn't depend on any external port: it's pure
    cryptography over settings.jwt_secret_key.
    """

    def __init__(self, user_repository: UserRepositoryPort):
        self.user_repository = user_repository

    async def authenticate(self, email: str, password: str) -> User:
        """
        Verifies email + password.

        Args:
            email: Email entered at login
            password: Plaintext password entered at login

        Returns:
            User: the authenticated user

        Raises:
            InvalidCredentialsError: if the email doesn't exist, the
                password doesn't match, or the user is inactive.
                Deliberately does NOT distinguish the reason in the
                exception/error message sent to the client (avoids
                leaking which emails exist).

        Note: connection/DB errors from user_repository.get_by_email are
        NOT caught here — they propagate as-is (see the AuthService and
        UserRepositoryPort docstrings), so main.py translates them into
        a 500 rather than "invalid credentials".
        """
        user = await self.user_repository.get_by_email(email)
        if user is None or not user.is_active:
            raise InvalidCredentialsError()

        if not bcrypt.checkpw(password.encode("utf-8"), user.password_hash.encode("utf-8")):
            raise InvalidCredentialsError()

        return user

    def create_access_token(self, user: User) -> str:
        """
        Generates a signed JWT (HS256) for a user session.

        Included claims:
        - sub: the user's id (as a string, standard JWT convention)
        - email: the user's email (avoids an extra query on every
          request to show who's logged in)
        - iat/exp: issued-at and expiration (settings.jwt_expiration_minutes)

        Returns:
            str: the encoded JWT, ready to send in the Authorization header
        """
        if not settings.jwt_secret_key:
            raise RuntimeError("JWT_SECRET_KEY not configured. Required to issue sessions.")

        now = datetime.now(timezone.utc)
        payload = {
            "sub": str(user.id),
            "email": user.email,
            "iat": now,
            "exp": now + timedelta(minutes=settings.jwt_expiration_minutes),
        }
        return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)

    def decode_access_token(self, token: str) -> TokenPayload:
        """
        Validates and decodes a JWT (signature + expiration).

        Raises:
            InvalidTokenError: if the signature doesn't match, the token
                has expired, or the format is invalid.
        """
        if not settings.jwt_secret_key:
            raise RuntimeError("JWT_SECRET_KEY not configured. Required to validate sessions.")

        try:
            payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
        except jwt.PyJWTError as e:
            raise InvalidTokenError() from e

        return TokenPayload(user_id=int(payload["sub"]), email=payload["email"])
