# /api/app/main.py
"""
FastAPI Entry Point - AIbrarian

This file is the ENTRY POINT for the whole application. When you run
`uvicorn app.main:app`, Python loads this module.

What does this file do?
1. INJECTS the dependencies: creates adapters and wires them into services
2. DEFINES the app's lifecycle (startup and shutdown)
3. DECLARES the REST API's endpoints
4. CONFIGURES middleware (CORS to allow requests from the frontend)

Why put it all here instead of separate files?
- It's FastAPI's standard pattern for medium-sized applications
- The endpoints need direct access to the injected services
- Keeps the wiring (dependency connections) in a single place

TypeScript equivalent with Express:
    // app.ts
    const app = express();
    const chromaDb = new ChromaDBAdapter();
    const ollama   = new OllamaAdapter();
    const syncService = new SyncService(pdfProcessor, ollama, chromaDb);
    const ragService  = new RAGService(ollama, chromaDb);

    app.post('/ask', async (req, res) => { ... });
    app.listen(8000);

Relationship to other files:
- Imports the ADAPTERS directly (for dependency injection)
- Imports the SERVICES (which internally talk to the ports)
- Imports the domain MODELS (Query, SyncResult) for the API's schemas
"""

# ============================================================================
# IMPORTS
# ============================================================================
import asyncio                              # To launch the LLM's warm-up in the background
import json                                 # To serialize /ask/stream's SSE events
from collections import defaultdict         # Login attempt counter per IP (rate limiting)
from contextlib import asynccontextmanager  # To define the lifecycle (startup/shutdown)
from pathlib import Path                    # File path handling
from time import monotonic                  # Monotonic clock for the rate-limit window

from fastapi import FastAPI, HTTPException, UploadFile, File, Form, Depends, Request  # Web framework + HTTP exceptions
from fastapi.responses import StreamingResponse  # For /ask/stream's SSE streaming
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials  # To read the JWT from the Authorization header
import tempfile
import shutil
from fastapi.middleware.cors import CORSMiddleware  # Middleware to allow cross-origin requests
from pydantic import BaseModel              # For the API's request/response models

# Domain models reused as API schemas
from app.config.settings import settings
from app.core.domain.models import Query, QueryResult, SyncResult
# Observability: structured logging and Prometheus metrics
from app.core.observability import (
    configure_structlog,
    get_logger,
    MetricsMiddleware,
    metrics_endpoint,
    RAG_QUERIES_TOTAL,
    RAG_QUERY_DURATION,
    RAG_CONTEXT_CHUNKS,
    DOCUMENTS_SYNCED,
    CHUNKS_CREATED,
)
# Business logic services
from app.core.services.sync_service import SyncService
from app.core.services.rag_service import RAGService
from app.core.services.auth_service import (
    AuthService,
    InvalidCredentialsError,
    InvalidTokenError,
    TokenPayload,
)
from app.core.services.conversation_service import ConversationService
# Concrete adapters (the only implementations this file knows about)
# Note: ChromaCloudAdapter and GroqAdapter are imported further below,
# inside their respective "if settings..." blocks, not up here. Their
# packages (groq, sentence-transformers → torch) are heavy dependencies
# only needed if those providers are active; importing them here would
# force installing them even for the local Ollama flow (ADR-007).
from app.adapters.outbound.chromadb_adapter import ChromaDBAdapter
from app.adapters.outbound.ollama_adapter import OllamaAdapter
from app.adapters.outbound.pdf_processor_adapter import PDFProcessorAdapter
from app.adapters.outbound.notion_processor_adapter import NotionProcessorAdapter
from app.adapters.outbound.postgres_user_adapter import PostgresUserAdapter
from app.adapters.outbound.postgres_conversation_adapter import PostgresConversationAdapter


# ============================================================================
# STRUCTURED LOGGING SETUP
# ============================================================================
# structlog replaces basic logging with JSON-formatted logs.
# This makes searching and analysis easier in tools like ELK, Loki, etc.
#
# In development (debug=True): human-readable format
# In production (debug=False): JSON format for automatic parsing
configure_structlog(json_format=not settings.debug)
logger = get_logger(__name__)


# ============================================================================
# DEPENDENCY INJECTION
# ============================================================================
# This is where the adapters get wired into the services.
# It's the ONLY place where a concrete instance of each adapter is created.
# Everywhere else in the code only talks to the interfaces (ports).
#
# Since Python only executes modules once, these variables are
# effectively singletons: the same instance is reused across the whole app.
#
# JS equivalent:
#   const chromaDb  = new ChromaDBAdapter();
#   const ollama    = new OllamaAdapter();
#   const syncSvc   = new SyncService(pdfProcessor, ollama, chromaDb);

# --- Adapters (concrete implementations of the ports) ---
# The concrete LLMPort/VectorDBPort class is chosen via configuration
# (settings.llm_provider / settings.vector_db_provider), not in code.
# Default = the usual local setup (native Ollama + ChromaDB in Docker).
# On Render, LLM_PROVIDER=groq and VECTOR_DB_PROVIDER=chroma_cloud via env vars.
# Neither of the two new adapters touches OllamaAdapter/ChromaDBAdapter.
if settings.llm_provider == "groq":
    from app.adapters.outbound.groq_adapter import GroqAdapter
    llm_adapter = GroqAdapter()
