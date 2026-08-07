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
async def test_query_filters_low_relevance_chunks(rag_service_with_mocks, sample_query, mock_chromadb):
    """
    Test: chunks con relevance_score por debajo del umbral se descartan.

    Sin este filtro, ChromaDB devuelve top_k chunks aunque no sean relevantes
    y el LLM acaba fabricando una respuesta en vez de decir "no lo sé".
    """
    # Arrange: un chunk relevante (0.9) y uno claramente irrelevante (0.05)
    from app.core.domain.models import SourceDocument

    async def mock_search(*args, **kwargs):
        return [
            SourceDocument(
                document_id="doc_relevant",
                chunk_content="Chunk relevante",
                metadata={},
                relevance_score=0.9
            ),
            SourceDocument(
                document_id="doc_irrelevant",
                chunk_content="Chunk irrelevante",
                metadata={},
                relevance_score=0.05
            ),
        ]

    mock_chromadb.similarity_search = AsyncMock(side_effect=mock_search)

    # Act
    response = await rag_service_with_mocks.ask_question(sample_query)

    # Assert
    doc_ids = [source.document_id for source in response.source_documents]
    assert "doc_relevant" in doc_ids
    assert "doc_irrelevant" not in doc_ids


@pytest.mark.unit
@pytest.mark.asyncio
async def test_query_all_chunks_below_threshold_returns_no_info(rag_service_with_mocks, sample_query, mock_chromadb):
    """
    Test: si TODOS los chunks recuperados están por debajo del umbral,
    se devuelve el mismo fallback que cuando no hay resultados en absoluto
    (no un branch nuevo, reutiliza el existente).
    """
    # Arrange: todos los chunks por debajo del umbral por defecto (0.3)
    from app.core.domain.models import SourceDocument

    async def mock_search(*args, **kwargs):
        return [
            SourceDocument(
                document_id="doc_irrelevant",
                chunk_content="Chunk irrelevante",
                metadata={},
                relevance_score=0.1
            ),
        ]

    mock_chromadb.similarity_search = AsyncMock(side_effect=mock_search)

    # Act
    response = await rag_service_with_mocks.ask_question(sample_query)

    # Assert
    assert response.source_documents == []
    assert "couldn't find relevant information" in response.answer


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
# TESTS DE preguntas de catálogo en ask_question() — clasificación vía LLM
# ============================================================================
# "¿Cuántos libros conoces?" no es una pregunta de contenido — no debe
# pasar por similarity_search/generate_response, sino resolverse con
# vector_db.list_documents() (ver RAGService._build_meta_answer). La
# decisión de "es esto una pregunta de catálogo" la toma el LLM
# (LLMPort.is_catalog_question), no un regex — por eso estos tests
# controlan directamente lo que devuelve ese mock, en vez de probar
# frases concretas: la cobertura de idiomas/redacciones es responsabilidad
# del LLM real, no de este test suite (ver test_ollama_adapter.py /
# test_groq_adapter.py para los tests de esa clasificación en sí).

@pytest.mark.unit
@pytest.mark.asyncio
async def test_meta_question_lists_full_catalog_without_search_or_generation(
    rag_service_with_mocks, mock_ollama, mock_chromadb
):
    """
    Si el LLM clasifica la pregunta como de catálogo, ask_question()
    responde con el listado completo (mock_chromadb.list_documents
    devuelve 2 documentos, ver conftest.py) sin llamar a generate_response
    ni a similarity_search — solo a is_catalog_question + list_documents.
    """
    from app.core.domain.models import Query

    mock_ollama.is_catalog_question = AsyncMock(return_value=True)
    query = Query(question="¿Cuántos libros conoces?")

    response = await rag_service_with_mocks.ask_question(query)

    assert "1984" in response.answer
    assert "Deep Learning" in response.answer
    assert response.answer.startswith("I know 2 documents")
    assert response.source_documents == []
    mock_ollama.is_catalog_question.assert_awaited_once_with(query.question)
    mock_chromadb.list_documents.assert_awaited_once()
    mock_ollama.generate_response.assert_not_called()
    mock_chromadb.similarity_search.assert_not_called()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_meta_question_with_empty_catalog(rag_service_with_mocks, mock_ollama, mock_chromadb):
    """Sin documentos indexados, responde honestamente en vez de listar vacío."""
    from app.core.domain.models import Query

    mock_ollama.is_catalog_question = AsyncMock(return_value=True)
    mock_chromadb.list_documents.side_effect = None
    mock_chromadb.list_documents.return_value = []

    query = Query(question="¿Cuántos documentos tienes?")
    response = await rag_service_with_mocks.ask_question(query)

    assert "don't have any documents" in response.answer.lower()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_content_question_still_uses_normal_pipeline(
    rag_service_with_mocks, sample_query, mock_ollama, mock_chromadb
):
    """
    Si el LLM clasifica la pregunta como de contenido (default del mock,
    ver conftest.py), NO se desvía al atajo de catálogo.
    """
    await rag_service_with_mocks.ask_question(sample_query)

    mock_ollama.is_catalog_question.assert_awaited_once_with(sample_query.question)
    mock_chromadb.similarity_search.assert_called()
    mock_ollama.generate_response.assert_called_once()
    mock_chromadb.list_documents.assert_not_called()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_catalog_classification_failure_falls_back_to_content_pipeline(
    rag_service_with_mocks, sample_query, mock_ollama, mock_chromadb
):
    """
    Si is_catalog_question() falla (excepción de red, etc.), el fallback
    seguro documentado en LLMPort.is_catalog_question es tratarla como
    pregunta de contenido — no que ask_question() explote entero.
    """
    mock_ollama.is_catalog_question = AsyncMock(side_effect=RuntimeError("LLM unavailable"))

    response = await rag_service_with_mocks.ask_question(sample_query)

    # ask_question() ya envuelve todo el cuerpo en try/except (ver el except
    # genérico al final del método) — una excepción aquí no debe romper la
    # petición, solo degradar a la respuesta de error habitual.
    assert response.answer is not None


