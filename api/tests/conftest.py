# /api/tests/conftest.py
"""
Fixtures compartidas para todos los tests.

pytest busca automáticamente fixtures en conftest.py y las hace
disponibles para todos los archivos de test sin necesidad de importarlas.

Fixtures principales:
- mock_ollama: Mock del adaptador de Ollama (evita llamadas reales al LLM)
- mock_chromadb: Mock de ChromaDB (evita llamadas reales a la BD vectorial)
- test_client: Cliente de FastAPI para tests de API
- sample_document: Documento de ejemplo para tests
"""

import os

# JWT_SECRET_KEY debe existir ANTES de "from app.main import app": Settings()
# se instancia al importar app.main (vía app.config.settings), y aunque
# jwt_secret_key es Optional, los tests de auth necesitan un valor real
# para firmar/verificar tokens. Fijamos uno de test aquí, antes de que
# ningún otro import dispare la carga de settings.
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-not-for-prod")

import bcrypt
import pytest
from datetime import datetime
from unittest.mock import Mock, AsyncMock, MagicMock
from fastapi.testclient import TestClient
from typing import List, Optional, Dict

from app.core.domain.models import Document, Chunk, QueryResult, SourceDocument, User, DocumentSummary
from app.main import app


# ============================================================================
# FIXTURES DE DATOS DE PRUEBA
# ============================================================================

@pytest.fixture
def sample_document() -> Document:
    """
    Documento de ejemplo para tests.

    Returns:
        Document con contenido de prueba sobre RAG
    """
    return Document(
        content="RAG es Retrieval-Augmented Generation. Es una técnica que combina "
                "búsqueda de información con generación de texto usando LLMs. "
                "Primero busca contexto relevante y luego genera una respuesta basada en ese contexto.",
        metadata={
            "source": "test_document.txt",
            "chunk_index": 0,
            "total_chunks": 1
        }
    )


@pytest.fixture
def sample_chunks() -> List[Chunk]:
    """
    Lista de chunks de ejemplo para tests de RAG.

    Returns:
        Lista de 3 chunks con contenido relacionado con RAG
    """
    return [
        Chunk(
            content="RAG es Retrieval-Augmented Generation. Es una técnica que combina búsqueda con LLMs.",
            metadata={"source": "doc1.pdf", "page": 1},
            embedding=[0.1, 0.2, 0.3]  # Embedding simplificado
        ),
        Chunk(
            content="Los embeddings son representaciones vectoriales de texto que capturan significado semántico.",
            metadata={"source": "doc2.pdf", "page": 2},
            embedding=[0.2, 0.3, 0.4]
        ),
        Chunk(
            content="ChromaDB es una base de datos vectorial que permite búsqueda por similaridad.",
            metadata={"source": "doc3.pdf", "page": 1},
            embedding=[0.3, 0.4, 0.5]
        )
    ]


@pytest.fixture
def sample_query():
    """Query de ejemplo para tests."""
    from app.core.domain.models import Query
    return Query(question="¿Qué es RAG?")


@pytest.fixture
def sample_query_response() -> QueryResult:
    """
    Respuesta de ejemplo del RAG para tests.

    Returns:
        QueryResult con respuesta simulada
    """
    return QueryResult(
        question="¿Qué es RAG?",
        answer="RAG (Retrieval-Augmented Generation) es una técnica que combina "
               "búsqueda de información relevante con generación de texto usando LLMs.",
        source_documents=[
            SourceDocument(
                document_id="doc1",
                chunk_content="RAG es Retrieval-Augmented...",
                metadata={"source": "doc1.pdf", "page": 1},
                relevance_score=0.95
            )
        ],
        processing_time=1.23
    )


# ============================================================================
# FIXTURES DE MOCKS DE SERVICIOS
# ============================================================================

