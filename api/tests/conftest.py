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

import pytest
from unittest.mock import Mock, AsyncMock, MagicMock
from fastapi.testclient import TestClient
from typing import List

from app.core.domain.models import Document, Chunk, QueryResponse
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
def sample_query() -> str:
    """Query de ejemplo para tests."""
    return "¿Qué es RAG?"


@pytest.fixture
def sample_query_response() -> QueryResponse:
    """
    Respuesta de ejemplo del RAG para tests.

    Returns:
        QueryResponse con respuesta simulada
    """
    return QueryResponse(
        answer="RAG (Retrieval-Augmented Generation) es una técnica que combina "
               "búsqueda de información relevante con generación de texto usando LLMs.",
        sources=[
            {"source": "doc1.pdf", "page": 1, "content": "RAG es Retrieval-Augmented..."}
        ],
        model="llama3.2"
    )


# ============================================================================
# FIXTURES DE MOCKS DE SERVICIOS
# ============================================================================

@pytest.fixture
def mock_ollama():
    """
    Mock del adaptador de Ollama para evitar llamadas reales al LLM.

    Simula:
    - generate(): Genera respuestas de texto
    - generate_embedding(): Genera embeddings

    Returns:
        Mock del OllamaAdapter configurado
    """
    mock = Mock()

    # Mock de generate (respuestas del LLM)
    async def mock_generate(prompt: str, **kwargs) -> str:
        return "Esta es una respuesta simulada del LLM para el prompt: " + prompt[:50]

    # Mock de generate_embedding (vectorización)
    async def mock_embedding(text: str) -> List[float]:
        # Retorna un embedding simple basado en el hash del texto
        # En producción, Ollama retorna vectores de 768-4096 dimensiones
        return [float(hash(text) % 100) / 100.0 for _ in range(10)]

    mock.generate = AsyncMock(side_effect=mock_generate)
    mock.generate_embedding = AsyncMock(side_effect=mock_embedding)

    return mock


@pytest.fixture
def mock_chromadb():
    """
    Mock del adaptador de ChromaDB para evitar llamadas reales a la BD vectorial.

    Simula:
    - add_documents(): Añade documentos (no hace nada en tests)
    - query(): Retorna chunks de ejemplo
    - get_stats(): Retorna estadísticas simuladas

    Returns:
        Mock del ChromaDBAdapter configurado
    """
    mock = Mock()

    # Mock de add_documents
    async def mock_add(chunks: List[Chunk]) -> None:
        pass  # No hace nada, solo simula que añadió

    # Mock de query (búsqueda por similaridad)
    async def mock_query_fn(query_embedding: List[float], n_results: int = 4) -> List[Chunk]:
        # Retorna chunks de ejemplo independientemente de la query
        return [
            Chunk(
                content="RAG combina búsqueda con generación de texto.",
                metadata={"source": "test.pdf", "page": 1},
                embedding=query_embedding[:10]  # Simula similaridad
            ),
            Chunk(
                content="Los LLMs son modelos de lenguaje grandes.",
                metadata={"source": "test.pdf", "page": 2},
                embedding=query_embedding[:10]
            )
        ]

    # Mock de get_stats
    async def mock_stats() -> dict:
        return {
            "total_documents": 10,
            "total_chunks": 50,
            "collection_name": "test_collection"
        }

    mock.add_documents = AsyncMock(side_effect=mock_add)
    mock.query = AsyncMock(side_effect=mock_query_fn)
    mock.get_stats = AsyncMock(side_effect=mock_stats)

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

    async def mock_process(file_path: str) -> Document:
        return Document(
            content=f"Contenido extraído del PDF: {file_path}",
            metadata={"source": file_path, "pages": 1}
        )

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
# FIXTURES DE FASTAPI TEST CLIENT
# ============================================================================

@pytest.fixture
def test_client():
    """
    Cliente de test de FastAPI.

    Permite hacer requests HTTP a la API sin necesidad de levantar un servidor.

    Returns:
        TestClient configurado con la app de FastAPI

    Uso:
        def test_endpoint(test_client):
            response = test_client.get("/health")
            assert response.status_code == 200
    """
    return TestClient(app)


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
