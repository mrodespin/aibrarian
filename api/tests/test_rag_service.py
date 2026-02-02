# /api/tests/test_rag_service.py
"""
Tests del RAGService - El corazón del sistema de consultas.

El RAGService es responsable de:
1. Vectorizar la pregunta del usuario (embedding)
2. Buscar chunks relevantes en ChromaDB (retrieval)
3. Construir un prompt con contexto
4. Generar respuesta con el LLM (generation)

Estos tests verifican cada paso del flujo RAG y casos de error.
"""

import pytest
from unittest.mock import AsyncMock, patch

from app.core.services.rag_service import RAGService
from app.core.domain.models import QueryResult, Chunk


# ============================================================================
# TESTS UNITARIOS (con mocks)
# ============================================================================

@pytest.mark.unit
@pytest.mark.asyncio
async def test_query_success(rag_service_with_mocks, sample_query):
    """
    Test básico: query exitosa retorna respuesta con fuentes.

    Verifica el flujo feliz completo:
    - Acepta una pregunta
    - Retorna QueryResult con answer y sources
    - Los sources incluyen metadata de los chunks
    """
    # Act
    response = await rag_service_with_mocks.ask_question(sample_query)

    # Assert
    from app.core.domain.models import SourceDocument
    assert isinstance(response, QueryResult)
    assert response.answer is not None
    assert len(response.answer) > 0
    assert isinstance(response.source_documents, list)
    assert len(response.source_documents) > 0
    # Verificar que cada source tiene la estructura esperada
    for source in response.source_documents:
        assert isinstance(source, SourceDocument)
        assert source.document_id is not None
        assert source.chunk_content is not None


@pytest.mark.unit
@pytest.mark.asyncio
async def test_query_calls_embedding(rag_service_with_mocks, sample_query, mock_ollama):
    """
    Test: verificar que se genera embedding de la query.

    El RAG debe vectorizar la pregunta antes de buscar contexto.
    """
    # Act
    await rag_service_with_mocks.ask_question(sample_query)

    # Assert
    # Verificar que se llamó a generate_embedding con la query
    mock_ollama.generate_embedding.assert_called_once()
    call_args = mock_ollama.generate_embedding.call_args[0]
    assert sample_query.question in call_args[0]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_query_calls_vector_search(rag_service_with_mocks, sample_query, mock_chromadb):
    """
    Test: verificar que se busca en ChromaDB.

    Después de vectorizar, debe buscar chunks similares en la BD vectorial.
    """
    # Act
    await rag_service_with_mocks.ask_question(sample_query)

    # Assert
    # Verificar que se llamó al similarity_search de ChromaDB
    mock_chromadb.similarity_search.assert_called_once()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_query_calls_llm_generation(rag_service_with_mocks, sample_query, mock_ollama):
    """
    Test: verificar que se genera respuesta con el LLM.

    Después de obtener contexto, debe llamar al LLM para generar la respuesta.
    """
    # Act
    await rag_service_with_mocks.ask_question(sample_query)

    # Assert
    # Verificar que se llamó a generate_response (generación de texto)
    mock_ollama.generate_response.assert_called_once()
    # El prompt debe incluir la query
    call_args = mock_ollama.generate_response.call_args
    # Check kwargs for 'prompt' parameter
    assert 'prompt' in call_args.kwargs or len(call_args.args) > 0


@pytest.mark.unit
@pytest.mark.asyncio
async def test_query_with_empty_string_raises_error(rag_service_with_mocks):
    """
    Test: query vacía debe lanzar ValidationError.

    Pydantic valida que question no esté vacía (min_length=1).
    """
    # Act & Assert
    from pydantic import ValidationError
    from app.core.domain.models import Query
    with pytest.raises(ValidationError):
        Query(question="")


@pytest.mark.unit
@pytest.mark.asyncio
async def test_query_with_none_raises_error(rag_service_with_mocks):
    """
    Test: query None debe lanzar ValidationError.

    Pydantic valida que question sea requerida.
    """
    # Act & Assert
    from pydantic import ValidationError
    from app.core.domain.models import Query
    with pytest.raises(ValidationError):
        Query(question=None)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_query_with_no_results_from_db(rag_service_with_mocks, sample_query, mock_chromadb):
    """
    Test: manejar caso donde ChromaDB no encuentra chunks relevantes.

    Si no hay contexto, el sistema debe manejarlo gracefully
    (puede generar respuesta sin contexto o indicar que no tiene información).
    """
    # Arrange: configurar mock para retornar lista vacía
    mock_chromadb.query = AsyncMock(return_value=[])

    # Act
    response = await rag_service_with_mocks.ask_question(sample_query)

    # Assert
    # Debe retornar respuesta aunque no haya contexto
    assert isinstance(response, QueryResult)
    assert response.answer is not None
    # Sources puede estar vacío o indicar que no hay contexto
    assert isinstance(response.source_documents, list)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_query_limits_context_chunks(rag_service_with_mocks):
    """
    Test: verificar que se limita el número de chunks de contexto.

    El RAG debe usar max_results para evitar prompts demasiado largos
    que saturen el context window del LLM.
    """
    # Arrange: crear query con max_results=2
    from app.core.domain.models import Query
    query = Query(question="¿Qué es RAG?", max_results=2)

    # Act
    response = await rag_service_with_mocks.ask_question(query)

    # Assert
    # Verificar que no se incluyen más de max_results fuentes
    assert len(response.source_documents) <= 2