@pytest.fixture
def mock_ollama():
    """
    Mock del adaptador de Ollama para evitar llamadas reales al LLM.

    Simula:
    - generate_response(): Genera respuestas de texto
    - generate_embedding(): Genera embeddings

    Returns:
        Mock del OllamaAdapter configurado
    """
    mock = Mock()

    # Mock de generate_response (respuestas del LLM)
    async def mock_generate_response(
        prompt: str,
        context: Optional[str] = None,
        history: Optional[str] = None,
        max_tokens: Optional[int] = None,
        temperature: float = 0.7,
        **kwargs
    ) -> str:
        if context:
            return f"Basándome en el contexto proporcionado, {prompt[:50]}"
        return "Esta es una respuesta simulada del LLM para el prompt: " + prompt[:50]

    # Mock de stream_response (misma respuesta que mock_generate_response,
    # pero troceada palabra a palabra para simular streaming real)
    async def mock_stream_response(
        prompt: str,
        context: Optional[str] = None,
        history: Optional[str] = None,
        max_tokens: Optional[int] = None,
        temperature: float = 0.7,
        **kwargs
    ):
        full_response = await mock_generate_response(prompt, context, history, max_tokens, temperature, **kwargs)
        for word in full_response.split(" "):
            yield word + " "

    # Mock de generate_embedding (vectorización)
    async def mock_embedding(text: str) -> List[float]:
        # Retorna un embedding simple basado en el hash del texto
        # En producción, Ollama retorna vectores de 768-4096 dimensiones
        return [float(hash(text) % 100) / 100.0 for _ in range(10)]

    # Mock de generate_embeddings_batch (vectorización en batch)
    async def mock_embeddings_batch(texts: List[str]) -> List[List[float]]:
        # Retorna un embedding por cada texto
        return [await mock_embedding(text) for text in texts]

    # Mock de extract_keywords (Query Expansion)
    async def mock_extract_keywords(question: str) -> List[str]:
        # Extrae palabras simples de la pregunta como keywords
        # En producción, el LLM extrae entidades y nombres propios
        words = question.replace("¿", "").replace("?", "").split()
        # Filtra palabras cortas y de pregunta
        stopwords = {"qué", "es", "cómo", "cuál", "quién", "dónde", "por", "para", "el", "la", "los", "las", "un", "una"}
        keywords = [w for w in words if len(w) > 2 and w.lower() not in stopwords]
        return keywords[:3]  # Máximo 3 keywords

    mock.generate_response = AsyncMock(side_effect=mock_generate_response)
    mock.stream_response = mock_stream_response  # async generator, no AsyncMock wrapper
    mock.generate_embedding = AsyncMock(side_effect=mock_embedding)
    mock.generate_embeddings_batch = AsyncMock(side_effect=mock_embeddings_batch)
    mock.extract_keywords = AsyncMock(side_effect=mock_extract_keywords)
    # Default: ninguna pregunta es "de catálogo" — los tests que quieran
    # ejercitar ese camino sobreescriben esto explícitamente
    # (mock_ollama.is_catalog_question = AsyncMock(return_value=True)),
    # ver RAGService.ask_question / test_rag_service.py.
    mock.is_catalog_question = AsyncMock(return_value=False)

    return mock