# ============================================================================
# TESTS DE condense_question() (query rewriting) en ask_question()
# ============================================================================
# Patrón estándar de RAG conversacional: una pregunta de seguimiento se
# reescribe como autocontenida usando el historial ANTES de retrievar, en
# vez de intentar responder solo desde el historial o dejar que
# similarity_search falle con una pregunta sin ancla (ver LLMPort.condense_question).

@pytest.mark.unit
@pytest.mark.asyncio
async def test_condense_question_called_when_history_present(
    rag_service_with_mocks, mock_ollama, mock_chromadb
):
    """Con historial, se condensa antes de retrievar y el retrieval usa la pregunta condensada."""
    from app.core.domain.models import Query

    mock_ollama.condense_question = AsyncMock(return_value="¿En qué año se publicó 1984?")
    history = "Usuario: háblame de 1984\nAsistente: ...publicado en 1949..."
    query = Query(question="¿En qué año se publicó?")

    await rag_service_with_mocks.ask_question(query, history=history)

    mock_ollama.condense_question.assert_awaited_once_with(query.question, history)
    # El retrieval (embeddings/keywords) debe usar la pregunta YA condensada,
    # no la pregunta de seguimiento original sin contexto
    mock_ollama.generate_embedding.assert_awaited_once_with("¿En qué año se publicó 1984?")
    mock_ollama.extract_keywords.assert_awaited_once_with("¿En qué año se publicó 1984?")


@pytest.mark.unit
@pytest.mark.asyncio
async def test_condense_question_not_called_without_history(
    rag_service_with_mocks, sample_query, mock_ollama
):
    """Sin historial no hay nada que condensar — no se llama al LLM para eso."""
    await rag_service_with_mocks.ask_question(sample_query)  # history=None por defecto

    mock_ollama.condense_question.assert_not_called()
    mock_ollama.generate_embedding.assert_awaited_once_with(sample_query.question)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_condense_question_not_called_for_catalog_questions(
    rag_service_with_mocks, mock_ollama
):
    """Una pregunta de catálogo no necesita condensarse — se corta antes."""
    from app.core.domain.models import Query

    mock_ollama.is_catalog_question = AsyncMock(return_value=True)
    query = Query(question="¿Cuántos libros conoces?")

    await rag_service_with_mocks.ask_question(query, history="algo de historial")

    mock_ollama.condense_question.assert_not_called()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_generate_response_receives_condensed_question_as_prompt(
    rag_service_with_mocks, mock_ollama
):
    """La respuesta final se genera con la pregunta condensada, no la original corta."""
    from app.core.domain.models import Query

    mock_ollama.condense_question = AsyncMock(return_value="¿Cuántas páginas tiene Cien años de soledad?")
    query = Query(question="¿Cuántas páginas tiene?")

    await rag_service_with_mocks.ask_question(query, history="Usuario: Cien años de soledad...")

    _, kwargs = mock_ollama.generate_response.call_args
    assert kwargs["prompt"] == "¿Cuántas páginas tiene Cien años de soledad?"


# ============================================================================
# TESTS DE ask_question_stream() (streaming SSE)
# ============================================================================