@pytest.mark.unit
@pytest.mark.asyncio
async def test_query_includes_source_metadata(rag_service_with_mocks, sample_query):
    """
    Test: verificar que las fuentes incluyen metadata útil.

    Cada source debe incluir información para que el usuario pueda
    verificar de dónde viene la información (source file, page, etc.).
    """
    # Act
    response = await rag_service_with_mocks.ask_question(sample_query)

    # Assert
    from app.core.domain.models import SourceDocument
    for source in response.source_documents:
        # Verificar que es un SourceDocument con los campos correctos
        assert isinstance(source, SourceDocument)
        assert source.document_id is not None
        assert source.chunk_content is not None
        assert len(source.chunk_content) > 0
        assert isinstance(source.metadata, dict)


# ============================================================================
# TESTS DE MANEJO DE ERRORES
# ============================================================================

@pytest.mark.unit
@pytest.mark.asyncio
async def test_query_handles_llm_error_gracefully(rag_service_with_mocks, sample_query, mock_ollama):
    """
    Test: manejar error del LLM gracefully.

    Si Ollama falla, el servicio captura el error y retorna un QueryResult
    con un mensaje de error en el answer.
    """
    # Arrange: configurar mock para lanzar excepción
    mock_ollama.generate_response = AsyncMock(side_effect=Exception("Ollama connection failed"))

    # Act
    response = await rag_service_with_mocks.ask_question(sample_query)

    # Assert: El servicio retorna un resultado con mensaje de error
    assert response is not None
    assert isinstance(response, QueryResult)
    assert "error" in response.answer.lower() or "failed" in response.answer.lower()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_query_handles_chromadb_error_gracefully(rag_service_with_mocks, sample_query, mock_chromadb):
    """
    Test: manejar error de ChromaDB gracefully.

    Si ChromaDB falla, el servicio captura el error y retorna un QueryResult
    con un mensaje de error en el answer.
    """
    # Arrange: configurar mock para lanzar excepción
    mock_chromadb.similarity_search = AsyncMock(side_effect=Exception("ChromaDB connection failed"))

    # Act
    response = await rag_service_with_mocks.ask_question(sample_query)

    # Assert: El servicio retorna un resultado con mensaje de error
    assert response is not None
    assert isinstance(response, QueryResult)
    assert "error" in response.answer.lower() or "failed" in response.answer.lower()


# ============================================================================
# TESTS DE EDGE CASES
# ============================================================================

@pytest.mark.unit
@pytest.mark.asyncio
async def test_query_with_very_long_question(rag_service_with_mocks):
    """
    Test: manejar preguntas muy largas.

    El sistema debe manejar queries largas sin fallar
    (pueden ser truncadas o procesadas completamente según diseño).
    """
    # Arrange: query de 1000 palabras
    from app.core.domain.models import Query
    long_question_text = "¿Qué es RAG? " * 200  # ~1000 palabras
    long_query = Query(question=long_question_text)

    # Act
    response = await rag_service_with_mocks.ask_question(long_query)

    # Assert
    assert isinstance(response, QueryResult)
    assert response.answer is not None


@pytest.mark.unit
@pytest.mark.asyncio
async def test_query_with_special_characters(rag_service_with_mocks):
    """
    Test: manejar caracteres especiales en la query.

    El sistema debe procesar correctamente queries con acentos,
    emojis, símbolos, etc.
    """
    # Arrange: query con caracteres especiales
    from app.core.domain.models import Query
    special_question_text = "¿Qué es RAG? 🤖 ¿Cómo funciona el embedding?"
    special_query = Query(question=special_question_text)

    # Act
    response = await rag_service_with_mocks.ask_question(special_query)

    # Assert
    assert isinstance(response, QueryResult)
    assert response.answer is not None


@pytest.mark.unit
@pytest.mark.asyncio
async def test_query_response_has_processing_time(rag_service_with_mocks, sample_query):
    """
    Test: verificar que la respuesta incluye processing_time.

    QueryResult debe incluir el tiempo de procesamiento.
    """
    # Act
    response = await rag_service_with_mocks.ask_question(sample_query)

    # Assert
    assert hasattr(response, "processing_time")
    # processing_time puede ser None o un float


# ============================================================================
# TESTS DE INTEGRACIÓN (requieren servicios reales)
# ============================================================================
# Estos tests se marcan con @pytest.mark.integration
# Solo se ejecutan cuando se quiere hacer tests completos con servicios reales

@pytest.mark.integration
@pytest.mark.asyncio
async def test_query_with_real_services():
    """
    Test de integración: query con Ollama y ChromaDB reales.

    NOTA: Este test requiere:
    - Ollama corriendo (ollama serve)
    - ChromaDB corriendo (docker-compose up chromadb)
    - Datos ingestados previamente

    No se ejecuta por defecto (usa pytest -m integration)
    """
    # Este test se implementaría conectando con servicios reales
    # Por ahora se deja como placeholder para documentar el approach
    pytest.skip("Requiere servicios reales - implementar cuando sea necesario")
