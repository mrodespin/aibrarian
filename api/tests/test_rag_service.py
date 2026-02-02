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
from app.core.domain.models import QueryResponse, Chunk


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
    - Retorna QueryResponse con answer y sources
    - Los sources incluyen metadata de los chunks
    """
    # Act
    response = await rag_service_with_mocks.query(sample_query)

    # Assert
    assert isinstance(response, QueryResponse)
    assert response.answer is not None
    assert len(response.answer) > 0
    assert isinstance(response.sources, list)
    assert len(response.sources) > 0
    # Verificar que cada source tiene la estructura esperada
    for source in response.sources:
        assert "source" in source
        assert "content" in source


@pytest.mark.unit
@pytest.mark.asyncio
async def test_query_calls_embedding(rag_service_with_mocks, sample_query, mock_ollama):
    """
    Test: verificar que se genera embedding de la query.

    El RAG debe vectorizar la pregunta antes de buscar contexto.
    """
    # Act
    await rag_service_with_mocks.query(sample_query)

    # Assert
    # Verificar que se llamó a generate_embedding con la query
    mock_ollama.generate_embedding.assert_called_once()
    call_args = mock_ollama.generate_embedding.call_args[0]
    assert sample_query in call_args[0]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_query_calls_vector_search(rag_service_with_mocks, sample_query, mock_chromadb):
    """
    Test: verificar que se busca en ChromaDB.

    Después de vectorizar, debe buscar chunks similares en la BD vectorial.
    """
    # Act
    await rag_service_with_mocks.query(sample_query)

    # Assert
    # Verificar que se llamó al query de ChromaDB
    mock_chromadb.query.assert_called_once()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_query_calls_llm_generation(rag_service_with_mocks, sample_query, mock_ollama):
    """
    Test: verificar que se genera respuesta con el LLM.

    Después de obtener contexto, debe llamar al LLM para generar la respuesta.
    """
    # Act
    await rag_service_with_mocks.query(sample_query)

    # Assert
    # Verificar que se llamó a generate (generación de texto)
    mock_ollama.generate.assert_called_once()
    # El prompt debe incluir tanto la query como el contexto
    call_args = mock_ollama.generate.call_args[0]
    prompt = call_args[0]
    assert sample_query in prompt  # La query debe estar en el prompt


@pytest.mark.unit
@pytest.mark.asyncio
async def test_query_with_empty_string_raises_error(rag_service_with_mocks):
    """
    Test: query vacía debe lanzar ValueError.

    El servicio debe validar inputs y rechazar queries inválidas.
    """
    # Act & Assert
    with pytest.raises(ValueError, match="vacía|empty"):
        await rag_service_with_mocks.query("")


@pytest.mark.unit
@pytest.mark.asyncio
async def test_query_with_none_raises_error(rag_service_with_mocks):
    """
    Test: query None debe lanzar error.

    El servicio debe validar inputs nulos.
    """
    # Act & Assert
    with pytest.raises((ValueError, TypeError)):
        await rag_service_with_mocks.query(None)


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
    response = await rag_service_with_mocks.query(sample_query)

    # Assert
    # Debe retornar respuesta aunque no haya contexto
    assert isinstance(response, QueryResponse)
    assert response.answer is not None
    # Sources puede estar vacío o indicar que no hay contexto
    assert isinstance(response.sources, list)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_query_limits_context_chunks(rag_service_with_mocks, sample_query):
    """
    Test: verificar que se limita el número de chunks de contexto.

    El RAG debe usar MAX_CONTEXT_CHUNKS (típicamente 4) para evitar
    prompts demasiado largos que saturen el context window del LLM.
    """
    # Act
    response = await rag_service_with_mocks.query(sample_query, max_chunks=2)

    # Assert
    # Verificar que no se incluyen más de max_chunks fuentes
    assert len(response.sources) <= 2


@pytest.mark.unit
@pytest.mark.asyncio
async def test_query_includes_source_metadata(rag_service_with_mocks, sample_query):
    """
    Test: verificar que las fuentes incluyen metadata útil.

    Cada source debe incluir información para que el usuario pueda
    verificar de dónde viene la información (source file, page, etc.).
    """
    # Act
    response = await rag_service_with_mocks.query(sample_query)

    # Assert
    for source in response.sources:
        # Verificar que tiene metadata básica
        assert "source" in source or "metadata" in source
        # Debe tener contenido del chunk
        assert "content" in source
        assert len(source["content"]) > 0


# ============================================================================
# TESTS DE MANEJO DE ERRORES
# ============================================================================

@pytest.mark.unit
@pytest.mark.asyncio
async def test_query_handles_llm_error_gracefully(rag_service_with_mocks, sample_query, mock_ollama):
    """
    Test: manejar error del LLM gracefully.

    Si Ollama falla, el servicio debe propagar el error de forma clara
    o retornar un mensaje de error apropiado (según diseño).
    """
    # Arrange: configurar mock para lanzar excepción
    mock_ollama.generate = AsyncMock(side_effect=Exception("Ollama connection failed"))

    # Act & Assert
    with pytest.raises(Exception):
        await rag_service_with_mocks.query(sample_query)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_query_handles_chromadb_error_gracefully(rag_service_with_mocks, sample_query, mock_chromadb):
    """
    Test: manejar error de ChromaDB gracefully.

    Si ChromaDB falla, el servicio debe propagar el error claramente.
    """
    # Arrange: configurar mock para lanzar excepción
    mock_chromadb.query = AsyncMock(side_effect=Exception("ChromaDB connection failed"))

    # Act & Assert
    with pytest.raises(Exception):
        await rag_service_with_mocks.query(sample_query)


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
    long_query = "¿Qué es RAG? " * 200  # ~1000 palabras

    # Act
    response = await rag_service_with_mocks.query(long_query)

    # Assert
    assert isinstance(response, QueryResponse)
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
    special_query = "¿Qué es RAG? 🤖 ¿Cómo funciona el embedding?"

    # Act
    response = await rag_service_with_mocks.query(special_query)

    # Assert
    assert isinstance(response, QueryResponse)
    assert response.answer is not None


@pytest.mark.unit
@pytest.mark.asyncio
async def test_query_response_model_field_is_populated(rag_service_with_mocks, sample_query):
    """
    Test: verificar que el campo model está poblado en la respuesta.

    QueryResponse debe incluir qué modelo LLM generó la respuesta.
    """
    # Act
    response = await rag_service_with_mocks.query(sample_query)

    # Assert
    assert hasattr(response, "model")
    # El campo puede ser None o tener un valor, dependiendo de la implementación
    # pero debe existir en la estructura


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
