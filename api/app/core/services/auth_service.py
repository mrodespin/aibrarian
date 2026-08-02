# /api/app/core/services/auth_service.py
"""
Servicio de Autenticación - TFM Bibliotecario-IA

Verifica credenciales y emite/valida los JWT de sesión que protegen la
API. Es el único servicio del proyecto sin UI de registro: los usuarios
se dan de alta con scripts/create_user.py.

Diferencia deliberada con RAGService/SyncService:
Esos dos servicios NO lanzan excepciones — atrapan errores y devuelven
un resultado de dominio con el error embebido (QueryResult.answer con un
mensaje, SyncResult.success=False). Este servicio SÍ lanza excepciones
(InvalidCredentialsError, InvalidTokenError). Es intencional: login es
una decisión binaria de control de flujo (401 vs 200), no un pipeline
degradable que pueda "responder con lo que haya" — main.py atrapa estas
excepciones y las traduce a HTTPException.

Equivalente en TypeScript:
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
    """Email inexistente, contraseña incorrecta o usuario inactivo."""
    pass


class InvalidTokenError(Exception):
    """El JWT no es válido: firma incorrecta, formato inválido o expirado."""
    pass


class TokenPayload(BaseModel):
    """
    Datos que viajan dentro del JWT, ya decodificados.

    Es lo que get_current_user() (en main.py) recibe e inyecta en los
    endpoints protegidos — deliberadamente NO es el User completo, así
    password_hash nunca cruza a la capa de manejo de requests.
    """
    user_id: int
    email: str


class AuthService:
    """
    Servicio de autenticación: verifica credenciales y gestiona JWT.

    Solo necesita un puerto (UserRepositoryPort) para consultar
    usuarios. La emisión/validación de JWT no depende de ningún puerto
    externo: es criptografía pura sobre settings.jwt_secret_key.
    """

    def __init__(self, user_repository: UserRepositoryPort):
        self.user_repository = user_repository

    async def authenticate(self, email: str, password: str) -> User:
        """
        Verifica email + contraseña.

        Args:
            email: Email introducido en el login
            password: Contraseña en texto plano introducida en el login

        Returns:
            User: el usuario autenticado

        Raises:
            InvalidCredentialsError: si el email no existe, la
                contraseña no coincide o el usuario está inactivo.
                Deliberadamente NO se distingue el motivo en la
                excepción/mensaje de error hacia el cliente (evita dar
                pistas de qué emails existen).

        Nota: los errores de conexión/DB de user_repository.get_by_email
        NO se atrapan aquí — se propagan tal cual (ver AuthService y
        UserRepositoryPort docstrings), para que main.py los traduzca a
        500 y no a "credenciales inválidas".
        """
        user = await self.user_repository.get_by_email(email)
        if user is None or not user.is_active:
            raise InvalidCredentialsError()

        if not bcrypt.checkpw(password.encode("utf-8"), user.password_hash.encode("utf-8")):
            raise InvalidCredentialsError()

        return user

    def create_access_token(self, user: User) -> str:
        """
        Genera un JWT firmado (HS256) para una sesión de usuario.

        Claims incluidos:
        - sub: id del usuario (como string, convención estándar de JWT)
        - email: email del usuario (evita una consulta extra en cada
          request para mostrar quién ha iniciado sesión)
        - iat/exp: emisión y expiración (settings.jwt_expiration_minutes)

        Returns:
            str: el JWT codificado, listo para meter en la cookie
        """
        if not settings.jwt_secret_key:
            raise RuntimeError("JWT_SECRET_KEY no configurada. Necesaria para emitir sesiones.")

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
        Valida y decodifica un JWT (firma + expiración).

        Raises:
            InvalidTokenError: si la firma no coincide, el token ha
                expirado o el formato es inválido.
        """
        if not settings.jwt_secret_key:
            raise RuntimeError("JWT_SECRET_KEY no configurada. Necesaria para validar sesiones.")

        try:
            payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
        except jwt.PyJWTError as e:
            raise InvalidTokenError() from e

        return TokenPayload(user_id=int(payload["sub"]), email=payload["email"])