else:
    llm_adapter = OllamaAdapter()

if settings.vector_db_provider == "chroma_cloud":
    from app.adapters.outbound.chromadb_cloud_adapter import ChromaCloudAdapter
    chromadb_adapter = ChromaCloudAdapter()
else:
    chromadb_adapter = ChromaDBAdapter()

pdf_processor = PDFProcessorAdapter()
notion_processor = NotionProcessorAdapter()

# --- Business logic services ---
# Note: there are TWO SyncService instances, one per source type.
# They share the same LLM and VectorDB, but differ in the DocumentProcessor:
#   - sync_service        → uses pdf_processor     (for PDFs)
#   - notion_sync_service → uses notion_processor  (for Notion)
# This pattern is possible thanks to the DocumentProcessorPort interface:
# SyncService doesn't know whether it's processing PDFs or Notion, it only talks to the port.
sync_service = SyncService(
    document_processor=pdf_processor,
    llm=llm_adapter,
    vector_db=chromadb_adapter
)

notion_sync_service = SyncService(
    document_processor=notion_processor,
    llm=llm_adapter,
    vector_db=chromadb_adapter
)

# RAGService only needs LLM + VectorDB (doesn't process new documents)
rag_service = RAGService(
    llm=llm_adapter,
    vector_db=chromadb_adapter
)

# --- Authentication (Postgres/Neon + JWT) ---
# Same manual DI pattern as the rest: a global adapter instance, injected
# into the service. connect()/close() are called from the lifespan
# (below), not here — creating the pool is an async operation.
user_repository = PostgresUserAdapter()
auth_service = AuthService(user_repository=user_repository)

# --- Conversation history (Postgres/Neon) ---
# Same pattern as the block above, its own pool (see
# postgres_conversation_adapter.py). Deliberately NOT injected into
# RAGService (which only needs LLM + VectorDB) — the /ask endpoint
# composes both services: it fetches the history before calling
# rag_service, and persists it afterward.
conversation_repository = PostgresConversationAdapter()
conversation_service = ConversationService(conversation_repository=conversation_repository)


# ============================================================================
# APPLICATION LIFECYCLE
# ============================================================================
# @asynccontextmanager lets you define code that runs when the app starts
# and when it shuts down.
#
# How does it work?
#   - Everything before "yield" runs on STARTUP
#   - Everything after "yield" runs on SHUTDOWN
#   - "yield" is where the app is active and serving requests
#
# JS equivalent with Express:
#   process.on('beforeExit', () => console.log('Shutting down'));
@asynccontextmanager
async def lifespan(app: FastAPI):
    """FastAPI application lifecycle manager."""
    # --- STARTUP ---
    logger.info(
        "Starting application",
        app_name=settings.app_name,
        version=settings.app_version,
        llm_provider=settings.llm_provider,
        vector_db_provider=settings.vector_db_provider,
    )

    # Check that the LLM (Ollama or Groq, per settings.llm_provider) is
    # available before serving requests. If it isn't, the app starts
    # anyway but the endpoints that need the LLM will fail with a
    # descriptive error.
    is_available = await llm_adapter.is_available()
    if not is_available:
        logger.warning("LLM service is not available", provider=settings.llm_provider)
    else:
        logger.info("LLM service is ready", provider=settings.llm_provider, model_info=llm_adapter.get_model_info())

    # Background warm-up: for GroqAdapter, preloads the local embedding
    # model into memory (a no-op for other adapters, see
    # LLMPort.warm_up). Launched with create_task (not `await`ed) on
    # purpose: uvicorn doesn't open the port until this generator
    # reaches `yield`, so a blocking warm-up here would reproduce the
    # same startup timeout on Render that is_available() used to cause
    # before this fix. The reference is stored in app.state so the
    # garbage collector doesn't cancel it mid-run.
    app.state.warm_up_task = asyncio.create_task(llm_adapter.warm_up())

    # Connect to Postgres (users/auth). Doesn't crash startup if it
    # fails — same as the LLM check above, the app stays up but
    # /auth/* endpoints will return 500 until this is fixed.
    try:
        await user_repository.connect()
        logger.info("Connected to Postgres (users)")
    except Exception as e:
        logger.warning("Failed to connect to Postgres — auth endpoints will fail until this is fixed", error=str(e))

    # Connect to Postgres (conversation history). Same as above,
    # doesn't crash startup if it fails — /ask simply keeps working
    # without history until this is fixed (see the try/except in the
    # endpoint itself, which degrades the same way request by request).
    try:
        await conversation_repository.connect()
        logger.info("Connected to Postgres (conversation history)")
    except Exception as e:
        logger.warning("Failed to connect to Postgres — conversation history will be unavailable until this is fixed", error=str(e))

    yield  # ← The app is active and serving requests from here on

    # --- SHUTDOWN ---
    logger.info("Shutting down application")
    await user_repository.close()
    await conversation_repository.close()


