# /api/app/main.py
"""
Entry Point de la API FastAPI - TFM Bibliotecario-IA

Este archivo es el PUNTO DE ENTRADA de toda la aplicación.
Cuando ejecutas `uvicorn app.main:app`, Python carga este módulo.

¿Qué hace este archivo?
1. INYECTA las dependencias: crea adaptadores y los conecta a los servicios
2. DEFINE el ciclo de vida de la app (startup y shutdown)
3. DECLARA los endpoints de la API REST
4. CONFIGURA middleware (CORS para permitir peticiones del frontend)

¿Por qué todo aquí y no en archivos separados?
- Es el patrón estándar de FastAPI para aplicaciones de tamaño medio
- Los endpoints necesitan acceso directo a los servicios inyectados
- Mantiene la wiring (conexión de dependencias) en un solo lugar

Equivalente en TypeScript con Express:
    // app.ts
    const app = express();
    const chromaDb = new ChromaDBAdapter();
    const ollama   = new OllamaAdapter();
    const syncService = new SyncService(pdfProcessor, ollama, chromaDb);
    const ragService  = new RAGService(ollama, chromaDb);

    app.post('/ask', async (req, res) => { ... });
    app.listen(8000);

Relación con otros ficheros:
- Importa los ADAPTADORES directamente (para la inyección de dependencias)
- Importa los SERVICIOS (que internamente hablan con los puertos)
- Importa los MODELOS de dominio (Query, SyncResult) para los schemas de la API
"""

# ============================================================================
# IMPORTS
# ============================================================================
from contextlib import asynccontextmanager  # Para definir el ciclo de vida (startup/shutdown)
from pathlib import Path                    # Manejo de rutas de archivos

from fastapi import FastAPI, HTTPException, UploadFile, File, Form  # Framework web + excepciones HTTP
import tempfile
import shutil
from fastapi.middleware.cors import CORSMiddleware  # Middleware para permitir origen cruzado
from pydantic import BaseModel              # Para los modelos de request/response de la API

# Modelos del dominio que se reutilizan como schemas de la API
from app.config.settings import settings
from app.core.domain.models import Query, QueryResult, SyncResult
# Observabilidad: logging estructurado y métricas Prometheus
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
# Servicios de lógica de negocio
from app.core.services.sync_service import SyncService
from app.core.services.rag_service import RAGService
# Adaptadores concretos (las únicas implementaciones que conoce este fichero)
# Nota: ChromaCloudAdapter y GroqAdapter se importan más abajo, dentro de sus
# respectivos "if settings...", no aquí arriba. Sus paquetes (groq,
# sentence-transformers → torch) son dependencias pesadas que solo hacen
# falta si esos proveedores están activos; importarlas aquí obligaría a
# instalarlas incluso para el flujo local con Ollama (ADR-007).
from app.adapters.outbound.chromadb_adapter import ChromaDBAdapter
from app.adapters.outbound.ollama_adapter import OllamaAdapter
from app.adapters.outbound.pdf_processor_adapter import PDFProcessorAdapter
from app.adapters.outbound.notion_processor_adapter import NotionProcessorAdapter


# ============================================================================
# CONFIGURACIÓN DE LOGGING ESTRUCTURADO
# ============================================================================
# structlog reemplaza el logging básico con logs en formato JSON.
# Esto facilita la búsqueda y análisis en herramientas como ELK, Loki, etc.
#
# En desarrollo (debug=True): formato human-readable con colores
# En producción (debug=False): formato JSON para parsing automático
configure_structlog(json_format=not settings.debug)
logger = get_logger(__name__)


# ============================================================================
# INYECCIÓN DE DEPENDENCIAS
# ============================================================================
# Aquí se conectan los adaptadores con los servicios.
# Es el ÚNICO lugar donde se crea una instancia concreta de cada adaptador.
# El resto del código solo habla con las interfaces (puertos).
#
# Como Python ejecuta los módulos una sola vez, estas variables son
# efectivamente singletons: la misma instancia se reutiliza en toda la app.
#
# Equivalente JS:
#   const chromaDb  = new ChromaDBAdapter();
#   const ollama    = new OllamaAdapter();
#   const syncSvc   = new SyncService(pdfProcessor, ollama, chromaDb);

