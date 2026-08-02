# /api/app/adapters/outbound/postgres_user_adapter.py
"""
Adaptador Postgres - Implementación concreta de UserRepositoryPort - TFM Bibliotecario-IA

Guarda usuarios de autenticación en Postgres (Neon en producción, un
contenedor local en desarrollo vía docker-compose).

¿Por qué Postgres y no reutilizar ChromaDB?
- ChromaDB es una base de datos vectorial: guardar aquí filas de
  usuario/contraseña sería forzar un dato relacional dentro de una
  colección pensada para embeddings.
- El contenedor de la API en Render (free tier) no tiene disco
  persistente, así que necesita un servicio externo hosteado — igual
  que Groq/Chroma Cloud (ver ADR-007). Neon es la versión "Postgres" de
  esa misma idea.

Sin ORM ni framework de migraciones (SQLAlchemy/Alembic): una sola tabla
no lo justifica. Se usa asyncpg directamente (driver async puro), y el
esquema se crea de forma idempotente (`CREATE TABLE IF NOT EXISTS`) en
connect(), igual que ChromaDBAdapter crea/obtiene colecciones al vuelo.

Desviación deliberada respecto a ChromaDBAdapter: los métodos de este
adaptador NO atrapan excepciones de conexión/consulta para devolver un
valor por defecto. Un fallo de Neon durante el login debe propagarse
como error 500, no disfrazarse de "usuario no encontrado" (eso sería un
bug de seguridad, no solo de estilo). Ver también el docstring de
UserRepositoryPort.

Equivalente en TypeScript:
    class PostgresUserAdapter implements UserRepositoryPort {
        private pool: Pool | null = null;
        async connect(): Promise<void> { ... }
        async close(): Promise<void> { ... }
        async getByEmail(email: string): Promise<User | null> { ... }
        async createUser(email: string, passwordHash: string): Promise<User> { ... }
    }
"""

from typing import Optional

import asyncpg

from app.core.ports.user_repository_port import UserRepositoryPort, UserAlreadyExistsError
from app.core.domain.models import User
from app.config.settings import settings
from app.core.observability import get_logger

logger = get_logger(__name__)


CREATE_USERS_TABLE = """
CREATE TABLE IF NOT EXISTS users (
    id            SERIAL PRIMARY KEY,
    email         TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    is_active     BOOLEAN NOT NULL DEFAULT true,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
"""


class PostgresUserAdapter(UserRepositoryPort):
    """
    Implementación concreta de UserRepositoryPort usando Postgres.

    Estado interno:
    - _pool: pool de conexiones asyncpg (lazy, se crea en connect())

    connect()/close() se llaman explícitamente desde el lifespan de
    main.py (startup/shutdown) y desde scripts/create_user.py — a
    diferencia de ChromaDBAdapter, aquí el ciclo de vida de la conexión
    es explícito porque un pool de Postgres conviene cerrarlo
    ordenadamente (ChromaDB habla HTTP sin estado de conexión que cerrar).
    """

    def __init__(self):
        self._pool: Optional[asyncpg.Pool] = None

    async def connect(self) -> None:
        """
        Crea el pool de conexiones y asegura que la tabla `users` existe.

        Idempotente: si ya hay un pool, no hace nada. Se puede llamar
        varias veces sin problema (p.ej. en tests).
        """
        if self._pool is not None:
            return

        if not settings.database_url:
            raise RuntimeError(
                "DATABASE_URL no configurada. Necesaria para autenticación "
                "(ver api/.env o las variables de entorno del servicio)."
            )

        try:
            self._pool = await asyncpg.create_pool(dsn=settings.database_url, min_size=1, max_size=5)
            async with self._pool.acquire() as conn:
                await conn.execute(CREATE_USERS_TABLE)
            logger.info("Connected to Postgres (users)")
        except Exception as e:
            logger.error("Failed to connect to Postgres (users)", error=str(e))
            raise

    async def close(self) -> None:
        """Cierra el pool de conexiones (llamado en el shutdown de la app)."""
        if self._pool is not None:
            await self._pool.close()
            self._pool = None

    def _get_pool(self) -> asyncpg.Pool:
        if self._pool is None:
            raise RuntimeError("PostgresUserAdapter no conectado. Llama a connect() primero.")
        return self._pool

    async def get_by_email(self, email: str) -> Optional[User]:
        """
        Busca un usuario por email.

        No atrapa excepciones de conexión/consulta: se propagan tal
        cual, para que un fallo de la base de datos no se confunda con
        "usuario no encontrado" (ver docstring del módulo).
        """
        pool = self._get_pool()
        row = await pool.fetchrow(
            "SELECT id, email, password_hash, is_active, created_at FROM users WHERE email = $1",
            email,
        )
        if row is None:
            return None
        return User(**dict(row))

    async def create_user(self, email: str, password_hash: str) -> User:
        """
        Inserta un usuario nuevo. Lanza UserAlreadyExistsError si el
        email ya existe (violación de la restricción UNIQUE).
        """
        pool = self._get_pool()
        try:
            row = await pool.fetchrow(
                """
                INSERT INTO users (email, password_hash)
                VALUES ($1, $2)
                RETURNING id, email, password_hash, is_active, created_at
                """,
                email,
                password_hash,
            )
        except asyncpg.UniqueViolationError as e:
            raise UserAlreadyExistsError(email) from e
        return User(**dict(row))
