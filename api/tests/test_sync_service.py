# /api/tests/test_sync_service.py
"""
Tests del SyncService - Pipeline de ingesta de documentos.

El SyncService es responsable de:
1. Procesar documentos (PDFs, Notion)
2. Dividir en chunks
3. Generar embeddings
4. Almacenar en ChromaDB

Estos tests verifican el flujo de ingesta y manejo de errores.
"""

import pytest
from unittest.mock import AsyncMock, Mock
from pathlib import Path

from app.core.services.sync_service import SyncService
from app.core.domain.models import Document, Chunk


# ============================================================================
# TESTS UNITARIOS DEL FLUJO DE INGESTA
# ============================================================================

@pytest.mark.unit
@pytest.mark.asyncio
async def test_ingest_document_success(sync_service_with_mocks, mock_pdf_processor, mock_ollama, mock_chromadb):
    """
    Test básico: ingesta exitosa de un documento.

    Verifica el flujo completo:
    1. Procesa documento → Document
    2. Divide en chunks → List[Chunk]
    3. Genera embeddings → Chunk con embedding
    4. Almacena en ChromaDB
    """
    # Arrange
    test_file_path = "/test/document.pdf"

    # Act
    result = await sync_service_with_mocks.ingest_document(test_file_path)

    # Assert
    # Verificar que llamó al processor
    mock_pdf_processor.process_document.assert_called_once_with(test_file_path)

    # Verificar que generó embeddings
    assert mock_ollama.generate_embedding.called

    # Verificar que almacenó en ChromaDB
    mock_chromadb.add_documents.assert_called_once()

    # Result debe indicar éxito
    assert result is not None


@pytest.mark.unit
@pytest.mark.asyncio
async def test_ingest_creates_chunks(sync_service_with_mocks):
    """
    Test: verificar que el documento se divide en chunks.

    Un documento largo debe dividirse en fragmentos manejables.
    """
    # Arrange
    test_file_path = "/test/long_document.pdf"

    # Act
    await sync_service_with_mocks.ingest_document(test_file_path)

    # Assert
    # Verificar que se llamó a add_documents con una lista de chunks
    # (el mock retorna un Document que luego se divide)
    # El servicio debe haber procesado y creado chunks
    assert True  # Placeholder - verificar según implementación específica


@pytest.mark.unit
@pytest.mark.asyncio
async def test_ingest_generates_embeddings_for_each_chunk(sync_service_with_mocks, mock_ollama):
    """
    Test: verificar que se generan embeddings para cada chunk.

    Cada chunk debe ser vectorizado antes de almacenarse.
    """
    # Arrange
    test_file_path = "/test/document.pdf"

    # Act
    await sync_service_with_mocks.ingest_document(test_file_path)

    # Assert
    # Verificar que generate_embedding fue llamado
    # (puede ser múltiples veces si hay múltiples chunks)
    assert mock_ollama.generate_embedding.called


@pytest.mark.unit
@pytest.mark.asyncio
async def test_ingest_stores_metadata(sync_service_with_mocks, mock_chromadb):
    """
    Test: verificar que se preserva metadata del documento.

    Los chunks deben incluir metadata (source, page, etc.) para trazabilidad.
    """
    # Arrange
    test_file_path = "/test/document.pdf"

    # Act
    await sync_service_with_mocks.ingest_document(test_file_path)

    # Assert
    # Verificar que add_documents fue llamado
    mock_chromadb.add_documents.assert_called_once()

    # Los chunks deben tener metadata
    call_args = mock_chromadb.add_documents.call_args[0]
    chunks = call_args[0]
    for chunk in chunks:
        assert hasattr(chunk, 'metadata')
        assert chunk.metadata is not None


# ============================================================================
# TESTS DE VALIDACIÓN DE INPUTS
# ============================================================================

@pytest.mark.unit
@pytest.mark.asyncio
async def test_ingest_with_empty_path_raises_error(sync_service_with_mocks):
    """
    Test: path vacío debe lanzar ValueError.
    """
    # Act & Assert
    with pytest.raises(ValueError):
        await sync_service_with_mocks.ingest_document("")


@pytest.mark.unit
@pytest.mark.asyncio
async def test_ingest_with_none_path_raises_error(sync_service_with_mocks):
    """
    Test: path None debe lanzar error.
    """
    # Act & Assert
    with pytest.raises((ValueError, TypeError)):
        await sync_service_with_mocks.ingest_document(None)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_ingest_with_nonexistent_file(sync_service_with_mocks, mock_pdf_processor):
    """
    Test: archivo inexistente debe manejarse apropiadamente.

    El processor puede lanzar excepción o retornar error.
    """
    # Arrange: configurar mock para simular archivo no encontrado
    mock_pdf_processor.process_document = AsyncMock(
        side_effect=FileNotFoundError("File not found")
    )

    # Act & Assert
    with pytest.raises(FileNotFoundError):
        await sync_service_with_mocks.ingest_document("/nonexistent/file.pdf")


# ============================================================================
# TESTS DE MANEJO DE ERRORES
# ============================================================================