@pytest.fixture
def mock_chromadb():
    """
    Mock del adaptador de ChromaDB para evitar llamadas reales a la BD vectorial.

    Simula:
    - store_chunks(): Añade documentos (no hace nada en tests)
    - similarity_search(): Retorna SourceDocuments de ejemplo
    - get_collection_stats(): Retorna estadísticas simuladas

    Returns:
        Mock del ChromaDBAdapter configurado
    """
    mock = Mock()

    # Mock de store_chunks
    async def mock_store(chunks: List[Chunk], collection_name: str = "documents") -> bool:
        return True  # Simula que almacenó correctamente

    # Mock de similarity_search (búsqueda por similaridad con Query Expansion)
    async def mock_similarity_search(
        query_embedding: List[float],
        collection_name: str = "documents",
        top_k: int = 4,
        filter_metadata: Optional[Dict] = None,
        keyword_filter: Optional[str] = None
    ) -> List[SourceDocument]:
        # Retorna SourceDocuments de ejemplo independientemente de la query
        # Si hay keyword_filter, simula que filtra (en tests siempre devuelve resultados)
        return [
            SourceDocument(
                document_id="doc_001",
                chunk_content="RAG combina búsqueda con generación de texto.",
                metadata={"source": "test.pdf", "page": 1},
                relevance_score=0.95
            ),
            SourceDocument(
                document_id="doc_001",
                chunk_content="Los LLMs son modelos de lenguaje grandes.",
                metadata={"source": "test.pdf", "page": 2},
                relevance_score=0.87
            )
        ][:top_k]  # Respetar el límite top_k

    # Mock de get_collection_stats
    async def mock_stats(collection_name: str = "documents") -> dict:
        return {
            "count": 50,
            "dimensions": 768,
            "collection_name": collection_name
        }

    # Mock de list_documents (catálogo completo, no pasa por similarity_search)
    async def mock_list_documents(collection_name: str = "documents") -> List[DocumentSummary]:
        return [
            DocumentSummary(document_id="doc_001", title="1984", source="notion", chunk_count=3),
            DocumentSummary(document_id="doc_002", title="Deep Learning", source="notion", chunk_count=4),
        ]

    mock.store_chunks = AsyncMock(side_effect=mock_store)
    mock.similarity_search = AsyncMock(side_effect=mock_similarity_search)
    mock.get_collection_stats = AsyncMock(side_effect=mock_stats)
    mock.list_documents = AsyncMock(side_effect=mock_list_documents)

    return mock


@pytest.fixture
def mock_pdf_processor():
    """
    Mock del procesador de PDFs.

    Simula la extracción de texto de un PDF sin necesidad de archivos reales.

    Returns:
        Mock del PDFProcessorAdapter configurado
    """
    mock = Mock()

    async def mock_process(
        source: str,
        chunk_size: int = 1000,
        chunk_overlap: int = 200
    ) -> tuple:
        from app.core.domain.models import DocumentSource
        # Crear documento mockeado
        document = Document(
            id="test_doc_001",
            source=DocumentSource.PDF,
            content=f"Contenido extraído del PDF: {source}",
            metadata={"source": source, "pages": 1}
        )
        # Crear chunks mockeados
        chunks = [
            Chunk(
                id="chunk_001",
                document_id="test_doc_001",
                content="Primer chunk del documento",
                metadata={"page": 1, "position": 0}
            ),
            Chunk(
                id="chunk_002",
                document_id="test_doc_001",
                content="Segundo chunk del documento",
                metadata={"page": 1, "position": 1}
            )
        ]
        return (document, chunks)

    mock.process_document = AsyncMock(side_effect=mock_process)

    return mock


# ============================================================================
# FIXTURES DE SERVICIOS CON MOCKS
# ============================================================================

@pytest.fixture
def rag_service_with_mocks(mock_ollama, mock_chromadb):
    """
    RAGService configurado con mocks para tests unitarios.

    Args:
        mock_ollama: Mock del adaptador Ollama
        mock_chromadb: Mock del adaptador ChromaDB

    Returns:
        RAGService configurado con dependencias mockeadas
    """
    from app.core.services.rag_service import RAGService

    return RAGService(
        llm=mock_ollama,
        vector_db=mock_chromadb
    )


@pytest.fixture
def sync_service_with_mocks(mock_ollama, mock_chromadb, mock_pdf_processor):
    """
    SyncService configurado con mocks para tests unitarios.

    Args:
        mock_ollama: Mock del adaptador Ollama
        mock_chromadb: Mock del adaptador ChromaDB
        mock_pdf_processor: Mock del procesador PDF

    Returns:
        SyncService configurado con dependencias mockeadas
    """
    from app.core.services.sync_service import SyncService

    return SyncService(
        document_processor=mock_pdf_processor,
        vector_db=mock_chromadb,
        llm=mock_ollama
    )


# ============================================================================
# FIXTURES DE AUTENTICACIÓN
# ============================================================================

