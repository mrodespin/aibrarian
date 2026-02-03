# /api/app/core/observability.py
"""
Módulo de Observabilidad - TFM Bibliotecario-IA

Este módulo centraliza toda la configuración de observabilidad:
- Logging estructurado con structlog (JSON format)
- Métricas con prometheus-client
- Middleware para métricas de requests HTTP

¿Por qué observabilidad?
- Logs estructurados facilitan búsqueda y análisis en producción
- Métricas permiten monitorear rendimiento y detectar problemas
- Es requisito en sistemas de producción modernos

Uso:
    from app.core.observability import get_logger, REQUEST_COUNT, REQUEST_LATENCY

    logger = get_logger(__name__)
    logger.info("Processing query", question=query.question, num_chunks=len(chunks))
"""

# ============================================================================
# IMPORTS
# ============================================================================
import time
import structlog
from typing import Callable

from prometheus_client import Counter, Histogram, Gauge, generate_latest, CONTENT_TYPE_LATEST
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response


# ============================================================================
# CONFIGURACIÓN DE STRUCTLOG
# ============================================================================
# structlog es una librería para logging estructurado.
# En lugar de strings como "Processing query: What is RAG?",
# genera JSON: {"event": "Processing query", "question": "What is RAG?"}
#
# Ventajas del logging estructurado:
# - Fácil de parsear y buscar en herramientas como ELK, Loki, CloudWatch
# - Cada campo es searchable (query por question="What is RAG?")
# - Contexto automático (timestamp, nivel, módulo)

def configure_structlog(json_format: bool = True):
    """
    Configura structlog para toda la aplicación.

    Args:
        json_format: Si True, output en JSON. Si False, output human-readable.
                    JSON es mejor para producción, human-readable para desarrollo.

    Esta función debe llamarse UNA sola vez al iniciar la aplicación.
    """
    # Processors son funciones que transforman cada log entry.
    # Se ejecutan en orden, cada uno puede añadir/modificar campos.
    shared_processors = [
        # Añade timestamp ISO 8601
        structlog.stdlib.add_log_level,
        # Añade nombre del logger (módulo)
        structlog.stdlib.add_logger_name,
        # Añade timestamp
        structlog.processors.TimeStamper(fmt="iso"),
        # Formatea excepciones de forma legible
        structlog.processors.format_exc_info,
        # Añade información de la llamada (archivo, línea, función)
        structlog.processors.CallsiteParameterAdder(
            parameters=[
                structlog.processors.CallsiteParameter.FILENAME,
                structlog.processors.CallsiteParameter.FUNC_NAME,
                structlog.processors.CallsiteParameter.LINENO,
            ]
        ),
    ]

    if json_format:
        # En producción: JSON para parsing automático
        renderer = structlog.processors.JSONRenderer()
    else:
        # En desarrollo: formato legible con colores
        renderer = structlog.dev.ConsoleRenderer(colors=True)

    structlog.configure(
        processors=shared_processors + [
            # Prepara el mensaje para el renderer final
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    # Configurar el formatter para stdlib logging (para librerías que usan logging estándar)
    import logging
    handler = logging.StreamHandler()
    handler.setFormatter(structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=shared_processors,
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            renderer,
        ],
    ))

    root_logger = logging.getLogger()
    root_logger.handlers = [handler]
    root_logger.setLevel(logging.INFO)


def get_logger(name: str = None) -> structlog.stdlib.BoundLogger:
    """
    Obtiene un logger estructurado.

    Args:
        name: Nombre del módulo (típicamente __name__)

    Returns:
        Logger configurado con structlog

    Uso:
        logger = get_logger(__name__)
        logger.info("Query processed", question="¿Qué es RAG?", duration_ms=150)
        logger.error("Failed to connect", service="chromadb", error=str(e))
    """
    return structlog.get_logger(name)


# ============================================================================
# MÉTRICAS PROMETHEUS
# ============================================================================
# Prometheus es un sistema de monitoreo que recolecta métricas via HTTP.
# Exponemos métricas en /metrics, Prometheus las "scrapea" periódicamente.
#
# Tipos de métricas:
# - Counter: valor que solo aumenta (requests totales, errores)
# - Histogram: distribución de valores (latencia, tamaño de respuesta)
# - Gauge: valor que puede subir o bajar (conexiones activas, temperatura)

# --- Métricas de Requests HTTP ---
REQUEST_COUNT = Counter(
    'http_requests_total',
    'Total de requests HTTP recibidos',
    ['method', 'endpoint', 'status_code']
)

REQUEST_LATENCY = Histogram(
    'http_request_duration_seconds',
    'Duración de requests HTTP en segundos',
    ['method', 'endpoint'],
    # Buckets personalizados para latencias típicas de una API
    buckets=[0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0]
)

