# /api/app/adapters/outbound/chromadb_cloud_adapter.py
"""
Adaptador ChromaDB Cloud - Implementación concreta de VectorDBPort - TFM Bibliotecario-IA

Variante de ChromaDBAdapter para el despliegue en Render (free tier).

¿Por qué no self-hostear ChromaDB en Render?
Los servicios gratuitos de Render no tienen disco persistente: cualquier
contenedor pierde su filesystem en cada redeploy o cuando el servicio
"duerme" por inactividad. Un ChromaDB self-hosted ahí perdería todos los
documentos indexados constantemente. Chroma Cloud es el mismo motor
ChromaDB pero como servicio gestionado con persistencia real.

¿Por qué heredar de ChromaDBAdapter en vez de reescribir todo?
Toda la lógica de negocio (formato columnar, query expansion, cálculo de
similarity_score, etc.) es idéntica: sigue siendo la librería `chromadb`,
solo cambia CÓMO se conecta al servidor. Se hereda todo y se sobreescribe
únicamente _get_client(). Si mañana se abandona el free tier de Render,
basta con seguir usando ChromaDBAdapter sin tocar nada de este archivo.

Nota (ver ADR-003 y ADR-007): la decisión original de ChromaDB self-hosted
fue explícitamente para que los datos NO salieran de la máquina. Usar
Chroma Cloud reintroduce ese trade-off, pero solo para la instancia
pública de demo — el modo de desarrollo local (docker-compose) sigue
usando ChromaDBAdapter sin cambios.
"""

import chromadb
from chromadb.config import Settings as ChromaSettings

from app.adapters.outbound.chromadb_adapter import ChromaDBAdapter
from app.config.settings import settings
from app.core.observability import get_logger

logger = get_logger(__name__)


class ChromaCloudAdapter(ChromaDBAdapter):
    """
    Misma interfaz y misma lógica que ChromaDBAdapter; solo cambia la
    forma de obtener el cliente (CloudClient autenticado en vez de
    HttpClient anónimo a un contenedor local).
    """

    def _get_client(self) -> chromadb.CloudClient:
        if self._client is None:
            if not settings.chroma_cloud_api_key:
                raise RuntimeError(
                    "CHROMA_CLOUD_API_KEY no configurada. Añádela a api/.env "
                    "(consíguela en https://www.trychroma.com tras crear tu base de datos)."
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