# --- Adaptadores (implementaciones concretas de los puertos) ---
# La clase concreta de LLMPort/VectorDBPort se elige por configuración
# (settings.llm_provider / settings.vector_db_provider), no por código.
# Default = setup local de siempre (Ollama nativo + ChromaDB en Docker).
# En Render, LLM_PROVIDER=groq y VECTOR_DB_PROVIDER=chroma_cloud vía env vars.
# Ninguno de los dos adaptadores nuevos toca OllamaAdapter/ChromaDBAdapter.
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

# --- Servicios de lógica de negocio ---
# Nota: hay DOS instancias de SyncService, una por cada tipo de fuente.
# Comparten el mismo LLM y VectorDB, pero difieren en el DocumentProcessor:
#   - sync_service        → usa pdf_processor     (para PDFs)
#   - notion_sync_service → usa notion_processor  (para Notion)
# Este patrón es posible gracias a la interfaz DocumentProcessorPort:
# SyncService no sabe si procesa PDFs o Notion, solo habla con el puerto.
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

# RAGService solo necesita LLM + VectorDB (no procesa documentos nuevos)
rag_service = RAGService(
    llm=llm_adapter,
    vector_db=chromadb_adapter
)


# ============================================================================
# CICLO DE VIDA DE LA APLICACIÓN
# ============================================================================
# @asynccontextmanager permite definir código que se ejecuta al
# iniciar y al cerrar la app (startup/shutdown).
#
# ¿Cómo funciona?
#   - Todo antes de "yield" se ejecuta al INICIAR (startup)
#   - Todo después de "yield" se ejecuta al CERRAR (shutdown)
#   - El "yield" es donde la app está activa y atiende peticiones
#
# Equivalente JS con Express:
#   process.on('beforeExit', () => console.log('Shutting down'));
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Gestor del ciclo de vida de la aplicación FastAPI."""
    # --- STARTUP ---
    logger.info(
        "Starting application",
        app_name=settings.app_name,
        version=settings.app_version,
        llm_provider=settings.llm_provider,
        vector_db_provider=settings.vector_db_provider,
    )

    # Verificar que el LLM (Ollama o Groq, según settings.llm_provider) está
    # disponible antes de atender peticiones. Si no lo está, la app inicia
    # de todas formas pero los endpoints que necesitan al LLM fallarán con
    # error descriptivo.
    is_available = await llm_adapter.is_available()
    if not is_available:
        logger.warning("LLM service is not available", provider=settings.llm_provider)
    else:
        logger.info("LLM service is ready", provider=settings.llm_provider, model_info=llm_adapter.get_model_info())

    yield  # ← La app está activa y atiende peticiones desde aquí

    # --- SHUTDOWN ---
    logger.info("Shutting down application")


# ============================================================================
# APLICACIÓN FASTAPI
# ============================================================================
app = FastAPI(
    title=settings.app_name,
    description="API for the AI Librarian RAG project - Local knowledge base with privacy.",
    version=settings.app_version,
    lifespan=lifespan  # Conecta el gestor de ciclo de vida definido arriba
)

# Middleware CORS: permite que el frontend (otro origen) haga peticiones a esta API.
# allow_origins=["*"]: cualquier origen puede hacer peticiones.
# En producción, cambiar por la URL exacta del frontend:
#   allow_origins=["http://localhost:3000"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Middleware de métricas: registra contador y latencia de cada request HTTP
# Las métricas se exponen en /metrics para que Prometheus las recolecte
app.add_middleware(MetricsMiddleware)


# ============================================================================
# MODELOS DE REQUEST/RESPONSE (CAPA API)
# ============================================================================
# Estos modelos son DIFERENTES a los del dominio (models.py).
# Su propósito es definir los schemas de entrada y salida de la API.
#
# ¿Por qué no usar los modelos del dominio directamente?
# - Los modelos del dominio representan conceptos de negocio internos
# - Estos modelos representan la FORMA de las peticiones HTTP
# - Separar ambas capas es parte de la arquitectura hexagonal
#
# FastAPI los usa para:
# - Deserializar el JSON de la petición automáticamente
# - Validar los datos de entrada (Pydantic)
# - Generar documentación Swagger/OpenAPI automáticamente

class SyncFileRequest(BaseModel):
    """
    Request para sincronizar un archivo PDF individual.

    Ejemplo de petición:
        POST /sync
        {"file_path": "./data/manual.pdf", "collection_name": null}
    """
    file_path: str                          # Ruta al archivo PDF
    collection_name: str | None = None      # Colección destino (None = usar default de settings)


class SyncNotionPageRequest(BaseModel):
    """
    Request para sincronizar una página de Notion.

    Ejemplo de petición:
        POST /sync/notion
        {"page_id": "a1b2c3d4e5f6...", "collection_name": null}
    """
    page_id: str                            # ID de página o URL de Notion
    collection_name: str | None = None


class SyncNotionDatabaseRequest(BaseModel):
    """
    Request para sincronizar todas las páginas de una base de datos de Notion.

    Ejemplo de petición:
        POST /sync/notion/database
        {"database_id": "abc123...", "max_pages": 10, "collection_name": null}
    """
    database_id: str | None = None          # ID de la base de datos (None = usar de settings)
    max_pages: int | None = None            # Límite de páginas (None = todas)
    collection_name: str | None = None


class HealthResponse(BaseModel):
    """
    Response del health check básico.

    response_model=HealthResponse en el endpoint le dice a FastAPI
    que valide y filtre la respuesta con este schema antes de devolverla.
    """
    status: str
    version: str
    ollama_available: bool
    chromadb_available: bool


# ============================================================================
# ENDPOINTS DE LA API
# ============================================================================

# ----------------------------------------------------------------------------
# Health Checks
# ----------------------------------------------------------------------------

@app.get("/", response_model=HealthResponse)
async def root():
    """
    Endpoint raíz — Health check básico.

    Verifica en tiempo real si Ollama y ChromaDB están disponibles.
    Útil para monitoreo y para que el frontend sepa si la API está lista.

    @app.get("/"): registra esta función como handler de GET /
    response_model=HealthResponse: FastAPI valida la respuesta con ese schema
    """
    ollama_ok = await llm_adapter.is_available()
    chromadb_ok = await chromadb_adapter.collection_exists(settings.chromadb_collection_name)

    return HealthResponse(
        status="running",
        version=settings.app_version,
        ollama_available=ollama_ok,
        chromadb_available=chromadb_ok
    )


@app.get("/health")
async def health_check():
    """
    Health check detallado.

    Devuelve más información que el endpoint raíz: estado de servicios
    y configuración actual. Útil para debugging y monitoreo.

    Sin response_model: devuelve el dict tal cual, sin validación de schema.
    """
    return {
        "status": "healthy",
        "services": {
            # La clave se mantiene "ollama" por compatibilidad con el frontend
            # (health.services.ollama), aunque con llm_provider="groq" refleja
            # la disponibilidad de Groq, no de un Ollama real.
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


@app.get("/stats")
async def get_stats():
    """
    Estadísticas de la colección vectorial y del modelo.

    Delega a RAGService.get_collection_info() que combina:
    - Estadísticas de ChromaDB (total de chunks almacenados)
    - Información del modelo LLM activo
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
    Endpoint de métricas Prometheus.

    Expone todas las métricas de la aplicación en formato Prometheus.
    Este endpoint es scrapeado periódicamente por Prometheus para
    recolectar métricas y almacenarlas en su base de datos de series temporales.

    Métricas incluidas:
    - http_requests_total: Contador de requests por método/endpoint/status
    - http_request_duration_seconds: Histograma de latencias HTTP
    - rag_queries_total: Contador de consultas RAG (éxito/error)
    - rag_query_duration_seconds: Tiempo de procesamiento de queries
    - documents_synced_total: Documentos sincronizados por fuente
    - llm_requests_total: Requests al LLM por operación

    Uso con Prometheus (prometheus.yml):
        scrape_configs:
          - job_name: 'bibliotecario-ia'
            static_configs:
              - targets: ['localhost:8000']
    """
    return await metrics_endpoint()


# ----------------------------------------------------------------------------
# Sincronización de documentos (Ingesta)
# ----------------------------------------------------------------------------

@app.post("/sync", response_model=SyncResult)
async def sync_document(request: SyncFileRequest):
    """
    Sincroniza un archivo PDF individual a la base de datos vectorial.

    Pipeline que ejecuta internamente (delegado a SyncService):
        1. Carga el PDF y extrae texto
        2. Divide en chunks
        3. Genera embeddings para cada chunk
        4. Almacena en ChromaDB

    Manejo de errores:
    - 404 si el archivo no existe
    - 400 si no es un PDF
    - 500 si falla el procesamiento interno

    ¿Por qué "except HTTPException: raise"?
    Los HTTPException que lanzamos nosotros (404, 400) no deben ser
    capturados por el except genérico de abajo. El "raise" los resuelta
    sin envolverlos en otro 500.

    Equivalente JS con Express:
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

        # Validaciones previas al procesamiento
        if not file_path.exists():
            raise HTTPException(status_code=404, detail=f"File not found: {request.file_path}")

        if not pdf_processor.supports_format(file_path):
            raise HTTPException(status_code=400, detail="Only PDF files are supported")

        # Delegar al servicio de sincronización
        result = await sync_service.sync_document_from_file(
            file_path=file_path,
            collection_name=request.collection_name
        )

        # Si el servicio reporta fallo, lanzar error 500
        if not result.success:
            DOCUMENTS_SYNCED.labels(source='pdf', status='error').inc()
            raise HTTPException(status_code=500, detail=result.message)

        # Registrar métricas de éxito
        DOCUMENTS_SYNCED.labels(source='pdf', status='success').inc()
        CHUNKS_CREATED.inc(result.chunks_created)
        logger.info("PDF sync completed", document_id=result.document_id, chunks=result.chunks_created)

        return result

    except HTTPException:
        raise  # Re-lanza HTTPException sin envolverla en otra
    except Exception as e:
        DOCUMENTS_SYNCED.labels(source='pdf', status='error').inc()
        logger.error("Sync endpoint error", error=str(e), file_path=request.file_path)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/sync/upload", response_model=SyncResult)
