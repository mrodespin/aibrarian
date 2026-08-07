# /api/app/adapters/outbound/chromadb_cloud_adapter.py
"""
ChromaDB Cloud Adapter - Concrete implementation of VectorDBPort - Bibliotecario-IA

Variant of ChromaDBAdapter for the Render (free tier) deployment.

Why not self-host ChromaDB on Render?
Render's free services don't have persistent disk: any container loses
its filesystem on every redeploy or whenever the service "sleeps" from
inactivity. A self-hosted ChromaDB there would constantly lose all
indexed documents. Chroma Cloud is the same ChromaDB engine but as a
managed service with real persistence.

Why inherit from ChromaDBAdapter instead of rewriting everything?
All the business logic (columnar format, query expansion, similarity
score calculation, etc.) is identical: it's still the `chromadb`
library, only HOW it connects to the server changes. Everything is
inherited and only _get_client() is overridden. If the Render free tier
gets dropped someday, you can just go back to using ChromaDBAdapter
without touching anything in this file.

Note (see ADR-003 and ADR-007): the original decision to self-host
ChromaDB was explicitly so data would NOT leave the machine. Using
Chroma Cloud reintroduces that trade-off, but only for the public demo
instance — the local development mode (docker-compose) still uses
ChromaDBAdapter unchanged.
"""

import chromadb
from chromadb.config import Settings as ChromaSettings

from app.adapters.outbound.chromadb_adapter import ChromaDBAdapter
from app.config.settings import settings
from app.core.observability import get_logger

logger = get_logger(__name__)


class ChromaCloudAdapter(ChromaDBAdapter):
    """
    Same interface and same logic as ChromaDBAdapter; only how the
    client is obtained changes (an authenticated CloudClient instead of
    an anonymous HttpClient to a local container).
    """

    def _get_client(self) -> chromadb.CloudClient:
        if self._client is None:
            missing = [
                name for name, value in (
                    ("CHROMA_CLOUD_API_KEY", settings.chroma_cloud_api_key),
                    ("CHROMA_CLOUD_TENANT", settings.chroma_cloud_tenant),
                    ("CHROMA_CLOUD_DATABASE", settings.chroma_cloud_database),
                ) if not value
            ]
            if missing:
                # Without this validation, chromadb.CloudClient() fails with
                # a generic error ("Could not connect to tenant None") that
                # doesn't make clear which of the three variables is missing
                # (e.g. on Render: Dashboard → service → Environment).
                raise RuntimeError(
                    f"Missing Chroma Cloud variables: {', '.join(missing)}. "
                    "Add them to api/.env (or the service's Environment on Render); "
                    "get them at https://www.trychroma.com after creating your database."
                )
            try:
                self._client = chromadb.CloudClient(
                    tenant=settings.chroma_cloud_tenant,
                    database=settings.chroma_cloud_database,
                    api_key=settings.chroma_cloud_api_key,
                    settings=ChromaSettings(anonymized_telemetry=False),
                )
                logger.info(
                    "Connected to Chroma Cloud",
                    tenant=settings.chroma_cloud_tenant,
                    database=settings.chroma_cloud_database,
                )
            except Exception as e:
                logger.error("Failed to connect to Chroma Cloud", error=str(e))
                raise
        return self._client