# Hash bcrypt precalculado de "testpass123", usado por mock_user_repository.
# Se calcula una sola vez a nivel de módulo (bcrypt.hashpw es relativamente
# lento) y se reutiliza en todos los tests que necesiten un login válido.
TEST_USER_PASSWORD = "testpass123"
TEST_USER_PASSWORD_HASH = bcrypt.hashpw(TEST_USER_PASSWORD.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


@pytest.fixture
def mock_user_repository():
    """
    Mock de UserRepositoryPort para tests unitarios de AuthService.

    Simula un único usuario existente: test@example.com / testpass123
    (TEST_USER_PASSWORD / TEST_USER_PASSWORD_HASH de arriba).
    """
    mock = Mock()

    async def mock_get_by_email(email: str):
        if email == "test@example.com":
            return User(
                id=1,
                email=email,
                password_hash=TEST_USER_PASSWORD_HASH,
                is_active=True,
            )
        return None

    async def mock_create_user(email: str, password_hash: str):
        return User(id=1, email=email, password_hash=password_hash)

    mock.get_by_email = AsyncMock(side_effect=mock_get_by_email)
    mock.create_user = AsyncMock(side_effect=mock_create_user)

    return mock


@pytest.fixture
def auth_service_with_mocks(mock_user_repository):
    """AuthService configurado con un UserRepositoryPort mockeado."""
    from app.core.services.auth_service import AuthService

    return AuthService(user_repository=mock_user_repository)


# ============================================================================
# FIXTURES DE HISTORIAL DE CONVERSACIÓN
# ============================================================================

@pytest.fixture
def mock_conversation_repository():
    """
    Mock de ConversationRepositoryPort para tests unitarios de ConversationService.

    Simula un almacén en memoria simple: append_message() guarda en un
    dict interno (keyed por session_id), get_recent_messages() lo lee.
    """
    from app.core.domain.models import ConversationMessage

    mock = Mock()
    storage: Dict[str, List[ConversationMessage]] = {}

    async def mock_append_message(session_id: str, user_id: int, role: str, content: str) -> None:
        storage.setdefault(session_id, []).append(
            ConversationMessage(role=role, content=content, created_at=datetime.now())
        )

    async def mock_get_recent_messages(session_id: str, user_id: int, limit: int):
        return storage.get(session_id, [])[-limit:]

    mock.append_message = AsyncMock(side_effect=mock_append_message)
    mock.get_recent_messages = AsyncMock(side_effect=mock_get_recent_messages)
    mock._storage = storage  # expuesto para inspección directa en tests

    return mock


@pytest.fixture
def conversation_service_with_mocks(mock_conversation_repository):
    """ConversationService configurado con un ConversationRepositoryPort mockeado."""
    from app.core.services.conversation_service import ConversationService

    return ConversationService(conversation_repository=mock_conversation_repository)


# ============================================================================
# FIXTURES DE FASTAPI TEST CLIENT
# ============================================================================

@pytest.fixture
def test_client():
    """
    Cliente de test de FastAPI, YA AUTENTICADO.

    Permite hacer requests HTTP a la API sin necesidad de levantar un servidor.
    Todos los tests que usan este fixture (test_api.py, test_notion_service.py,
    etc.) fueron escritos antes de que existiera autenticación y verifican
    lógica de negocio (validación, códigos de error específicos), no el
    login en sí — así que se sobreescribe get_current_user con un usuario
    de prueba para que sigan probando lo que probaban antes.

    Los tests que SÍ quieren probar la autenticación (test_auth_endpoints.py)
    usan su propio fixture `client`, sin este override.

    Returns:
        TestClient configurado con la app de FastAPI

    Uso:
        def test_endpoint(test_client):
            response = test_client.get("/health")
            assert response.status_code == 200
    """
    from app.main import get_current_user
    from app.core.services.auth_service import TokenPayload

    app.dependency_overrides[get_current_user] = lambda: TokenPayload(user_id=1, email="test@example.com")
    yield TestClient(app)
    app.dependency_overrides.clear()


# ============================================================================
# HOOKS DE PYTEST (setup/teardown)
# ============================================================================

@pytest.fixture(autouse=True)
def reset_mocks():
    """
    Fixture que se ejecuta automáticamente antes de cada test.

    Resetea el estado de los mocks para evitar contaminación entre tests.
    autouse=True significa que se aplica automáticamente a todos los tests.
    """
    yield  # El test se ejecuta aquí
    # Después del test, cualquier cleanup si fuera necesario
    pass