async def sync_upload(
    file: UploadFile = File(...),
    collection_name: str = Form(None)
):
    """
    Sube y sincroniza un archivo PDF desde el navegador.

    Este endpoint acepta multipart/form-data con un archivo PDF.
    El archivo se guarda temporalmente, se procesa y luego se elimina.

    Ejemplo con curl:
        curl -X POST "http://localhost:8000/sync/upload" \
             -F "file=@documento.pdf"

    Args:
        file: Archivo PDF subido (multipart/form-data)
        collection_name: Colección destino (opcional)

    Returns:
        SyncResult con el resultado de la sincronización
    """
    # Validar que es un PDF
    if not file.filename.lower().endswith('.pdf'):
        raise HTTPException(
            status_code=400,
            detail="Only PDF files are supported. Please upload a .pdf file."
        )

    # Validar content type
    if file.content_type and file.content_type != 'application/pdf':
        logger.warning(f"Unexpected content type: {file.content_type}")

    temp_file = None
    try:
        # Crear archivo temporal para guardar el PDF
        # suffix mantiene la extensión .pdf para que el procesador lo reconozca
        with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as temp_file:
            # Copiar contenido del upload al archivo temporal
            shutil.copyfileobj(file.file, temp_file)
            temp_path = Path(temp_file.name)

        logger.info("Uploaded file saved to temp", temp_path=str(temp_path), filename=file.filename)

        # Procesar el PDF usando el servicio existente
        result = await sync_service.sync_document_from_file(
            file_path=temp_path,
            collection_name=collection_name
        )

        if not result.success:
            DOCUMENTS_SYNCED.labels(source='pdf', status='error').inc()
            raise HTTPException(status_code=500, detail=result.message)

        # Registrar métricas de éxito
        DOCUMENTS_SYNCED.labels(source='pdf', status='success').inc()
        CHUNKS_CREATED.inc(result.chunks_created)

        # Añadir el nombre original del archivo al mensaje
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
        # Limpiar archivo temporal
        if temp_file and Path(temp_file.name).exists():
            try:
                Path(temp_file.name).unlink()
                logger.debug("Cleaned up temp file", temp_path=temp_file.name)
            except Exception as e:
                logger.warning("Failed to cleanup temp file", error=str(e))