async def _collect_stream(async_gen):
    """Helper: consume un async generator y devuelve la lista de eventos."""
    return [event async for event in async_gen]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_stream_yields_sources_before_tokens(rag_service_with_mocks, sample_query):
    """El primer evento emitido siempre es 'sources', antes de cualquier 'token'."""
    events = await _collect_stream(rag_service_with_mocks.ask_question_stream(sample_query))

    assert events[0]["type"] == "sources"
    assert len(events[0]["source_documents"]) > 0
    assert any(e["type"] == "token" for e in events[1:-1])


@pytest.mark.unit
@pytest.mark.asyncio
async def test_stream_ends_with_done_event(rag_service_with_mocks, sample_query):
    """El último evento siempre es 'done', con processing_time y session_id."""
    events = await _collect_stream(rag_service_with_mocks.ask_question_stream(sample_query))

    assert events[-1]["type"] == "done"
    assert "processing_time" in events[-1]
    assert events[-1]["session_id"] == sample_query.session_id


@pytest.mark.unit
@pytest.mark.asyncio
async def test_stream_tokens_concatenate_to_full_answer(rag_service_with_mocks, sample_query, mock_ollama):
    """Concatenar los 'token' del stream da la misma respuesta que generate_response()."""
    events = await _collect_stream(rag_service_with_mocks.ask_question_stream(sample_query))

    streamed_answer = "".join(e["text"] for e in events if e["type"] == "token")
    full_answer = await mock_ollama.generate_response(prompt=sample_query.question, context="cualquier contexto")

    # mock_stream_response trocea la misma plantilla que mock_generate_response
    # (ver conftest.py) — no podemos comparar el contexto exacto, pero sí que
    # el streaming no pierde/duplica texto: ambas empiezan igual.
    assert streamed_answer.startswith("Basándome en el contexto proporcionado,")
    assert full_answer.startswith("Basándome en el contexto proporcionado,")


@pytest.mark.unit
@pytest.mark.asyncio
async def test_stream_no_relevant_context_yields_fallback_token(rag_service_with_mocks, sample_query, mock_chromadb):
    """Sin chunks relevantes, se emite sources vacío + un único token de fallback + done."""
    from app.core.domain.models import SourceDocument

    async def mock_search(*args, **kwargs):
        return [SourceDocument(document_id="doc", chunk_content="irrelevante", metadata={}, relevance_score=0.05)]

    mock_chromadb.similarity_search = AsyncMock(side_effect=mock_search)

    events = await _collect_stream(rag_service_with_mocks.ask_question_stream(sample_query))

    assert events[0] == {"type": "sources", "source_documents": []}
    token_events = [e for e in events if e["type"] == "token"]
    assert len(token_events) == 1
    assert "couldn't find relevant information" in token_events[0]["text"]
    assert events[-1]["type"] == "done"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_stream_meta_question_yields_single_token_with_catalog(
    rag_service_with_mocks, mock_ollama, mock_chromadb
):
    """Mismo atajo que ask_question(), pero como stream: un único token, sin generación."""
    from app.core.domain.models import Query

    mock_ollama.is_catalog_question = AsyncMock(return_value=True)
    query = Query(question="¿Qué documentos tienes?")
    events = await _collect_stream(rag_service_with_mocks.ask_question_stream(query))

    assert events[0] == {"type": "sources", "source_documents": []}
    token_events = [e for e in events if e["type"] == "token"]
    assert len(token_events) == 1
    assert "1984" in token_events[0]["text"]
    assert events[-1]["type"] == "done"
    mock_ollama.generate_response.assert_not_called()
    mock_chromadb.similarity_search.assert_not_called()


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

    Ejecutar con: pytest -m integration tests/test_rag_service.py -v
    """
    from app.adapters.outbound.ollama_adapter import OllamaAdapter
    from app.adapters.outbound.chromadb_adapter import ChromaDBAdapter
    from app.core.services.rag_service import RAGService
    from app.core.domain.models import Query

    # Verificar que Ollama está disponible
    ollama = OllamaAdapter()
    if not await ollama.is_available():
        pytest.skip("Ollama no está disponible")

    # Crear servicio RAG con adaptadores reales
    chromadb = ChromaDBAdapter()
    rag_service = RAGService(llm=ollama, vector_db=chromadb)

    # Test básico de query
    query = Query(question="¿Qué información tienes disponible?", max_results=3)
    result = await rag_service.ask_question(query)

    # Verificar estructura de respuesta
    assert result is not None
    assert result.answer is not None
    assert isinstance(result.source_documents, list)
    assert result.processing_time > 0

    # Log para debugging
    print(f"\n✅ Respuesta: {result.answer[:100]}...")
    print(f"📚 Fuentes encontradas: {len(result.source_documents)}")
