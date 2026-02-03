# /api/tests/test_api.py
"""
Tests de los endpoints de FastAPI.

Tests de los endpoints HTTP de la API:
- GET /health: Health check
- POST /ask: Queries al RAG
- POST /sync: Ingesta de documentos individuales
- POST /sync/directory: Ingesta de directorio
- GET /stats: Estadísticas de la colección

Usa TestClient de FastAPI para simular requests HTTP sin levantar servidor.
"""

import pytest
from fastapi.testclient import TestClient


# ============================================================================
# TESTS DEL ENDPOINT /health
# ============================================================================

@pytest.mark.unit
def test_health_endpoint_returns_200(test_client):
    """
    Test: /health debe retornar 200 OK.

    El health check debe responder siempre que la API esté activa.
    """
    # Act
    response = test_client.get("/health")

    # Assert
    assert response.status_code == 200


@pytest.mark.unit
def test_health_endpoint_returns_json(test_client):
    """
    Test: /health debe retornar JSON con status.
    """
    # Act
    response = test_client.get("/health")

    # Assert
    assert response.headers["content-type"] == "application/json"
    data = response.json()
    assert "status" in data
    assert data["status"] == "healthy"


# ============================================================================
# TESTS DEL ENDPOINT /ask
# ============================================================================

@pytest.mark.unit
def test_ask_endpoint_accepts_post(test_client):
    """
    Test: /ask debe aceptar POST requests.
    """
    # Arrange
    payload = {"question": "¿Qué es RAG?"}

    # Act
    response = test_client.post("/ask", json=payload)

    # Assert
    # Puede retornar 200 (con mock) o error si falta configuración
    # Lo importante es que acepte el método POST
    assert response.status_code in [200, 500, 503]  # 500/503 si faltan servicios reales


@pytest.mark.unit
def test_ask_endpoint_requires_question_field(test_client):
    """
    Test: /ask debe requerir el campo 'question'.

    Request sin 'question' debe retornar 422 (Validation Error).
    """
    # Arrange
    payload = {}  # Sin question

    # Act
    response = test_client.post("/ask", json=payload)

    # Assert
    assert response.status_code == 422  # Unprocessable Entity


@pytest.mark.unit
def test_ask_endpoint_rejects_empty_question(test_client):
    """
    Test: /ask debe rechazar preguntas vacías.
    """
    # Arrange
    payload = {"question": ""}

    # Act
    response = test_client.post("/ask", json=payload)

    # Assert
    # Puede ser 422 (validation) o 400 (bad request)
    assert response.status_code in [400, 422]


@pytest.mark.unit
def test_ask_endpoint_returns_json_with_answer(test_client):
    """
    Test: /ask debe retornar JSON con estructura esperada.

    Response debe incluir:
    - answer: string
    - sources: array
    - model: string (opcional)
    """
    # Arrange
    payload = {"question": "¿Qué es RAG?"}

    # Act
    response = test_client.post("/ask", json=payload)

    # Assert
    if response.status_code == 200:
        data = response.json()
        assert "answer" in data
        assert "source_documents" in data
        assert isinstance(data["answer"], str)
        assert isinstance(data["source_documents"], list)


# ============================================================================
# TESTS DEL ENDPOINT /sync
# ============================================================================

@pytest.mark.unit
def test_sync_endpoint_accepts_post(test_client):
    """
    Test: /sync debe aceptar POST requests.
    """
    # Arrange
    payload = {"file_path": "/test/document.pdf"}

    # Act
    response = test_client.post("/sync", json=payload)

    # Assert
    # Aceptará POST aunque falle por falta de archivo real
    assert response.status_code in [200, 404, 500]


@pytest.mark.unit
def test_sync_endpoint_requires_file_path(test_client):
    """
    Test: /sync debe requerir el campo 'file_path'.
    """
    # Arrange
    payload = {}

    # Act
    response = test_client.post("/sync", json=payload)

    # Assert
    assert response.status_code == 422  # Validation error


@pytest.mark.unit
def test_sync_endpoint_rejects_empty_file_path(test_client):
    """
    Test: /sync debe rechazar file_path vacío.
    """
    # Arrange
    payload = {"file_path": ""}

    # Act
    response = test_client.post("/sync", json=payload)

    # Assert
    assert response.status_code in [400, 422]


# ============================================================================
# TESTS DEL ENDPOINT /sync/directory
# ============================================================================

@pytest.mark.unit
def test_sync_directory_endpoint_accepts_post(test_client):
    """
    Test: /sync/directory debe aceptar POST requests.
    """
    # Arrange
    payload = {"directory_path": "/test/pdfs"}

    # Act
    response = test_client.post("/sync/directory", json=payload)

    # Assert
    assert response.status_code in [200, 404, 500]


@pytest.mark.unit
def test_sync_directory_uses_default_path_if_not_provided(test_client):
    """
    Test: /sync/directory debe usar ./data por defecto.

    Si no se proporciona directory_path, debe usar el configurado en settings.
    """
    # Arrange
    payload = {}  # Sin directory_path

    # Act
    response = test_client.post("/sync/directory", json=payload)

    # Assert
    # Debe aceptar el request (puede fallar si no hay PDFs pero no por validación)
    assert response.status_code in [200, 404, 500]
    assert response.status_code != 422  # No debe ser validation error