# ============================================================================
# FASTAPI APPLICATION
# ============================================================================
app = FastAPI(
    title=settings.app_name,
    description="API for the AI Librarian RAG project - Local knowledge base with privacy.",
    version=settings.app_version,
    lifespan=lifespan  # Wires in the lifecycle manager defined above
)

# CORS middleware: lets the frontend (a different origin) make requests to this API.
# allow_origins=[settings.frontend_url]: ONLY the frontend's exact origin.
# allow_credentials=False because the session no longer travels as a
# cookie: the JWT goes in the Authorization header, which the client
# attaches explicitly and which "*" in allow_headers already covers.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_url],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Metrics middleware: records a counter and latency for every HTTP request
# The metrics are exposed at /metrics for Prometheus to scrape
app.add_middleware(MetricsMiddleware)


# ============================================================================
# AUTHENTICATION — AUTHORIZATION HEADER AND FASTAPI DEPENDENCY
# ============================================================================
# The JWT travels in the `Authorization: Bearer <token>` header, attached
# by hand by the frontend (see frontend/src/api/client.js), instead of in
# a cookie. Why: in prod, frontend and API live on different Render
# subdomains (cross-site) and Safari (ITP) aggressively blocks/drops
# cross-site cookies even with SameSite=None; Secure=True — every other
# authenticated request (stats, documents, /ask) failed on Safari while
# working fine on Chrome/Brave. The header doesn't suffer that block
# because it isn't a browser cookie.
#
# auto_error=False: we want to raise our own 401 with a consistent
# message instead of the generic 403 HTTPBearer would give by default.
_bearer_scheme = HTTPBearer(auto_error=False)


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme)
) -> TokenPayload:
    """
    FastAPI dependency that requires a valid session.

    Usage: dependencies=[Depends(get_current_user)] on any endpoint that
    should require login (see the rest of the file).

    Raises:
        HTTPException(401): if the Authorization header is missing or
            the token isn't valid/has expired.
    """
    if not credentials:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        return auth_service.decode_access_token(credentials.credentials)
    except InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid or expired session")


# ============================================================================
# REQUEST/RESPONSE MODELS (API LAYER)
# ============================================================================
# These models are DIFFERENT from the domain ones (models.py).
# Their purpose is to define the API's input/output schemas.
#
# Why not use the domain models directly?
# - The domain models represent internal business concepts
# - These models represent the SHAPE of HTTP requests
# - Separating both layers is part of hexagonal architecture
#
# FastAPI uses them to:
# - Automatically deserialize the request's JSON
# - Validate input data (Pydantic)
# - Automatically generate Swagger/OpenAPI documentation

class SyncFileRequest(BaseModel):
    """
    Request to sync a single PDF file.

    Example request:
        POST /sync
        {"file_path": "./data/manual.pdf", "collection_name": null}
    """
    file_path: str                          # Path to the PDF file
    collection_name: str | None = None      # Target collection (None = use settings' default)


class SyncNotionPageRequest(BaseModel):
    """
    Request to sync a Notion page.

    Example request:
        POST /sync/notion
        {"page_id": "a1b2c3d4e5f6...", "collection_name": null}
    """
    page_id: str                            # Notion page ID or URL
    collection_name: str | None = None


class SyncNotionDatabaseRequest(BaseModel):
    """
    Request to sync every page of a Notion database.

    Example request:
        POST /sync/notion/database
        {"database_id": "abc123...", "max_pages": 10, "collection_name": null}
    """
    database_id: str | None = None          # Database ID (None = use settings')
    max_pages: int | None = None            # Page limit (None = all)
    collection_name: str | None = None


class LoginRequest(BaseModel):
    """
    Request to log in.

    Example request:
        POST /auth/login
        {"email": "ana@example.com", "password": "..."}
    """
    email: str
    password: str


class UserResponse(BaseModel):
    """
    Response with a user's public data.

    Deliberately does NOT include password_hash — unlike the domain
    User (core/domain/models.py), this model is the only thing that
    leaves the API. Same domain/API separation as HealthResponse.
    """
    id: int
    email: str


class LoginResponse(UserResponse):
    """
    /auth/login's response: the user's data + the JWT the frontend must
    store (localStorage) and resend as
    `Authorization: Bearer <access_token>` on every subsequent request.
    """
    access_token: str
    token_type: str = "bearer"


class HealthResponse(BaseModel):
    """
    Basic health check response.

    response_model=HealthResponse on the endpoint tells FastAPI to
    validate and filter the response against this schema before returning it.
    """
    status: str
    version: str
    llm_provider: str
    llm_available: bool
    vector_db_provider: str
    vector_db_available: bool


# ============================================================================
# API ENDPOINTS
# ============================================================================

# ----------------------------------------------------------------------------
# Health Checks
# ----------------------------------------------------------------------------