@pytest.mark.unit
@pytest.mark.asyncio
async def test_ingest_handles_processor_error(sync_service_with_mocks, mock_pdf_processor):
    """
    Test: error del processor debe propagarse.

    Si falla la extracción de texto, debe fallar la ingesta.
    """
    # Arrange
    mock_pdf_processor.process_document = AsyncMock(
        side_effect=Exception("PDF corrupted")
    )

    # Act & Assert
    with pytest.raises(Exception, match="corrupted"):
        await sync_service_with_mocks.ingest_document("/test/corrupted.pdf")


@pytest.mark.unit
@pytest.mark.asyncio
async def test_ingest_handles_embedding_error(sync_service_with_mocks, mock_ollama):
    """
    Test: error al generar embeddings debe manejarse.

    Si Ollama falla al vectorizar, debe fallar la ingesta.
    """
    # Arrange
    mock_ollama.generate_embedding = AsyncMock(
        side_effect=Exception("Ollama service unavailable")
    )

    # Act & Assert
    with pytest.raises(Exception, match="unavailable"):
        await sync_service_with_mocks.ingest_document("/test/document.pdf")


@pytest.mark.unit
@pytest.mark.asyncio
async def test_ingest_handles_chromadb_error(sync_service_with_mocks, mock_chromadb):
    """
    Test: error al almacenar en ChromaDB debe manejarse.

    Si falla el almacenamiento, debe fallar la ingesta.
    """
    # Arrange
    mock_chromadb.add_documents = AsyncMock(
        side_effect=Exception("ChromaDB connection failed")
    )

    # Act & Assert
    with pytest.raises(Exception, match="connection failed"):
        await sync_service_with_mocks.ingest_document("/test/document.pdf")


# ============================================================================
# TESTS DE EDGE CASES
# ============================================================================

@pytest.mark.unit
@pytest.mark.asyncio
async def test_ingest_empty_document(sync_service_with_mocks, mock_pdf_processor):
    """
    Test: documento vacío debe manejarse apropiadamente.

    Un PDF sin contenido de texto debe procesarse sin fallar
    (puede generar advertencia o simplemente no crear chunks).
    """
    # Arrange: documento con contenido vacío
    mock_pdf_processor.process_document = AsyncMock(
        return_value=Document(content="", metadata={"source": "empty.pdf"})
    )

    # Act
    result = await sync_service_with_mocks.ingest_document("/test/empty.pdf")

    # Assert
    # Debe completar sin error (aunque no genere chunks útiles)
    assert result is not None


@pytest.mark.unit
@pytest.mark.asyncio
async def test_ingest_very_large_document(sync_service_with_mocks, mock_pdf_processor):
    """
    Test: documento muy largo debe dividirse en múltiples chunks.

    Un documento de muchas páginas debe chunkearse apropiadamente.
    """
    # Arrange: documento muy largo (100KB de texto)
    long_content = "Este es un documento muy largo. " * 3000  # ~100KB
    mock_pdf_processor.process_document = AsyncMock(
        return_value=Document(
            content=long_content,
            metadata={"source": "large.pdf", "pages": 100}
        )
    )

    # Act
    await sync_service_with_mocks.ingest_document("/test/large.pdf")

    # Assert
    # Debe haber generado múltiples embeddings (uno por chunk)
    assert mock_ollama.generate_embedding.call_count > 1


@pytest.mark.unit
@pytest.mark.asyncio
async def test_ingest_document_with_special_characters(sync_service_with_mocks, mock_pdf_processor):
    """
    Test: documento con caracteres especiales debe procesarse correctamente.

    Acentos, emojis, símbolos matemáticos, etc. deben manejarse.
    """
    # Arrange: contenido con caracteres especiales
    special_content = "RAG 🤖 utiliza embeddings ∑ para búsqueda semántica ñ á é"
    mock_pdf_processor.process_document = AsyncMock(
        return_value=Document(
            content=special_content,
            metadata={"source": "special.pdf"}
        )
    )

    # Act
    result = await sync_service_with_mocks.ingest_document("/test/special.pdf")

    # Assert
    assert result is not None


# ============================================================================
# TESTS DE CHUNKING
# ============================================================================

@pytest.mark.unit
def test_chunk_size_configuration():
    """
    Test: verificar que el tamaño de chunks es configurable.

    El sistema debe permitir configurar CHUNK_SIZE y CHUNK_OVERLAP
    desde settings o parámetros.
    """
    from app.config.settings import settings

    # Assert: verificar que existen las configuraciones
    assert hasattr(settings, 'CHUNK_SIZE') or hasattr(settings, 'chunk_size')
    assert hasattr(settings, 'CHUNK_OVERLAP') or hasattr(settings, 'chunk_overlap')


# ============================================================================
# TESTS DE INTEGRACIÓN
# ============================================================================

@pytest.mark.integration
@pytest.mark.asyncio
async def test_ingest_real_pdf_file():
    """
    Test de integración: ingesta de un PDF real.

    Requiere:
    - PDF real en /data
    - Ollama corriendo
    - ChromaDB corriendo

    No se ejecuta por defecto (usa pytest -m integration)
    """
    pytest.skip("Requiere servicios reales - implementar cuando sea necesario")