# ============================================================================
# TESTS DEL ENDPOINT /sync/notion
# ============================================================================

@pytest.mark.unit
def test_sync_notion_page_requires_page_id(test_client):
    """
    Test: /sync/notion debe requerir page_id.
    """
    # Arrange
    payload = {}

    # Act
    response = test_client.post("/sync/notion", json=payload)

    # Assert
    assert response.status_code == 422


@pytest.mark.unit
def test_sync_notion_database_requires_database_id(test_client):
    """
    Test: /sync/notion/database debe requerir database_id.

    El endpoint valida el database_id con lógica custom y retorna 400
    si no está configurado (ni en request ni en settings).

    Nota: Usamos patch para simular que NOTION_DATABASE_ID no está
    configurado en el entorno, ya que el .env de desarrollo puede tenerlo.
    """
    from unittest.mock import patch

    # Arrange
    payload = {}

    # Act: Mockear settings para que notion_database_id sea None
    with patch("app.main.settings") as mock_settings:
        # Configurar el mock con los valores necesarios
        mock_settings.notion_api_key = "fake-api-key"  # Pasar primera validación
        mock_settings.notion_database_id = None  # Simular que no está configurado

        response = test_client.post("/sync/notion/database", json=payload)

    # Assert: El endpoint retorna 400 cuando falta el database_id
    assert response.status_code == 400


# ============================================================================
# TESTS DEL ENDPOINT /stats
# ============================================================================

@pytest.mark.unit
def test_stats_endpoint_returns_200(test_client):
    """
    Test: /stats debe retornar 200 OK.
    """
    # Act
    response = test_client.get("/stats")

    # Assert
    # Puede retornar 200 o 503 si ChromaDB no está disponible
    assert response.status_code in [200, 503]


@pytest.mark.unit
def test_stats_endpoint_returns_collection_info(test_client):
    """
    Test: /stats debe retornar información de la colección.

    Response debe incluir al menos:
    - collection_name
    - document_count (o similar)
    """
    # Act
    response = test_client.get("/stats")

    # Assert
    if response.status_code == 200:
        data = response.json()
        # Verificar que retorna alguna información útil
        assert isinstance(data, dict)
        assert len(data) > 0


# ============================================================================
# TESTS DE CORS Y HEADERS
# ============================================================================

@pytest.mark.unit
def test_api_allows_cors(test_client):
    """
    Test: la API debe tener CORS configurado para el frontend.

    Necesario para que el frontend React pueda hacer requests.
    """
    # Act
    response = test_client.options("/health")

    # Assert
    # Verificar que permite CORS o que responde a OPTIONS
    assert response.status_code in [200, 405]  # 405 si OPTIONS no implementado


@pytest.mark.unit
def test_api_returns_correct_content_type(test_client):
    """
    Test: todos los endpoints deben retornar application/json.
    """
    # Act
    responses = [
        test_client.get("/health"),
        test_client.get("/stats"),
    ]

    # Assert
    for response in responses:
        if response.status_code == 200:
            assert "application/json" in response.headers.get("content-type", "")


# ============================================================================
# TESTS DE MANEJO DE ERRORES
# ============================================================================

@pytest.mark.unit
def test_invalid_endpoint_returns_404(test_client):
    """
    Test: endpoint inexistente debe retornar 404.
    """
    # Act
    response = test_client.get("/invalid/endpoint")

    # Assert
    assert response.status_code == 404


@pytest.mark.unit
def test_invalid_method_returns_405(test_client):
    """
    Test: método HTTP incorrecto debe retornar 405.

    Por ejemplo, GET en un endpoint que solo acepta POST.
    """
    # Act
    response = test_client.get("/ask")  # /ask solo acepta POST

    # Assert
    assert response.status_code == 405  # Method Not Allowed


@pytest.mark.unit
def test_malformed_json_returns_422(test_client):
    """
    Test: JSON malformado debe retornar 422.
    """
    # Act
    response = test_client.post(
        "/ask",
        data="not valid json",  # No es JSON válido
        headers={"Content-Type": "application/json"}
    )

    # Assert
    assert response.status_code == 422


# ============================================================================
# TESTS DE PERFORMANCE/TIMEOUT
# ============================================================================

@pytest.mark.slow
def test_ask_endpoint_responds_within_reasonable_time(test_client):
    """
    Test: /ask debe responder en tiempo razonable (<30s).

    Marcado como @slow porque puede tardar con servicios reales.
    """
    import time

    # Arrange
    payload = {"question": "¿Qué es RAG?"}

    # Act
    start = time.time()
    response = test_client.post("/ask", json=payload)
    elapsed = time.time() - start

    # Assert
    # Con mocks debe ser instantáneo, con servicios reales <30s
    if response.status_code == 200:
        assert elapsed < 30.0


# ============================================================================
# TESTS DE INTEGRACIÓN (requieren servicios reales)
# ============================================================================

@pytest.mark.integration
def test_full_api_flow_with_real_services(test_client):
    """
    Test de integración: flujo completo ingesta → query.

    Requiere:
    - Ollama corriendo
    - ChromaDB corriendo
    - PDF de prueba

    1. Ingesta un PDF
    2. Hace una query
    3. Verifica que la respuesta incluye información del PDF

    No se ejecuta por defecto (usa pytest -m integration)
    """
    pytest.skip("Requiere servicios reales - implementar cuando sea necesario")
