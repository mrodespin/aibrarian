# /api/app/adapters/outbound/postgres_conversation_adapter.py
"""
Adaptador Postgres - Implementación concreta de ConversationRepositoryPort - TFM Bibliotecario-IA

Guarda el historial de conversación (turnos usuario/asistente) en Postgres,
mismo servicio (Neon en producción, contenedor local en desarrollo) que ya
usa PostgresUserAdapter para autenticación.

Mismo patrón que postgres_user_adapter.py: sin ORM ni migraciones
(SQLAlchemy/Alembic), pool asyncpg propio (independiente del de
PostgresUserAdapter — mantiene ambos adaptadores desacoplados y testeables
por separado), esquema creado de forma idempotente (`CREATE TABLE IF NOT
EXISTS`) en connect().

A diferencia de PostgresUserAdapter, aquí SÍ tiene sentido degradar en
caso de fallo (ver ConversationService): el historial es una mejora de
UX, no una decisión de seguridad binaria como el login. Por eso este
adaptador tampoco atrapa excepciones — deja que se propaguen tal cual —
pero es quien LLAMA (el endpoint /ask) el que decide loguear y continuar
sin historial en vez de fallar la petición completa.
"""

from typing import List, Optional

import asyncpg

from app.core.ports.conversation_repository_port import ConversationRepositoryPort
from app.core.domain.models import ConversationMessage
from app.config.settings import settings
from app.core.observability import get_logger

# Reutiliza la misma heurística de DSN/SSL que postgres_user_adapter.py
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
    Implementación concreta de ConversationRepositoryPort usando Postgres.

    Estado interno:
    - _pool: pool de conexiones asyncpg propio (lazy, se crea en connect())
    """

    def __init__(self):
        self._pool: Optional[asyncpg.Pool] = None

    async def connect(self) -> None:
        """
        Crea el pool de conexiones y asegura que la tabla
        `conversation_messages` (y su índice) existen.

        Idempotente: si ya hay un pool, no hace nada.

        Nota: conversation_messages tiene una FK a users(id), así que la
        tabla `users` debe existir antes — en la práctica siempre es así
        porque PostgresUserAdapter.connect() se llama primero en el
        lifespan de main.py.
        """
        if self._pool is not None:
            return

        if not settings.database_url:
            raise RuntimeError(
                "DATABASE_URL no configurada. Necesaria para el historial "
                "de conversación (ver api/.env o las variables de entorno del servicio)."
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
        """Cierra el pool de conexiones (llamado en el shutdown de la app)."""
        if self._pool is not None:
            await self._pool.close()
            self._pool = None

    def _get_pool(self) -> asyncpg.Pool:
        if self._pool is None:
            raise RuntimeError("PostgresConversationAdapter no conectado. Llama a connect() primero.")
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
        # Traemos los `limit` más recientes en orden DESC y los invertimos
        # en Python, para devolver orden cronológico ascendente (el que
        # espera ConversationService al formatear el bloque de historial).
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