# --- Métricas del Sistema RAG ---
RAG_QUERIES_TOTAL = Counter(
    'rag_queries_total',
    'Total de consultas RAG procesadas',
    ['status']  # 'success' o 'error'
)

RAG_QUERY_DURATION = Histogram(
    'rag_query_duration_seconds',
    'Tiempo de procesamiento de queries RAG',
    buckets=[0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0]
)

RAG_CONTEXT_CHUNKS = Histogram(
    'rag_context_chunks',
    'Número de chunks usados como contexto por query',
    buckets=[1, 2, 3, 4, 5, 10]
)

# --- Métricas de Documentos ---
DOCUMENTS_SYNCED = Counter(
    'documents_synced_total',
    'Total de documentos sincronizados',
    ['source', 'status']  # source: 'pdf', 'notion'. status: 'success', 'error'
)

CHUNKS_CREATED = Counter(
    'chunks_created_total',
    'Total de chunks creados durante sincronización'
)

# --- Métricas del LLM ---
LLM_REQUESTS = Counter(
    'llm_requests_total',
    'Total de requests al LLM (Ollama)',
    ['operation']  # 'generate', 'embed', 'extract_keywords'
)

LLM_LATENCY = Histogram(
    'llm_latency_seconds',
    'Latencia de requests al LLM',
    ['operation'],
    buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0]
)

# --- Métricas de Vector DB ---
VECTOR_SEARCH_LATENCY = Histogram(
    'vector_search_latency_seconds',
    'Latencia de búsquedas en ChromaDB',
    buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0]
)


# ============================================================================
# MIDDLEWARE DE MÉTRICAS HTTP
# ============================================================================
class MetricsMiddleware(BaseHTTPMiddleware):
    """
    Middleware que registra métricas de cada request HTTP.

    Captura:
    - Conteo de requests por método/endpoint/status
    - Latencia de cada request

    ¿Qué es un middleware?
    - Código que se ejecuta ANTES y DESPUÉS de cada request
    - Permite interceptar requests sin modificar los endpoints
    - Como un "envoltorio" alrededor de toda la aplicación

    Equivalente conceptual en Express:
        app.use((req, res, next) => {
            const start = Date.now();
            res.on('finish', () => {
                const duration = Date.now() - start;
                metrics.record(req.method, req.path, res.statusCode, duration);
            });
            next();
        });
    """

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """
        Intercepta cada request para registrar métricas.

        Args:
            request: Request HTTP entrante
            call_next: Función que ejecuta el siguiente handler (el endpoint)

        Returns:
            Response del endpoint
        """
        # Extraer información del request
        method = request.method
        # Normalizar path para evitar cardinalidad alta en métricas
        # ej: /documents/abc123 → /documents/{id}
        path = self._normalize_path(request.url.path)

        # Medir tiempo de procesamiento
        start_time = time.perf_counter()

        # Ejecutar el request (llama al endpoint)
        response = await call_next(request)

        # Calcular duración
        duration = time.perf_counter() - start_time

        # Registrar métricas (excepto para /metrics para evitar recursión)
        if path != "/metrics":
            REQUEST_COUNT.labels(
                method=method,
                endpoint=path,
                status_code=response.status_code
            ).inc()

            REQUEST_LATENCY.labels(
                method=method,
                endpoint=path
            ).observe(duration)

        return response

    def _normalize_path(self, path: str) -> str:
        """
        Normaliza paths para reducir cardinalidad de métricas.

        Problema: /documents/abc123 y /documents/xyz789 son endpoints diferentes
                  pero conceptualmente son el mismo (DELETE document by ID).
                  Si no normalizamos, tendríamos infinitas combinaciones.

        Solución: Reemplazar IDs variables por placeholders.

        Args:
            path: Path original del request

        Returns:
            Path normalizado
        """
        parts = path.split('/')
        normalized = []

        for part in parts:
            # Detectar si parece un ID (alphanumeric largo o UUID)
            if len(part) > 8 and part.replace('-', '').isalnum():
                normalized.append('{id}')
            else:
                normalized.append(part)

        return '/'.join(normalized)


# ============================================================================
# ENDPOINT DE MÉTRICAS
# ============================================================================
async def metrics_endpoint() -> Response:
    """
    Handler para el endpoint /metrics.

    Genera el output en formato Prometheus (texto plano con métricas).
    Prometheus hace scrape de este endpoint periódicamente.

    Returns:
        Response con métricas en formato Prometheus

    Ejemplo de output:
        # HELP http_requests_total Total de requests HTTP recibidos
        # TYPE http_requests_total counter
        http_requests_total{method="GET",endpoint="/health",status_code="200"} 42.0
        http_requests_total{method="POST",endpoint="/ask",status_code="200"} 15.0
    """
    return Response(
        content=generate_latest(),
        media_type=CONTENT_TYPE_LATEST
    )