@app.get("/", response_model=HealthResponse)
async def root():
    """
    Root endpoint — basic health check.

    Checks in real time whether the configured LLM and vector DB
    (Ollama/Groq, ChromaDB local/Chroma Cloud, per settings.llm_provider
    and settings.vector_db_provider) are available. Useful for
    monitoring (e.g. Render's healthCheckPath) and for the frontend to
    know whether the API is ready.

    @app.get("/"): registers this function as the handler for GET /
    response_model=HealthResponse: FastAPI validates the response against that schema
    """
    llm_ok = await llm_adapter.is_available()
    vector_db_ok = await chromadb_adapter.collection_exists(settings.chromadb_collection_name)

    return HealthResponse(
        status="running",
        version=settings.app_version,
        llm_provider=settings.llm_provider,
        llm_available=llm_ok,
        vector_db_provider=settings.vector_db_provider,
        vector_db_available=vector_db_ok,
    )


@app.get("/health")
async def health_check():
    """
    Detailed health check.

    Returns more information than the root endpoint: service status
    and current configuration. Useful for debugging and monitoring.

    No response_model: returns the dict as-is, with no schema validation.
    """
    return {
        "status": "healthy",
        "services": {
            # The key stays "ollama" for frontend compatibility
            # (health.services.ollama), even though with llm_provider="groq"
            # it reflects Groq's availability, not a real Ollama's.
            "ollama": await llm_adapter.is_available(),
            "chromadb": await chromadb_adapter.collection_exists(settings.chromadb_collection_name)
        },
        "config": {
            "llm_provider": settings.llm_provider,
            "vector_db_provider": settings.vector_db_provider,
            **llm_adapter.get_model_info(),
            "collection": settings.chromadb_collection_name,
            "data_directory": settings.data_directory
        }
    }


