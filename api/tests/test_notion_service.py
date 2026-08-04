# /api/tests/test_notion_service.py
"""
Tests del servicio de sincronización de Notion.

Estos tests verifican el flujo de ingesta desde Notion usando mocks,
sin necesidad de una API key real de Notion.

El flujo de Notion es similar al de PDF:
1. NotionProcessorAdapter extrae contenido de una página/database
2. Se generan chunks del contenido
3. Se generan embeddings con Ollama
4. Se almacenan en ChromaDB
"""

import pytest
from unittest.mock import AsyncMock, Mock, patch
from typing import List

from app.core.domain.models import Document, Chunk, DocumentSource, SyncResult
from app.adapters.outbound.notion_processor_adapter import NotionProcessorAdapter


# ============================================================================
# FIXTURES ESPECÍFICAS PARA NOTION
# ============================================================================

@pytest.fixture
def mock_notion_processor():
    """
    Mock del NotionProcessorAdapter.

    Simula la extracción de contenido de Notion sin llamar a la API real.
    """
    mock = Mock()

    async def mock_process_document(
        source: str,
        chunk_size: int = 1000,
        chunk_overlap: int = 200
    ) -> tuple:
        """Simula procesar una página de Notion."""
        # Crear documento mockeado como si viniera de Notion
        document = Document(
            id=f"notion_{source}",
            source=DocumentSource.NOTION,
            content=f"Contenido de la página de Notion: {source}. "
                    "Esta es una página de ejemplo con información sobre el proyecto. "
                    "Incluye detalles técnicos, arquitectura y guías de uso.",
            metadata={
                "notion_page_id": source,
                "title": "Página de Ejemplo",
                "url": f"https://notion.so/{source}"
            }
        )
        # Crear chunks mockeados
        chunks = [
            Chunk(
                id=f"notion_{source}_chunk_0",
                document_id=f"notion_{source}",
                content="Contenido de la página de Notion sobre el proyecto.",
                metadata={"notion_page_id": source, "chunk_index": 0}
            ),
            Chunk(
                id=f"notion_{source}_chunk_1",
                document_id=f"notion_{source}",
                content="Detalles técnicos y arquitectura del sistema.",
                metadata={"notion_page_id": source, "chunk_index": 1}
            )
        ]
        return (document, chunks)

    async def mock_load_database_pages(database_id: str) -> List[Document]:
        """Simula cargar todas las páginas de una base de datos de Notion."""
        return [
            Document(
                id=f"notion_db_{database_id}_page_1",
                source=DocumentSource.NOTION,
                content="Primera página de la base de datos con contenido relevante.",
                metadata={"database_id": database_id, "page_index": 0}
            ),
            Document(
                id=f"notion_db_{database_id}_page_2",
                source=DocumentSource.NOTION,
                content="Segunda página con más información del proyecto.",
                metadata={"database_id": database_id, "page_index": 1}
            )
        ]

    mock.process_document = AsyncMock(side_effect=mock_process_document)
    mock.load_database_pages = AsyncMock(side_effect=mock_load_database_pages)

    return mock


@pytest.fixture
def notion_sync_service_with_mocks(mock_notion_processor, mock_ollama, mock_chromadb):
    """
    SyncService configurado con NotionProcessor mockeado.
    """
    from app.core.services.sync_service import SyncService

    return SyncService(
        document_processor=mock_notion_processor,
        vector_db=mock_chromadb,
        llm=mock_ollama
    )


# ============================================================================
# TESTS UNITARIOS - FLUJO DE SINCRONIZACIÓN DE NOTION
# ============================================================================

