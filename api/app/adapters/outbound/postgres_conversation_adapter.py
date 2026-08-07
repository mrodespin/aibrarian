# /api/app/adapters/outbound/postgres_conversation_adapter.py
"""
Postgres Adapter - Concrete implementation of ConversationRepositoryPort - AIbrarian

Stores conversation history (user/assistant turns) in Postgres, the
same service (Neon in production, local container in development)
already used by PostgresUserAdapter for authentication.

Same pattern as postgres_user_adapter.py: no ORM or migrations
(SQLAlchemy/Alembic), its own asyncpg pool (separate from
PostgresUserAdapter's — keeps both adapters decoupled and independently
testable), schema created idempotently (`CREATE TABLE IF NOT EXISTS`)
in connect().

Unlike PostgresUserAdapter, degrading gracefully on failure DOES make
sense here (see ConversationService): history is a UX enhancement, not
a binary security decision like login. That's why this adapter also
doesn't catch exceptions — it lets them propagate as-is — but it's the
CALLER (the /ask endpoint) that decides to log and continue without
history instead of failing the whole request.
"""

from typing import List, Optional

import asyncpg

from app.core.ports.conversation_repository_port import ConversationRepositoryPort
from app.core.domain.models import ConversationMessage
from app.config.settings import settings
from app.core.observability import get_logger

# Reuses the same DSN/SSL heuristic as postgres_user_adapter.py
from app.adapters.outbound.postgres_user_adapter import _prepare_dsn

logger = get_logger(__name__)


CREATE_CONVERSATION_MESSAGES_TABLE = """
CREATE TABLE IF NOT EXISTS conversation_messages (
    id         SERIAL PRIMARY KEY,
    session_id TEXT NOT NULL,
    user_id    INT NOT NULL REFERENCES users(id),
    role       TEXT NOT NULL,
    content    TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
"""

CREATE_CONVERSATION_MESSAGES_INDEX = """
CREATE INDEX IF NOT EXISTS idx_conversation_messages_session
    ON conversation_messages (session_id, created_at);
"""


class PostgresConversationAdapter(ConversationRepositoryPort):
    """
    Concrete implementation of ConversationRepositoryPort using Postgres.

    Internal state:
    - _pool: its own asyncpg connection pool (lazy, created in connect())
    """

    def __init__(self):
        self._pool: Optional[asyncpg.Pool] = None

    async def connect(self) -> None:
        """
        Creates the connection pool and ensures the
        `conversation_messages` table (and its index) exist.

        Idempotent: if there's already a pool, does nothing.

        Note: conversation_messages has an FK to users(id), so the
        `users` table must exist first — in practice this is always the
        case because PostgresUserAdapter.connect() is called first in
        main.py's lifespan.
        """
        if self._pool is not None:
            return

        if not settings.database_url:
            raise RuntimeError(
                "DATABASE_URL not configured. Required for conversation "
                "history (see api/.env or the service's environment variables)."
            )

        try:
            dsn, ssl_mode = _prepare_dsn(settings.database_url)
            self._pool = await asyncpg.create_pool(dsn=dsn, ssl=ssl_mode, min_size=1, max_size=5)
            async with self._pool.acquire() as conn:
                await conn.execute(CREATE_CONVERSATION_MESSAGES_TABLE)
                await conn.execute(CREATE_CONVERSATION_MESSAGES_INDEX)
            logger.info("Connected to Postgres (conversation history)")
        except Exception as e:
            logger.error("Failed to connect to Postgres (conversation history)", error=str(e))
            raise

    async def close(self) -> None:
        """Closes the connection pool (called on the app's shutdown)."""
        if self._pool is not None:
            await self._pool.close()
            self._pool = None

    def _get_pool(self) -> asyncpg.Pool:
        if self._pool is None:
            raise RuntimeError("PostgresConversationAdapter not connected. Call connect() first.")
        return self._pool

    async def append_message(
        self,
        session_id: str,
        user_id: int,
        role: str,
        content: str
    ) -> None:
        pool = self._get_pool()
        await pool.execute(
            """
            INSERT INTO conversation_messages (session_id, user_id, role, content)
            VALUES ($1, $2, $3, $4)
            """,
            session_id,
            user_id,
            role,
            content,
        )

    async def get_recent_messages(
        self,
        session_id: str,
        user_id: int,
        limit: int
    ) -> List[ConversationMessage]:
        pool = self._get_pool()
        # We fetch the `limit` most recent rows in DESC order and reverse
        # them in Python, to return ascending chronological order (what
        # ConversationService expects when formatting the history block).
        rows = await pool.fetch(
            """
            SELECT role, content, created_at
            FROM conversation_messages
            WHERE session_id = $1 AND user_id = $2
            ORDER BY created_at DESC
            LIMIT $3
            """,
            session_id,
            user_id,
            limit,
        )
        messages = [ConversationMessage(**dict(row)) for row in rows]
        return list(reversed(messages))