@app.post("/sync/directory")
async def sync_directory(directory_path: str | None = None):
    """
    Sincroniza todos los PDFs de un directorio.

    directory_path es un query parameter opcional.
    Si no se proporciona, usa el directorio configurado en settings.

    ¿Cómo se pasa el parámetro?
        POST /sync/directory                         → usa settings.data_directory
        POST /sync/directory?directory_path=./docs   → usa ./docs

    En FastAPI, los parámetros de función que NO están en el path
    y NO son modelos Pydantic se interpretan como query parameters.
    Equivalente JS: req.query.directory_path

    Retorna un resumen con total, exitosos, fallidos y detalle por archivo.
    """
    try:
        dir_path = directory_path or settings.data_directory

        results = await sync_service.sync_directory(dir_path)

        # Generar resumen de resultados
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
# Sincronización de Notion
# ----------------------------------------------------------------------------

@app.post("/sync/notion", response_model=SyncResult)
async def sync_notion_page(request: SyncNotionPageRequest):
    """
    Sincroniza una página de Notion a la base de datos vectorial.

    Flujo:
        1. Verifica que NOTION_API_KEY esté configurada
        2. Conecta a la API de Notion
        3. Carga el contenido de la página
        4. Divide en chunks, genera embeddings y almacena

    Usa notion_sync_service (otra instancia de SyncService que tiene
    NotionProcessorAdapter en lugar de PDFProcessorAdapter).
    El resto del pipeline es idéntico al de PDFs.
    """
    try:
        logger.info("Syncing Notion page", page_id=request.page_id)

        # Verificar configuración antes de proceder
        if not settings.notion_api_key:
            raise HTTPException(
                status_code=400,
                detail="Notion API key not configured. Set NOTION_API_KEY environment variable."
            )

        # En Notion el "file_path" del servicio es el page_id
        result = await notion_sync_service.sync_document_from_file(
            file_path=request.page_id,
            collection_name=request.collection_name
        )

        if not result.success:
            DOCUMENTS_SYNCED.labels(source='notion', status='error').inc()
            raise HTTPException(status_code=500, detail=result.message)

        # Registrar métricas de éxito
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