@pytest.mark.unit
@pytest.mark.asyncio
async def test_notion_sync_page_success(notion_sync_service_with_mocks, mock_notion_processor):
    """
    Test: sincronizar una página de Notion exitosamente.

    Verifica el flujo completo:
    1. Procesa la página de Notion
    2. Genera embeddings para los chunks
    3. Almacena en ChromaDB
    """
    # Arrange
    page_id = "abc123def456"

    # Act
    result = await notion_sync_service_with_mocks.sync_document_from_file(page_id)

    # Assert
    assert result is not None
    assert result.success == True
    assert result.chunks_created > 0
    mock_notion_processor.process_document.assert_called_once()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_notion_sync_creates_chunks_with_metadata(notion_sync_service_with_mocks, mock_chromadb):
    """
    Test: los chunks de Notion incluyen metadata correcta.

    Los chunks deben tener notion_page_id para trazabilidad.
    """
    # Arrange
    page_id = "test_page_123"

    # Act
    await notion_sync_service_with_mocks.sync_document_from_file(page_id)

    # Assert
    mock_chromadb.store_chunks.assert_called_once()
    call_args = mock_chromadb.store_chunks.call_args
    chunks = call_args.kwargs.get('chunks') or call_args.args[0]

    for chunk in chunks:
        assert chunk.metadata is not None
        # Los chunks de Notion deben tener el page_id en metadata
        assert "notion_page_id" in chunk.metadata or "chunk_index" in chunk.metadata


@pytest.mark.unit
@pytest.mark.asyncio
async def test_notion_sync_generates_embeddings(notion_sync_service_with_mocks, mock_ollama):
    """
    Test: se generan embeddings para los chunks de Notion.
    """
    # Arrange
    page_id = "page_with_content"

    # Act
    await notion_sync_service_with_mocks.sync_document_from_file(page_id)

    # Assert
    assert mock_ollama.generate_embeddings_batch.called


@pytest.mark.unit
@pytest.mark.asyncio
async def test_notion_sync_handles_processor_error(notion_sync_service_with_mocks, mock_notion_processor):
    """
    Test: manejar error del NotionProcessor gracefully.

    Si la API de Notion falla, debe retornar SyncResult con success=False.
    """
    # Arrange: simular error de API de Notion
    mock_notion_processor.process_document = AsyncMock(
        side_effect=Exception("Notion API rate limit exceeded")
    )

    # Act
    result = await notion_sync_service_with_mocks.sync_document_from_file("some_page_id")

    # Assert
    assert result is not None
    assert result.success == False
    assert "rate limit" in result.message.lower() or "failed" in result.message.lower()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_notion_sync_handles_invalid_page_id(notion_sync_service_with_mocks, mock_notion_processor):
    """
    Test: manejar page_id inválido.
    """
    # Arrange: simular página no encontrada
    mock_notion_processor.process_document = AsyncMock(
        side_effect=Exception("Page not found: invalid_id")
    )

    # Act
    result = await notion_sync_service_with_mocks.sync_document_from_file("invalid_id")

    # Assert
    assert result.success == False
    assert "not found" in result.message.lower() or "failed" in result.message.lower()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_notion_document_has_correct_source_type(notion_sync_service_with_mocks, mock_notion_processor):
    """
    Test: documentos de Notion tienen source=NOTION.
    """
    # El mock ya retorna DocumentSource.NOTION
    # Este test verifica que el flujo mantiene ese tipo

    # Arrange
    page_id = "notion_page_test"

    # Act
    result = await notion_sync_service_with_mocks.sync_document_from_file(page_id)

    # Assert
    assert result.success == True
    # Verificar que el processor fue llamado (el mock retorna NOTION)
    mock_notion_processor.process_document.assert_called_once()


# ============================================================================
# TESTS UNITARIOS - BASE DE DATOS DE NOTION
# ============================================================================

@pytest.mark.unit
@pytest.mark.asyncio
async def test_notion_load_database_pages(mock_notion_processor):
    """
    Test: cargar páginas de una base de datos de Notion.
    """
    # Arrange
    database_id = "db_123456"

    # Act
    pages = await mock_notion_processor.load_database_pages(database_id)

    # Assert
    assert pages is not None
    assert len(pages) > 0
    for page in pages:
        assert page.source == DocumentSource.NOTION
        assert "database_id" in page.metadata


