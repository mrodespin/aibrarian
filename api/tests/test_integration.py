# /api/tests/test_integration.py
"""
Tests de Integración End-to-End.

Estos tests verifican el flujo completo del sistema con servicios reales:
- Ollama para embeddings y generación
- ChromaDB para almacenamiento vectorial
- Pipeline completo: ingest → store → retrieve → generate

IMPORTANTE:
Estos tests requieren servicios corriendo y se ejecutan con:
    pytest -m integration

No se ejecutan por defecto para mantener los tests rápidos.
"""

import pytest
from pathlib import Path


# ============================================================================
# TEST E2E: FLUJO COMPLETO DE INGESTA Y QUERY
# ============================================================================

@pytest.mark.integration
@pytest.mark.e2e
@pytest.mark.asyncio
async def test_full_rag_pipeline():
    """
    Test E2E: Flujo completo de ingesta y consulta.

    Requisitos previos:
    1. Ollama corriendo: ollama serve
    2. ChromaDB corriendo: docker-compose up chromadb
    3. PDF de prueba en /data/test_document.pdf

    Flujo:
    1. Ingesta el PDF de prueba
    2. Verifica que se almacenó en ChromaDB
    3. Hace una query relacionada con el contenido
    4. Verifica que la respuesta es coherente

    Este test tarda ~10-30 segundos dependiendo del hardware.
    """
    from app.core.services.sync_service import SyncService
    from app.core.services.rag_service import RAGService
    from app.adapters.outbound.ollama_adapter import OllamaAdapter
    from app.adapters.outbound.chromadb_adapter import ChromaDBAdapter
    from app.adapters.outbound.pdf_processor_adapter import PDFProcessorAdapter
    from app.config.settings import settings

    # Arrange: Inicializar servicios reales
    # Los adaptadores usan lazy initialization y obtienen configuración de settings
    ollama = OllamaAdapter()
    chromadb = ChromaDBAdapter()
    pdf_processor = PDFProcessorAdapter()

    sync_service = SyncService(
        document_processor=pdf_processor,
        vector_db=chromadb,
        llm=ollama
    )

    rag_service = RAGService(
        llm=ollama,
        vector_db=chromadb
    )

    # Verificar que existe el PDF de prueba
    test_pdf = Path(settings.data_directory) / "test_document.pdf"
    if not test_pdf.exists():
        pytest.skip(f"PDF de prueba no encontrado en {test_pdf}")

    # Act: Paso 1 - Ingestar el PDF
    try:
        await sync_service.ingest_document(str(test_pdf))
    except Exception as e:
        pytest.fail(f"Falló la ingesta: {e}")

    # Act: Paso 2 - Verificar que se almacenó
    try:
        stats = await chromadb.get_stats()
        assert stats["total_documents"] > 0 or stats.get("total_chunks", 0) > 0
    except Exception as e:
        pytest.fail(f"Falló la verificación de almacenamiento: {e}")

    # Act: Paso 3 - Hacer una query
    try:
        from app.core.domain.models import Query
        query = Query(question="¿De qué trata este documento?")
        response = await rag_service.ask_question(query)
    except Exception as e:
        pytest.fail(f"Falló la query: {e}")

    # Assert: Verificar respuesta
    assert response is not None
    assert response.answer is not None
    assert len(response.answer) > 0
    assert len(response.source_documents) > 0

    # Verificar que la respuesta menciona conceptos del documento
    # (el test_document.pdf habla de RAG, Bibliotecario-IA, etc.)
    answer_lower = response.answer.lower()
    assert any(keyword in answer_lower for keyword in ["rag", "bibliotecario", "documento", "sistema"])

    print(f"\n✅ Test E2E exitoso!")
    print(f"📝 Respuesta: {response.answer[:100]}...")
    print(f"📚 Fuentes: {len(response.source_documents)} chunks")


@pytest.mark.integration
@pytest.mark.asyncio
async def test_rag_with_empty_database():
    """
    Test de integración: query con base de datos vacía.

    Verifica que el sistema maneja gracefully el caso donde
    no hay documentos ingestados.
    """
    from app.core.services.rag_service import RAGService
    from app.adapters.outbound.ollama_adapter import OllamaAdapter
    from app.adapters.outbound.chromadb_adapter import ChromaDBAdapter
    from app.config.settings import settings

    # Arrange: RAG con colección vacía
    # Los adaptadores usan lazy initialization y obtienen configuración de settings
    ollama = OllamaAdapter()
    chromadb = ChromaDBAdapter()

    rag_service = RAGService(llm=ollama, vector_db=chromadb)

    # Act: Query sin documentos
    try:
        from app.core.domain.models import Query
        query = Query(question="¿Qué es RAG?")
        response = await rag_service.ask_question(query)
    except Exception as e:
        pytest.fail(f"El sistema debe manejar BD vacía gracefully, pero falló: {e}")

    # Assert: Debe retornar respuesta (aunque sin contexto)
    assert response is not None
    assert response.answer is not None
    # Sources puede estar vacío
    assert isinstance(response.source_documents, list)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_ollama_connectivity():
    """
    Test de integración: verificar conectividad con Ollama.

    Pre-check rápido antes de ejecutar tests E2E completos.
    """
    from app.adapters.outbound.ollama_adapter import OllamaAdapter
    from app.config.settings import settings

    # Arrange: El adaptador usa lazy initialization
    ollama = OllamaAdapter()

    # Act: Generar embedding simple
    try:
        embedding = await ollama.generate_embedding("test")
    except Exception as e:
        pytest.fail(f"Ollama no está disponible: {e}")

    # Assert
    assert embedding is not None
    assert isinstance(embedding, list)
    assert len(embedding) > 0
    print(f"✅ Ollama conectado (embedding dimension: {len(embedding)})")


@pytest.mark.integration
@pytest.mark.asyncio
async def test_chromadb_connectivity():
    """
    Test de integración: verificar conectividad con ChromaDB.

    Pre-check rápido antes de ejecutar tests E2E completos.
    """
    from app.adapters.outbound.chromadb_adapter import ChromaDBAdapter
    from app.config.settings import settings

    # Arrange: El adaptador usa lazy initialization
    chromadb = ChromaDBAdapter()

    # Act: Obtener estadísticas de la colección por defecto
    try:
        stats = await chromadb.get_collection_stats()
    except Exception as e:
        pytest.fail(f"ChromaDB no está disponible: {e}")

    # Assert
    assert stats is not None
    assert isinstance(stats, dict)
    print(f"✅ ChromaDB conectado (colección: {stats.get('collection_name')})")


# ============================================================================
# HELPERS PARA SETUP/TEARDOWN DE TESTS DE INTEGRACIÓN
# ============================================================================

@pytest.fixture
async def cleanup_test_collection():
    """
    Fixture para limpiar colecciones de test después de ejecutar.

    Uso:
        @pytest.mark.integration
        async def test_something(cleanup_test_collection):
            # test code
            pass
        # Al terminar, se limpia automáticamente
    """
    yield  # Test se ejecuta aquí

    # Cleanup después del test
    # (Implementar si necesitas limpiar colecciones de test)
    pass