@app.get("/stats", dependencies=[Depends(get_current_user)])
async def get_stats():
    """
    Statistics for the vector collection and the model.

    Delegates to RAGService.get_collection_info(), which combines:
    - ChromaDB stats (total stored chunks)
    - Info about the active LLM model
    """
    try:
        info = await rag_service.get_collection_info()
        return info
    except Exception as e:
        logger.error("Failed to get stats", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/metrics")
async def get_metrics():
    """
    Prometheus metrics endpoint.

    Exposes all of the application's metrics in Prometheus format. This
    endpoint is scraped periodically by Prometheus to collect metrics
    and store them in its time-series database.

    Metrics included:
    - http_requests_total: Request counter by method/endpoint/status
    - http_request_duration_seconds: Histogram of HTTP latencies
    - rag_queries_total: RAG query counter (success/error)
    - rag_query_duration_seconds: Query processing time
    - documents_synced_total: Documents synced by source
    - llm_requests_total: LLM requests by operation

    Usage with Prometheus (prometheus.yml):
        scrape_configs:
          - job_name: 'aibrarian'
            static_configs:
              - targets: ['localhost:8000']
    """
    return await metrics_endpoint()


# ----------------------------------------------------------------------------
# Authentication
# ----------------------------------------------------------------------------

# In-memory rate limiting for /auth/login — no Redis/slowapi because a
# single users table and a single instance (Render free tier, already
# RAM-constrained, see requirements.txt) don't justify it. If the
# service ever scaled to multiple instances, each would carry its own
# counter (it stops being a strict global limit), but it would still
# throttle brute force from a given IP against any individual instance.
_LOGIN_RATE_LIMIT = 5      # attempts
_LOGIN_RATE_WINDOW = 60.0  # seconds
_login_attempts: dict[str, list[float]] = defaultdict(list)


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _enforce_login_rate_limit(request: Request) -> None:
    ip = _client_ip(request)
    now = monotonic()
    attempts = _login_attempts[ip]
    attempts[:] = [t for t in attempts if now - t < _LOGIN_RATE_WINDOW]
    if len(attempts) >= _LOGIN_RATE_LIMIT:
        raise HTTPException(status_code=429, detail="Too many login attempts. Try again later.")
    attempts.append(now)


@app.post("/auth/login", response_model=LoginResponse)
async def login(request: LoginRequest, http_request: Request):
    """
    Logs in: verifies credentials and, if correct, returns a session
    JWT (valid for settings.jwt_expiration_minutes) in the response body.

    The frontend stores that token (localStorage) and resends it by
    hand as `Authorization: Bearer <token>` on every subsequent request
    — see get_current_user() above for why this design was chosen over
    a session cookie.

    Raises:
        HTTPException(429): more than _LOGIN_RATE_LIMIT attempts from
            the same IP in the last _LOGIN_RATE_WINDOW seconds.
    """
    _enforce_login_rate_limit(http_request)
    try:
        user = await auth_service.authenticate(request.email, request.password)
    except InvalidCredentialsError:
        raise HTTPException(status_code=401, detail="Invalid email or password")
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Login endpoint error", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))

    token = auth_service.create_access_token(user)
    return LoginResponse(id=user.id, email=user.email, access_token=token)


@app.post("/auth/logout")
async def logout():
    """
    Logs out. The JWT is stateless (no server-side blocklist): the
    client simply discards the token stored in localStorage.
    """
    return {"status": "success"}


@app.get("/auth/me", response_model=UserResponse)
async def me(current_user: TokenPayload = Depends(get_current_user)):
    """Returns the current session's user (used by the frontend on load)."""
    return UserResponse(id=current_user.user_id, email=current_user.email)


# ----------------------------------------------------------------------------
# Document Sync (Ingestion)
# ----------------------------------------------------------------------------

@app.post("/sync", response_model=SyncResult, dependencies=[Depends(get_current_user)])
async def sync_document(request: SyncFileRequest):
    """
    Syncs a single PDF file into the vector database.

    Pipeline it runs internally (delegated to SyncService):
        1. Loads the PDF and extracts text
        2. Splits it into chunks
        3. Generates embeddings for each chunk
        4. Stores them in ChromaDB

    Error handling:
    - 404 if the file doesn't exist
    - 400 if it isn't a PDF
    - 500 if internal processing fails

    Why "except HTTPException: raise"?
    The HTTPExceptions we raise ourselves (404, 400) shouldn't be
    caught by the generic except below. The "raise" lets them resolve
    without wrapping them in another 500.

    Express (JS) equivalent:
        app.post('/sync', async (req, res) => {
            if (!fs.existsSync(req.body.file_path))
                return res.status(404).json({ detail: 'File not found' });
            const result = await syncService.syncFile(req.body.file_path);
            res.json(result);
        });
    """
    try:
        file_path = Path(request.file_path)
        logger.info("Syncing PDF document", file_path=str(file_path))

        # Validations before processing
        if not file_path.exists():
            raise HTTPException(status_code=404, detail=f"File not found: {request.file_path}")

        if not pdf_processor.supports_format(file_path):
            raise HTTPException(status_code=400, detail="Only PDF files are supported")

        # Delegate to the sync service
        result = await sync_service.sync_document_from_file(
            file_path=file_path,
            collection_name=request.collection_name
        )

        # If the service reports a failure, raise a 500 error
        if not result.success:
            DOCUMENTS_SYNCED.labels(source='pdf', status='error').inc()
            raise HTTPException(status_code=500, detail=result.message)

        # Record success metrics
        DOCUMENTS_SYNCED.labels(source='pdf', status='success').inc()
        CHUNKS_CREATED.inc(result.chunks_created)
        logger.info("PDF sync completed", document_id=result.document_id, chunks=result.chunks_created)

        return result

    except HTTPException:
        raise  # Re-raise HTTPException without wrapping it in another one
    except Exception as e:
        DOCUMENTS_SYNCED.labels(source='pdf', status='error').inc()
        logger.error("Sync endpoint error", error=str(e), file_path=request.file_path)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/sync/upload", response_model=SyncResult, dependencies=[Depends(get_current_user)])
async def sync_upload(
    file: UploadFile = File(...),
    collection_name: str = Form(None)
):
    """
    Uploads and syncs a PDF file from the browser.

    This endpoint accepts multipart/form-data with a PDF file. The file
    is saved temporarily, processed, and then deleted.

    Example with curl:
        curl -X POST "http://localhost:8000/sync/upload" \
             -F "file=@document.pdf"

    Args:
        file: Uploaded PDF file (multipart/form-data)
        collection_name: Target collection (optional)

    Returns:
        SyncResult with the sync's result
    """
    # Validate it's a PDF
    if not file.filename.lower().endswith('.pdf'):
        raise HTTPException(
            status_code=400,
            detail="Only PDF files are supported. Please upload a .pdf file."
        )

    # Validate the content type
    if file.content_type and file.content_type != 'application/pdf':
        logger.warning(f"Unexpected content type: {file.content_type}")

    temp_file = None
    try:
        # Create a temp file to save the PDF
        # suffix keeps the .pdf extension so the processor recognizes it
        with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as temp_file:
            # Copy the upload's content into the temp file
            shutil.copyfileobj(file.file, temp_file)
            temp_path = Path(temp_file.name)

        logger.info("Uploaded file saved to temp", temp_path=str(temp_path), filename=file.filename)

        # Process the PDF using the existing service
        result = await sync_service.sync_document_from_file(
            file_path=temp_path,
            collection_name=collection_name
        )

        if not result.success:
            DOCUMENTS_SYNCED.labels(source='pdf', status='error').inc()
            raise HTTPException(status_code=500, detail=result.message)

        # Record success metrics
        DOCUMENTS_SYNCED.labels(source='pdf', status='success').inc()
        CHUNKS_CREATED.inc(result.chunks_created)

        # Add the file's original name to the message
        result.message = f"Uploaded and synced: {file.filename}"
        logger.info("Upload sync completed", filename=file.filename, chunks=result.chunks_created)

        return result

    except HTTPException:
        raise
    except Exception as e:
        DOCUMENTS_SYNCED.labels(source='pdf', status='error').inc()
        logger.error("Upload sync error", error=str(e), filename=file.filename)
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        # Clean up the temp file
        if temp_file and Path(temp_file.name).exists():
            try:
                Path(temp_file.name).unlink()
                logger.debug("Cleaned up temp file", temp_path=temp_file.name)
            except Exception as e:
                logger.warning("Failed to cleanup temp file", error=str(e))


@app.post("/sync/directory", dependencies=[Depends(get_current_user)])
async def sync_directory(directory_path: str | None = None):
    """
    Syncs every PDF in a directory.

    directory_path is an optional query parameter.
    If not provided, uses the directory configured in settings.

    How is the parameter passed?
        POST /sync/directory                         → uses settings.data_directory
        POST /sync/directory?directory_path=./docs   → uses ./docs

    In FastAPI, function parameters that are NOT in the path and are
    NOT Pydantic models are interpreted as query parameters.
    JS equivalent: req.query.directory_path

    Returns a summary with total, successful, failed and a per-file breakdown.
    """
    try:
        dir_path = directory_path or settings.data_directory

        results = await sync_service.sync_directory(dir_path)

        # Build the results summary
        successful = sum(1 for r in results if r.success)
        failed = len(results) - successful

        return {
            "total": len(results),
            "successful": successful,
            "failed": failed,
            "results": results
        }

    except Exception as e:
        logger.error("Directory sync error", error=str(e), directory=directory_path)
        raise HTTPException(status_code=500, detail=str(e))


# ----------------------------------------------------------------------------
# Notion Sync
# ----------------------------------------------------------------------------

@app.post("/sync/notion", response_model=SyncResult, dependencies=[Depends(get_current_user)])
async def sync_notion_page(request: SyncNotionPageRequest):
    """
    Syncs a Notion page into the vector database.

    Flow:
        1. Checks that NOTION_API_KEY is configured
        2. Connects to Notion's API
        3. Loads the page's content
        4. Splits into chunks, generates embeddings, and stores them

    Uses notion_sync_service (another SyncService instance wired with
    NotionProcessorAdapter instead of PDFProcessorAdapter). The rest of
    the pipeline is identical to the PDF one.
    """
    try:
        logger.info("Syncing Notion page", page_id=request.page_id)

        # Check the configuration before proceeding
        if not settings.notion_api_key:
            raise HTTPException(
                status_code=400,
                detail="Notion API key not configured. Set NOTION_API_KEY environment variable."
            )

        # In Notion, the service's "file_path" is the page_id
        result = await notion_sync_service.sync_document_from_file(
            file_path=request.page_id,
            collection_name=request.collection_name
        )

        if not result.success:
            DOCUMENTS_SYNCED.labels(source='notion', status='error').inc()
            raise HTTPException(status_code=500, detail=result.message)

        # Record success metrics
        DOCUMENTS_SYNCED.labels(source='notion', status='success').inc()
        CHUNKS_CREATED.inc(result.chunks_created)
        logger.info("Notion page sync completed", page_id=request.page_id, chunks=result.chunks_created)

        return result

    except HTTPException:
        raise
    except Exception as e:
        DOCUMENTS_SYNCED.labels(source='notion', status='error').inc()
        logger.error("Notion sync endpoint error", error=str(e), page_id=request.page_id)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/sync/notion/database", dependencies=[Depends(get_current_user)])
async def sync_notion_database(request: SyncNotionDatabaseRequest):
    """
    Syncs every page of a Notion database.

    This endpoint is more complex than sync_notion_page because:
    1. It first loads ALL the database's pages
    2. Then processes each individually (chunks → embeddings → store)

    Why not delegate everything to notion_sync_service?
    - notion_sync_service.sync_document_from_file() processes ONE document
    - A database can have dozens of pages
    - load_database_pages() already has them in memory, there's no point
      loading them again one by one from Notion's API

    That's why this endpoint implements the split → embeddings → store
    pipeline directly, reusing the already-instantiated adapters.

    Per-page resilience: the loop wraps each document in its own
    try/except (the same protection ingest_database() in
    scripts/ingest_notion.py already had — this endpoint didn't). Without
    this, a single page failing (embeddings, ChromaDB, whatever) would
    abort the ENTIRE request with a 500 and the remaining pages wouldn't
    even be attempted — found in production while debugging why only 2
    of 12 pages of a Notion database were getting indexed. Now a failing
    page gets recorded as a failed result and the loop continues with the rest.
    """
    try:
        if not settings.notion_api_key:
            raise HTTPException(
                status_code=400,
                detail="Notion API key not configured. Set NOTION_API_KEY environment variable."
            )

        # database_id can come from the request or from settings
        database_id = request.database_id or settings.notion_database_id

        if not database_id:
            raise HTTPException(
                status_code=400,
                detail="Database ID is required. Provide in request or set NOTION_DATABASE_ID environment variable."
            )

        # Load every page in the database
        documents = await notion_processor.load_database_pages(
            database_id=database_id,
            max_pages=request.max_pages
        )

        # If there are no pages, return an empty response (not an error)
        if not documents:
            return {
                "total": 0,
                "successful": 0,
                "failed": 0,
                "message": "No pages found in database",
                "results": []
            }

        # Process each document: split → embeddings → store.
        # Each iteration is isolated: if a page fails, it's recorded as a
        # failed result and the loop continues with the next one (see docstring).
        results = []
        for doc in documents:
            title = doc.metadata.get("title", "Untitled")
            try:
                # Split into chunks
                chunks = await notion_processor.split_into_chunks(doc)

                # Generate embeddings in a batch (more efficient than one by one)
                chunk_texts = [chunk.content for chunk in chunks]
                embeddings = await llm_adapter.generate_embeddings_batch(chunk_texts)

                # Assign embeddings to the chunks
                # zip() pairs chunks[i] with embeddings[i]
                for chunk, embedding in zip(chunks, embeddings):
                    chunk.embedding = embedding

                # Store in ChromaDB
                collection = request.collection_name or settings.chromadb_collection_name
                success = await chromadb_adapter.store_chunks(chunks, collection)

                results.append(
                    SyncResult(
                        document_id=doc.id,
                        chunks_created=len(chunks),
                        success=success,
                        message=f"Synced '{title}'" if success else f"Failed to store chunks for '{title}'"
                    )
                )

            except Exception as e:
                # Don't re-raise: a broken page shouldn't take down the
                # rest of the sync. It's recorded as a failure and the loop continues.
                logger.error(
                    "Failed to sync Notion page, continuing with the rest",
                    document_id=doc.id, title=title, error=str(e)
                )
                results.append(
                    SyncResult(
                        document_id=doc.id,
                        chunks_created=0,
                        success=False,
                        message=f"Error syncing '{title}': {e}"
                    )
                )

        # Final summary
        successful = sum(1 for r in results if r.success)
        failed = len(results) - successful

        return {
            "total": len(results),
            "successful": successful,
            "failed": failed,
            "results": results
        }

    except HTTPException:
        raise
    except Exception as e:
        DOCUMENTS_SYNCED.labels(source='notion', status='error').inc()
        logger.error("Notion database sync error", error=str(e), database_id=request.database_id)
        raise HTTPException(status_code=500, detail=str(e))


# ----------------------------------------------------------------------------
# RAG Queries
# ----------------------------------------------------------------------------

@app.post("/ask", response_model=QueryResult)
async def ask_question(query: Query, current_user: TokenPayload = Depends(get_current_user)):
    """
    Main endpoint of the RAG system: asking the "librarian" questions.

    This is the endpoint the frontend uses for the chat.

    Full flow:
        1. (If there's a session_id) Fetch the conversation's recent history
        2. Delegate to RAGService: vectorize, search chunks, build
           context, generate the answer (with the history as extra context)
        3. (If there's a session_id) Persist the new turn (question + answer)
        4. Return the answer + the sources used

    History is a UX enhancement, not a business decision: if Postgres
    isn't available, it's logged and the request continues without
    history instead of failing entirely (see ConversationService).

    Example request:
        POST /ask
        {"question": "What is Docker?", "max_results": 3, "session_id": "abc-123"}

    Example response:
        {
            "question": "What is Docker?",
            "answer": "Docker is a container platform...",
            "source_documents": [
                {"document_id": "pdf_abc123", "chunk_content": "...", "relevance_score": 0.92}
            ],
            "processing_time": 2.34
        }
    """
    import time
    start_time = time.perf_counter()

    history = None
    if query.session_id:
        try:
            history = await conversation_service.get_history_prompt_block(query.session_id, current_user.user_id)
        except Exception as e:
            logger.warning("Failed to load conversation history, continuing without it", error=str(e), session_id=query.session_id)

    try:
        logger.info("Processing RAG query", question=query.question[:100])
        result = await rag_service.ask_question(query, history=history)

        # Record success metrics
        duration = time.perf_counter() - start_time
        RAG_QUERIES_TOTAL.labels(status='success').inc()
        RAG_QUERY_DURATION.observe(duration)
        RAG_CONTEXT_CHUNKS.observe(len(result.source_documents))

        logger.info(
            "RAG query completed",
            question=query.question[:50],
            duration_seconds=round(duration, 3),
            num_sources=len(result.source_documents)
        )

        if query.session_id:
            try:
                await conversation_service.append_turn(query.session_id, current_user.user_id, query.question, result.answer)
            except Exception as e:
                logger.warning("Failed to persist conversation turn", error=str(e), session_id=query.session_id)

        return result

    except Exception as e:
        # Record error metrics
        RAG_QUERIES_TOTAL.labels(status='error').inc()
        logger.error("Ask endpoint error", error=str(e), question=query.question[:50])
        raise HTTPException(status_code=500, detail=str(e))


def _sse_event(event_type: str, data: dict) -> str:
    """
    Formats an event in the Server-Sent Events format the client expects
    (see frontend/src/api/chat.js's askStream()):

        event: <event_type>
        data: <JSON>
        <blank line>

    ensure_ascii=False: keeps accented characters as-is instead of
    \\uXXXX, the body already travels as UTF-8.
    """
    return f"event: {event_type}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


@app.post("/ask/stream")
async def ask_question_stream(query: Query, current_user: TokenPayload = Depends(get_current_user)):
    """
    Streaming version of /ask: the LLM's answer is sent chunk by chunk
    via Server-Sent Events instead of waiting to have it complete.

    A separate endpoint instead of content-negotiation over /ask: /ask
    uses response_model=QueryResult, which FastAPI validates/serializes
    as a single JSON payload — incompatible with StreamingResponse. This
    endpoint receives the same body (Query) but returns text/event-stream.

    IMPORTANT for the client: native EventSource can't be used, because
    it doesn't allow sending the Authorization header (see
    frontend/src/api/chat.js's askStream(), which uses fetch() + manual
    stream reading).

    Events emitted (one per `data:` line, SSE format):
        event: sources → {"source_documents": [...]}  (once, right after retrieval)
        event: token   → {"text": "..."}               (one per generated fragment)
        event: done    → {"processing_time": ..., "session_id": ...}  (once, at the end)
        event: error   → {"detail": "..."}             (only if something fails mid-stream)

    Conversation history is fetched before generation starts and
    persisted at the end, same pattern as /ask (silent — logged-only —
    degradation if Postgres isn't available).
    """
    history = None
    if query.session_id:
        try:
            history = await conversation_service.get_history_prompt_block(query.session_id, current_user.user_id)
        except Exception as e:
            logger.warning("Failed to load conversation history, continuing without it", error=str(e), session_id=query.session_id)

    async def event_generator():
        answer_parts: list[str] = []
        logger.info("Processing RAG query (stream)", question=query.question[:100])
        try:
            async for event in rag_service.ask_question_stream(query, history=history):
                if event["type"] == "sources":
                    source_documents = event["source_documents"]
                    RAG_CONTEXT_CHUNKS.observe(len(source_documents))
                    yield _sse_event("sources", {
                        "source_documents": [doc.model_dump() for doc in source_documents]
                    })
                elif event["type"] == "token":
                    answer_parts.append(event["text"])
                    yield _sse_event("token", {"text": event["text"]})
                elif event["type"] == "done":
                    RAG_QUERIES_TOTAL.labels(status='success').inc()
                    RAG_QUERY_DURATION.observe(event["processing_time"])
                    logger.info(
                        "RAG query completed (stream)",
                        question=query.question[:50],
                        duration_seconds=round(event["processing_time"], 3)
                    )
                    yield _sse_event("done", {
                        "processing_time": event["processing_time"],
                        "session_id": event["session_id"]
                    })
        except Exception as e:
            RAG_QUERIES_TOTAL.labels(status='error').inc()
            logger.error("Ask stream endpoint error", error=str(e), question=query.question[:50])
            yield _sse_event("error", {"detail": str(e)})
            return

        if query.session_id:
            try:
                await conversation_service.append_turn(
                    query.session_id, current_user.user_id, query.question, "".join(answer_parts)
                )
            except Exception as e:
                logger.warning("Failed to persist conversation turn", error=str(e), session_id=query.session_id)

    return StreamingResponse(event_generator(), media_type="text/event-stream")


# ----------------------------------------------------------------------------
# Utility Endpoints
# ----------------------------------------------------------------------------

@app.get("/documents", dependencies=[Depends(get_current_user)])
async def list_documents():
    """
    Lists every document indexed in the knowledge base.

    Unlike POST /ask, this does NOT go through the LLM or similarity
    search — it returns the full catalog, grouping chunks by document_id
    (see RAGService.list_known_documents / VectorDBPort.list_documents).

    Meant so the frontend can show "what's indexed" without relying on
    the chat being able to answer aggregate questions like "how many
    documents do you have?" well (semantic RAG alone can't guarantee
    covering the whole catalog, see LLMPort.is_catalog_question for the
    equivalent case inside the chat).

    Example response:
        {
            "total": 12,
            "documents": [
                {"document_id": "notion_abc123", "title": "1984", "source": "notion", "chunk_count": 3},
                ...
            ]
        }
    """
    try:
        documents = await rag_service.list_known_documents()
        return {"total": len(documents), "documents": documents}
    except Exception as e:
        logger.error("Failed to list documents", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/documents/{document_id}", dependencies=[Depends(get_current_user)])
async def delete_document(document_id: str):
    """
    Deletes a document (and all its chunks) from the vector database.

    {document_id} in the route is a path parameter.
    FastAPI extracts it automatically and passes it as a function argument.
    JS equivalent: router.delete('/documents/:documentId', ...)

    When would you use this?
    - If you update a PDF and want to re-ingest the new version
    - If you want to remove stale documents
    - To clean up the database during development

    Example:
        DELETE /documents/pdf_a3f2b1c9
        → {"status": "success", "message": "Document pdf_a3f2b1c9 deleted"}
    """
    try:
        success = await sync_service.delete_document(document_id)

        if not success:
            raise HTTPException(status_code=404, detail="Document not found or deletion failed")

        return {"status": "success", "message": f"Document {document_id} deleted"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Delete endpoint error", error=str(e), document_id=document_id)
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# DIRECT ENTRY POINT
# ============================================================================
# This block only runs if you launch the script directly:
#     python main.py
#
# In development, uvicorn is used from the command line instead:
#     uvicorn app.main:app --reload
#
# Why the difference?
# - uvicorn --reload: watches for file changes and restarts automatically
# - python main.py: manual launch with no reload (useful for simple production)
#
# if __name__ == "__main__":
#     Only runs when this file is the main module.
#     If another module imports it (like uvicorn), __name__ will be "app.main"
#     and this block does NOT run.
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