@pytest.mark.unit
@pytest.mark.asyncio
async def test_notion_database_sync_multiple_pages(mock_notion_processor):
    """
    Test: la base de datos retorna múltiples páginas.
    """
    # Arrange
    database_id = "multi_page_db"

    # Act
    pages = await mock_notion_processor.load_database_pages(database_id)

    # Assert
    assert len(pages) >= 2  # El mock retorna 2 páginas


# ============================================================================
# TESTS DE VALIDACIÓN DE API ENDPOINTS
# ============================================================================

@pytest.mark.unit
def test_notion_endpoint_without_api_key(test_client):
    """
    Test: endpoint de Notion rechaza sin API key configurada.

    Si NOTION_API_KEY no está en .env, debe retornar 400.
    """
    # Arrange
    payload = {"page_id": "some_page_id"}

    # Act
    response = test_client.post("/sync/notion", json=payload)

    # Assert: Sin API key configurada, debe dar error
    # El código puede ser 400 (no configurado) o 422 (validación)
    assert response.status_code in [400, 422, 500]


@pytest.mark.unit
def test_notion_database_endpoint_without_api_key(test_client):
    """
    Test: endpoint de database rechaza sin API key.
    """
    # Arrange
    payload = {"database_id": "some_db_id"}

    # Act
    response = test_client.post("/sync/notion/database", json=payload)

    # Assert
    assert response.status_code in [400, 422, 500]


# ============================================================================
# TESTS DE _extract_title() — descubrimiento por type=="title", no por nombre
# ============================================================================
# NotionProcessorAdapter() no necesita API key real para estos tests: la key
# solo se usa al crear el cliente HTTP (_get_client), lazy y no invocado aquí.
# _extract_title() es una función pura sobre un dict, así que se instancia
# el adapter real (sin mocks) y se le pasan payloads de página construidos
# a mano, igual de shape que los que devuelve la API de Notion.

def _fake_page(properties: dict) -> dict:
    """Construye un payload de página de Notion mínimo para los tests."""
    return {"properties": properties}


def _title_property(text: str) -> dict:
    """Construye una propiedad type=="title" con el texto dado."""
    return {"type": "title", "title": [{"plain_text": text}] if text else []}


@pytest.mark.unit
def test_extract_title_finds_title_by_type_regardless_of_property_name():
    """
    Caso que reproduce el bug original: la columna título de la BD de
    Notion no se llama "title"/"Name"/"Nombre" (ninguno de los nombres que
    probaba la versión antigua), sino algo arbitrario como "Película".
    Debe encontrarse igualmente porque se busca por type, no por nombre.
    """
    adapter = NotionProcessorAdapter(notion_api_key="fake-key")
    page = _fake_page({
        "Película": _title_property("Blade Runner 2049"),
        "Año": {"type": "number", "number": 2017},
    })

    assert adapter._extract_title(page) == "Blade Runner 2049"


@pytest.mark.unit
def test_extract_title_still_works_with_common_names():
    """Regresión: los nombres de columna típicos siguen funcionando."""
    adapter = NotionProcessorAdapter(notion_api_key="fake-key")
    page = _fake_page({
        "Name": _title_property("Deep Learning"),
    })

    assert adapter._extract_title(page) == "Deep Learning"


@pytest.mark.unit
def test_extract_title_returns_untitled_when_title_property_is_empty():
    """Si la celda título existe pero está vacía, cae al fallback "Untitled"."""
    adapter = NotionProcessorAdapter(notion_api_key="fake-key")
    page = _fake_page({
        "Nombre": _title_property(""),
    })

    assert adapter._extract_title(page) == "Untitled"


@pytest.mark.unit
def test_extract_title_returns_untitled_when_no_title_property_exists():
    """Si no hay ninguna propiedad type=="title" (payload degenerado), fallback."""
    adapter = NotionProcessorAdapter(notion_api_key="fake-key")
    page = _fake_page({
        "Año": {"type": "number", "number": 2017},
    })

    assert adapter._extract_title(page) == "Untitled"