@app.post("/sync/notion/database")
async def sync_notion_database(request: SyncNotionDatabaseRequest):
    """
    Sincroniza todas las páginas de una base de datos de Notion.

    Este endpoint es más complejo que sync_notion_page porque:
    1. Primero carga TODAS las páginas de la base de datos
    2. Luego procesa cada una individualmente (chunks → embeddings → store)

    ¿Por qué no delegar todo a notion_sync_service?
    - notion_sync_service.sync_document_from_file() procesa UN documento
    - Una base de datos puede tener decenas de páginas
    - load_database_pages() ya las tiene en memoria, no tiene sentido
      volver a cargarlas una por una desde la API de Notion

    Por eso este endpoint implementa el pipeline split → embeddings → store
    de forma directa, reutilizando los adaptadores ya instanciados.
    """
    try:
        if not settings.notion_api_key:
            raise HTTPException(
                status_code=400,
                detail="Notion API key not configured. Set NOTION_API_KEY environment variable."
            )

        # database_id puede venir del request o de settings
        database_id = request.database_id or settings.notion_database_id

        if not database_id:
            raise HTTPException(
                status_code=400,
                detail="Database ID is required. Provide in request or set NOTION_DATABASE_ID environment variable."
            )

        # Cargar todas las páginas de la base de datos
        documents = await notion_processor.load_database_pages(
            database_id=database_id,
            max_pages=request.max_pages
        )

        # Si no hay páginas, retornar respuesta vacía (no es error)
        if not documents:
            return {
                "total": 0,
                "successful": 0,
                "failed": 0,
                "message": "No pages found in database",
                "results": []
            }

        # Procesar cada documento: split → embeddings → store
        results = []
        for doc in documents:
            # Dividir en chunks
            chunks = await notion_processor.split_into_chunks(doc)

            # Generar embeddings en batch (más eficiente que uno por uno)
            chunk_texts = [chunk.content for chunk in chunks]
            embeddings = await llm_adapter.generate_embeddings_batch(chunk_texts)

            # Asignar embeddings a los chunks
            # zip() empareja chunks[i] con embeddings[i]
            for chunk, embedding in zip(chunks, embeddings):
                chunk.embedding = embedding

            # Almacenar en ChromaDB
            collection = request.collection_name or settings.chromadb_collection_name
            success = await chromadb_adapter.store_chunks(chunks, collection)

            results.append(
                SyncResult(
                    document_id=doc.id,
                    chunks_created=len(chunks),
                    success=success,
                    message=f"Synced '{doc.metadata.get('title', 'Untitled')}'"
                )
            )

        # Resumen final
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
# Consultas RAG
# ----------------------------------------------------------------------------

