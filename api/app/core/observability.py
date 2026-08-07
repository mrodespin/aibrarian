# /api/app/core/observability.py
"""
Observability Module - Bibliotecario-IA

This module centralizes all observability configuration:
- Structured logging with structlog (JSON format)
- Metrics with prometheus-client
- Middleware for HTTP request metrics

Why observability?
- Structured logs make searching and analysis easier in production
- Metrics let you monitor performance and catch problems
- It's a requirement in modern production systems

Usage:
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
# STRUCTLOG CONFIGURATION
# ============================================================================
# structlog is a library for structured logging.
# Instead of strings like "Processing query: What is RAG?", it produces
# JSON: {"event": "Processing query", "question": "What is RAG?"}
#
# Advantages of structured logging:
# - Easy to parse and search in tools like ELK, Loki, CloudWatch
# - Every field is searchable (query by question="What is RAG?")
# - Automatic context (timestamp, level, module)

def configure_structlog(json_format: bool = True):
    """
    Configures structlog for the whole application.

    Args:
        json_format: If True, JSON output. If False, human-readable output.
                    JSON is better for production, human-readable for development.

    This function should be called ONCE when the application starts.
    """
    # Processors are functions that transform each log entry.
    # They run in order, each one can add/modify fields.
    shared_processors = [
        # Adds the ISO 8601 timestamp
        structlog.stdlib.add_log_level,
        # Adds the logger name (module)
        structlog.stdlib.add_logger_name,
        # Adds the timestamp
        structlog.processors.TimeStamper(fmt="iso"),
        # Formats exceptions in a readable way
        structlog.processors.format_exc_info,
        # Adds call-site info (file, line, function)
        structlog.processors.CallsiteParameterAdder(
            parameters=[
                structlog.processors.CallsiteParameter.FILENAME,
                structlog.processors.CallsiteParameter.FUNC_NAME,
                structlog.processors.CallsiteParameter.LINENO,
            ]
        ),
    ]

    if json_format:
        # In production: JSON for automatic parsing
        renderer = structlog.processors.JSONRenderer()
    else:
        # In development: readable format with colors
        renderer = structlog.dev.ConsoleRenderer(colors=True)

    structlog.configure(
        processors=shared_processors + [
            # Prepares the message for the final renderer
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    # Configure the formatter for stdlib logging (for libraries using standard logging)
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
    Gets a structured logger.

    Args:
        name: Module name (typically __name__)

    Returns:
        Logger configured with structlog

    Usage:
        logger = get_logger(__name__)
        logger.info("Query processed", question="What is RAG?", duration_ms=150)
        logger.error("Failed to connect", service="chromadb", error=str(e))
    """
    return structlog.get_logger(name)


# ============================================================================
# PROMETHEUS METRICS
# ============================================================================
# Prometheus is a monitoring system that collects metrics over HTTP.
# We expose metrics at /metrics, and Prometheus "scrapes" them periodically.
#
# Metric types:
# - Counter: a value that only goes up (total requests, errors)
# - Histogram: distribution of values (latency, response size)
# - Gauge: a value that can go up or down (active connections, temperature)

# --- HTTP Request Metrics ---
REQUEST_COUNT = Counter(
    'http_requests_total',
    'Total HTTP requests received',
    ['method', 'endpoint', 'status_code']
)

REQUEST_LATENCY = Histogram(
    'http_request_duration_seconds',
    'HTTP request duration in seconds',
    ['method', 'endpoint'],
    # Custom buckets for an API's typical latencies
    buckets=[0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0]
)

# --- RAG System Metrics ---
RAG_QUERIES_TOTAL = Counter(
    'rag_queries_total',
    'Total RAG queries processed',
    ['status']  # 'success' or 'error'
)

RAG_QUERY_DURATION = Histogram(
    'rag_query_duration_seconds',
    'RAG query processing time',
    buckets=[0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0]
)

RAG_CONTEXT_CHUNKS = Histogram(
    'rag_context_chunks',
    'Number of chunks used as context per query',
    buckets=[1, 2, 3, 4, 5, 10]
)

# --- Document Metrics ---
DOCUMENTS_SYNCED = Counter(
    'documents_synced_total',
    'Total documents synced',
    ['source', 'status']  # source: 'pdf', 'notion'. status: 'success', 'error'
)

CHUNKS_CREATED = Counter(
    'chunks_created_total',
    'Total chunks created during sync'
)

# --- LLM Metrics ---
LLM_REQUESTS = Counter(
    'llm_requests_total',
    'Total requests to the LLM (Ollama)',
    ['operation']  # 'generate', 'embed', 'extract_keywords'
)

LLM_LATENCY = Histogram(
    'llm_latency_seconds',
    'LLM request latency',
    ['operation'],
    buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0]
)

# --- Vector DB Metrics ---
VECTOR_SEARCH_LATENCY = Histogram(
    'vector_search_latency_seconds',
    'ChromaDB search latency',
    buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0]
)


# ============================================================================
# HTTP METRICS MIDDLEWARE
# ============================================================================
class MetricsMiddleware(BaseHTTPMiddleware):
    """
    Middleware that records metrics for every HTTP request.

    Captures:
    - Request count by method/endpoint/status
    - Latency of each request

    What is a middleware?
    - Code that runs BEFORE and AFTER every request
    - Lets you intercept requests without modifying the endpoints
    - Like a "wrapper" around the whole application

    Conceptual Express equivalent:
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
        Intercepts each request to record metrics.

        Args:
            request: Incoming HTTP request
            call_next: Function that runs the next handler (the endpoint)

        Returns:
            The endpoint's response
        """
        # Extract info from the request
        method = request.method
        # Normalize the path to avoid high cardinality in metrics
        # e.g.: /documents/abc123 → /documents/{id}
        path = self._normalize_path(request.url.path)

        # Measure processing time
        start_time = time.perf_counter()

        # Run the request (calls the endpoint)
        response = await call_next(request)

        # Compute the duration
        duration = time.perf_counter() - start_time

        # Record metrics (except for /metrics, to avoid recursion)
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
        Normalizes paths to reduce metric cardinality.

        Problem: /documents/abc123 and /documents/xyz789 are different
                 endpoints but conceptually the same one (DELETE document
                 by ID). Without normalizing, we'd get infinite combinations.

        Solution: replace variable IDs with placeholders.

        Args:
            path: The request's original path

        Returns:
            The normalized path
        """
        parts = path.split('/')
        normalized = []

        for part in parts:
            # Detect whether it looks like an ID (long alphanumeric or UUID)
            if len(part) > 8 and part.replace('-', '').isalnum():
                normalized.append('{id}')
            else:
                normalized.append(part)

        return '/'.join(normalized)


# ============================================================================
# METRICS ENDPOINT
# ============================================================================
async def metrics_endpoint() -> Response:
    """
    Handler for the /metrics endpoint.

    Generates the output in Prometheus format (plain text with metrics).
    Prometheus scrapes this endpoint periodically.

    Returns:
        Response with metrics in Prometheus format

    Example output:
        # HELP http_requests_total Total HTTP requests received
        # TYPE http_requests_total counter
        http_requests_total{method="GET",endpoint="/health",status_code="200"} 42.0
        http_requests_total{method="POST",endpoint="/ask",status_code="200"} 15.0
    """
    return Response(
        content=generate_latest(),
        media_type=CONTENT_TYPE_LATEST
    )
