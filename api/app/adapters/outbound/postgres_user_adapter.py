# /api/app/adapters/outbound/postgres_user_adapter.py
"""
Postgres Adapter - Concrete implementation of UserRepositoryPort - Bibliotecario-IA

Stores authentication users in Postgres (Neon in production, a local
container in development via docker-compose).

Why Postgres and not reuse ChromaDB?
- ChromaDB is a vector database: storing user/password rows here would
  force relational data into a collection meant for embeddings.
- The API container on Render (free tier) has no persistent disk, so it
  needs an external hosted service — same reasoning as Groq/Chroma
  Cloud (see ADR-007). Neon is the "Postgres" version of that same idea.

No ORM or migration framework (SQLAlchemy/Alembic): a single table
doesn't justify it. asyncpg is used directly (pure async driver), and
the schema is created idempotently (`CREATE TABLE IF NOT EXISTS`) in
connect(), the same way ChromaDBAdapter creates/gets collections on the fly.

Deliberate deviation from ChromaDBAdapter: this adapter's methods do
NOT catch connection/query exceptions to return a default value. A Neon
outage during login must propagate as a 500 error, not disguise itself
as "user not found" (that would be a security bug, not just a style
one). See also UserRepositoryPort's docstring.

TypeScript equivalent:
    class PostgresUserAdapter implements UserRepositoryPort {
        private pool: Pool | null = null;
        async connect(): Promise<void> { ... }
        async close(): Promise<void> { ... }
        async getByEmail(email: string): Promise<User | null> { ... }
        async createUser(email: string, passwordHash: string): Promise<User> { ... }
    }
"""

from typing import Optional
from urllib.parse import urlsplit, urlunsplit

import asyncpg

from app.core.ports.user_repository_port import UserRepositoryPort, UserAlreadyExistsError
from app.core.domain.models import User
from app.config.settings import settings
from app.core.observability import get_logger

logger = get_logger(__name__)


def _prepare_dsn(dsn: str) -> tuple[str, "bool | str"]:
    """
    Splits the Postgres DSN into (dsn_without_query, ssl_mode), ready
    for asyncpg.create_pool().

    Why: depending on which tab/tool the connection string was copied
    from in Neon's dashboard, the SSL query parameter can show up as
    sslmode=require, ssl=true, or come with channel_binding=require,
    etc. asyncpg only recognizes 'sslmode' as a valid query field and
    raises "bad query field" for any other one (seen in production with
    'ssl'). Instead of trying to enumerate every possible variant, the
    whole query string is stripped and SSL is decided explicitly via
    create_pool()'s `ssl` kwarg, which is reliable and doesn't depend on
    the URL's format.

    Heuristic: local host (docker-compose/localhost) → no SSL (the
    local Postgres has no certificates configured). Any other host
    (Neon or another managed Postgres) → SSL required.
    """
    parts = urlsplit(dsn)
    clean_dsn = urlunsplit((parts.scheme, parts.netloc, parts.path, "", parts.fragment))
    is_local = parts.hostname in ("localhost", "127.0.0.1", "postgres")
    return clean_dsn, (False if is_local else "require")


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
    Concrete implementation of UserRepositoryPort using Postgres.

    Internal state:
    - _pool: asyncpg connection pool (lazy, created in connect())

    connect()/close() are called explicitly from main.py's lifespan
    (startup/shutdown) and from scripts/create_user.py — unlike
    ChromaDBAdapter, here the connection lifecycle is explicit because a
    Postgres pool should be closed in an orderly way (ChromaDB speaks
    stateless HTTP, with no connection to close).
    """

    def __init__(self):
        self._pool: Optional[asyncpg.Pool] = None

    async def connect(self) -> None:
        """
        Creates the connection pool and ensures the `users` table exists.

        Idempotent: if there's already a pool, does nothing. Can be
        called multiple times safely (e.g. in tests).
        """
        if self._pool is not None:
            return

        if not settings.database_url:
            raise RuntimeError(
                "DATABASE_URL not configured. Required for authentication "
                "(see api/.env or the service's environment variables)."
            )

        try:
            dsn, ssl_mode = _prepare_dsn(settings.database_url)
            self._pool = await asyncpg.create_pool(dsn=dsn, ssl=ssl_mode, min_size=1, max_size=5)
            async with self._pool.acquire() as conn:
                await conn.execute(CREATE_USERS_TABLE)
            logger.info("Connected to Postgres (users)")
        except Exception as e:
            logger.error("Failed to connect to Postgres (users)", error=str(e))
            raise

    async def close(self) -> None:
        """Closes the connection pool (called on the app's shutdown)."""
        if self._pool is not None:
            await self._pool.close()
            self._pool = None

    def _get_pool(self) -> asyncpg.Pool:
        if self._pool is None:
            raise RuntimeError("PostgresUserAdapter not connected. Call connect() first.")
        return self._pool

    async def get_by_email(self, email: str) -> Optional[User]:
        """
        Looks up a user by email.

        Doesn't catch connection/query exceptions: they propagate
        as-is, so a database outage isn't confused with "user not
        found" (see the module's docstring).
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
        Inserts a new user. Raises UserAlreadyExistsError if the email
        already exists (UNIQUE constraint violation).
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