@app.post("/ask", response_model=QueryResult)
async def ask_question(query: Query):
    """
    Endpoint principal del sistema RAG: hacer preguntas al "bibliotecario".

    Este es el endpoint que el frontend usará para el chat.

    Flujo completo (delegado a RAGService):
        1. Vectorizar la pregunta del usuario
        2. Buscar chunks similares en ChromaDB
        3. Construir contexto con esos chunks
        4. Pedir al LLM que responda basándose en ese contexto
        5. Retornar la respuesta + las fuentes usadas

    ¿Por qué es tan simple este endpoint?
    Toda la lógica vive en RAGService.ask_question().
    El endpoint solo hace la conexión HTTP ↔ servicio.
    Esta es la ventaja de la arquitectura hexagonal: los endpoints
    son delgados y delegan al core.

    Ejemplo de petición:
        POST /ask
        {"question": "¿Qué es Docker?", "max_results": 3}

    Ejemplo de respuesta:
        {
            "question": "¿Qué es Docker?",
            "answer": "Docker es una plataforma de contenedores...",
            "source_documents": [
                {"document_id": "pdf_abc123", "chunk_content": "...", "relevance_score": 0.92}
            ],
            "processing_time": 2.34
        }
    """
    import time
    start_time = time.perf_counter()

    try:
        logger.info("Processing RAG query", question=query.question[:100])
        result = await rag_service.ask_question(query)

        # Registrar métricas de éxito
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
        return result

    except Exception as e:
        # Registrar métricas de error
        RAG_QUERIES_TOTAL.labels(status='error').inc()
        logger.error("Ask endpoint error", error=str(e), question=query.question[:50])
        raise HTTPException(status_code=500, detail=str(e))


# ----------------------------------------------------------------------------
# Endpoints de utilidad
# ----------------------------------------------------------------------------

@app.delete("/documents/{document_id}")
async def delete_document(document_id: str):
    """
    Elimina un documento (y todos sus chunks) de la base de datos vectorial.

    {document_id} en la ruta es un path parameter.
    FastAPI lo extrae automáticamente y lo pasa como argumento de la función.
    Equivalente JS: router.delete('/documents/:documentId', ...)

    ¿Cuándo usar esto?
    - Si actualizas un PDF y quieres re-ingestar la versión nueva
    - Si quieres eliminar documentos obsoletos
    - Para limpiar la base de datos durante desarrollo

    Ejemplo:
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
# PUNTO DE ENTRADA DIRECTO
# ============================================================================
# Este bloque solo se ejecuta si lanzas el script directamente:
#     python main.py
#
# En desarrollo se usa uvicorn desde la línea de comandos:
#     uvicorn app.main:app --reload
#
# ¿Por qué la diferencia?
# - uvicorn --reload: monitorea cambios en archivos y reinicia automáticamente
# - python main.py: lanzamiento manual sin reload (útil para producción simple)
#
# if __name__ == "__main__":
#     Se ejecuta solo cuando este archivo es el módulo principal.
#     Si otro módulo lo importa (como uvicorn), __name__ será "app.main"
#     y este bloque NO se ejecuta.
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
