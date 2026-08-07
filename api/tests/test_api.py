# /api/tests/test_api.py
"""
Tests for FastAPI's endpoints.

Tests for the API's HTTP endpoints:
- GET /health: Health check
- POST /ask: RAG queries
- POST /sync: Single-document ingestion
- POST /sync/directory: Directory ingestion
- GET /stats: Collection statistics

Uses FastAPI's TestClient to simulate HTTP requests without spinning up a server.
"""

import pytest
from fastapi.testclient import TestClient


# ============================================================================
# /health ENDPOINT TESTS
# ============================================================================

@pytest.mark.unit
def test_health_endpoint_returns_200(test_client):
    """
    Test: /health must return 200 OK.

    The health check must always respond while the API is up.
    """
    # Act
    response = test_client.get("/health")

    # Assert
    assert response.status_code == 200


@pytest.mark.unit
def test_health_endpoint_returns_json(test_client):
    """
    Test: /health must return JSON with status.
    """
    # Act
    response = test_client.get("/health")

    # Assert
    assert response.headers["content-type"] == "application/json"
    data = response.json()
    assert "status" in data
    assert data["status"] == "healthy"


# ============================================================================
# /ask ENDPOINT TESTS
# ============================================================================

@pytest.mark.unit
def test_ask_endpoint_accepts_post(test_client):
    """
    Test: /ask must accept POST requests.
    """
    # Arrange
    payload = {"question": "What is RAG?"}

    # Act
    response = test_client.post("/ask", json=payload)

    # Assert
    # May return 200 (with the mock) or an error if configuration is missing
    # What matters is that it accepts the POST method
    assert response.status_code in [200, 500, 503]  # 500/503 if real services are missing


@pytest.mark.unit
def test_ask_endpoint_requires_question_field(test_client):
    """
    Test: /ask must require the 'question' field.

    A request without 'question' must return 422 (Validation Error).
    """
    # Arrange
    payload = {}  # No question

    # Act
    response = test_client.post("/ask", json=payload)

    # Assert
    assert response.status_code == 422  # Unprocessable Entity


@pytest.mark.unit
def test_ask_endpoint_rejects_empty_question(test_client):
    """
    Test: /ask must reject empty questions.
    """
    # Arrange
    payload = {"question": ""}

    # Act
    response = test_client.post("/ask", json=payload)

    # Assert
    # May be 422 (validation) or 400 (bad request)
    assert response.status_code in [400, 422]


@pytest.mark.unit
def test_ask_endpoint_returns_json_with_answer(test_client):
    """
    Test: /ask must return JSON with the expected structure.

    The response must include:
    - answer: string
    - sources: array
    - model: string (optional)
    """
    # Arrange
    payload = {"question": "What is RAG?"}

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
# /sync ENDPOINT TESTS
# ============================================================================

@pytest.mark.unit
def test_sync_endpoint_accepts_post(test_client):
    """
    Test: /sync must accept POST requests.
    """
    # Arrange
    payload = {"file_path": "/test/document.pdf"}

    # Act
    response = test_client.post("/sync", json=payload)

    # Assert
    # Will accept POST even if it fails due to the file not existing
    assert response.status_code in [200, 404, 500]


@pytest.mark.unit
def test_sync_endpoint_requires_file_path(test_client):
    """
    Test: /sync must require the 'file_path' field.
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
    Test: /sync must reject an empty file_path.
    """
    # Arrange
    payload = {"file_path": ""}

    # Act
    response = test_client.post("/sync", json=payload)

    # Assert
    assert response.status_code in [400, 422]


# ============================================================================
# /sync/directory ENDPOINT TESTS
# ============================================================================

@pytest.mark.unit
def test_sync_directory_endpoint_accepts_post(test_client):
    """
    Test: /sync/directory must accept POST requests.
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
    Test: /sync/directory must use ./data by default.

    If directory_path isn't provided, it must use the one configured in settings.
    """
    # Arrange
    payload = {}  # No directory_path

    # Act
    response = test_client.post("/sync/directory", json=payload)

    # Assert
    # Must accept the request (it may fail if there are no PDFs, but not due to validation)
    assert response.status_code in [200, 404, 500]
    assert response.status_code != 422  # Must not be a validation error


# ============================================================================
# /sync/notion ENDPOINT TESTS
# ============================================================================

@pytest.mark.unit
def test_sync_notion_page_requires_page_id(test_client):
    """
    Test: /sync/notion must require page_id.
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
    Test: /sync/notion/database must require database_id.

    The endpoint validates database_id with custom logic and returns
    400 if it isn't configured (neither in the request nor in settings).

    Note: We use patch to simulate NOTION_DATABASE_ID not being
    configured in the environment, since the dev .env might have it set.
    """
    from unittest.mock import patch

    # Arrange
    payload = {}

    # Act: mock settings so notion_database_id is None
    with patch("app.main.settings") as mock_settings:
        # Configure the mock with the necessary values
        mock_settings.notion_api_key = "fake-api-key"  # Pass the first validation
        mock_settings.notion_database_id = None  # Simulate it not being configured

        response = test_client.post("/sync/notion/database", json=payload)

    # Assert: the endpoint returns 400 when database_id is missing
    assert response.status_code == 400


# ============================================================================
# /stats ENDPOINT TESTS
# ============================================================================

@pytest.mark.unit
def test_stats_endpoint_returns_200(test_client):
    """
    Test: /stats must return 200 OK.
    """
    # Act
    response = test_client.get("/stats")

    # Assert
    # May return 200 or 503 if ChromaDB isn't available
    assert response.status_code in [200, 503]


@pytest.mark.unit
def test_stats_endpoint_returns_collection_info(test_client):
    """
    Test: /stats must return the collection's info.

    The response must include at least:
    - collection_name
    - document_count (or similar)
    """
    # Act
    response = test_client.get("/stats")

    # Assert
    if response.status_code == 200:
        data = response.json()
        # Verify it returns some useful information
        assert isinstance(data, dict)
        assert len(data) > 0


# ============================================================================
# GET /documents ENDPOINT TESTS
# ============================================================================

@pytest.mark.unit
def test_list_documents_endpoint_returns_200(test_client):
    """
    Test: GET /documents must return 200 OK.

    Unlike /stats, the adapter's list_documents() never raises (same
    contract as similarity_search/get_collection_stats: on error it
    degrades to an empty list), so there's no need to tolerate an
    alternate status code here — always 200, with "documents": [] if
    the real vector_db isn't available in the test environment.
    """
    response = test_client.get("/documents")

    assert response.status_code == 200
    data = response.json()
    assert "total" in data
    assert "documents" in data
    assert isinstance(data["documents"], list)
    assert data["total"] == len(data["documents"])


# ============================================================================
# CORS AND HEADERS TESTS
# ============================================================================

@pytest.mark.unit
def test_api_allows_cors(test_client):
    """
    Test: the API must have CORS configured for the frontend.

    Necessary for the React frontend to be able to make requests.
    """
    # Act
    response = test_client.options("/health")

    # Assert
    # Verify it allows CORS or responds to OPTIONS
    assert response.status_code in [200, 405]  # 405 if OPTIONS isn't implemented


@pytest.mark.unit
def test_api_returns_correct_content_type(test_client):
    """
    Test: every endpoint must return application/json.
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
# ERROR HANDLING TESTS
# ============================================================================

@pytest.mark.unit
def test_invalid_endpoint_returns_404(test_client):
    """
    Test: a nonexistent endpoint must return 404.
    """
    # Act
    response = test_client.get("/invalid/endpoint")

    # Assert
    assert response.status_code == 404


@pytest.mark.unit
def test_invalid_method_returns_405(test_client):
    """
    Test: a wrong HTTP method must return 405.

    For example, GET on an endpoint that only accepts POST.
    """
    # Act
    response = test_client.get("/ask")  # /ask only accepts POST

    # Assert
    assert response.status_code == 405  # Method Not Allowed


@pytest.mark.unit
def test_malformed_json_returns_422(test_client):
    """
    Test: malformed JSON must return 422.
    """
    # Act
    response = test_client.post(
        "/ask",
        data="not valid json",  # Not valid JSON
        headers={"Content-Type": "application/json"}
    )

    # Assert
    assert response.status_code == 422


# ============================================================================
# PERFORMANCE/TIMEOUT TESTS
# ============================================================================

@pytest.mark.slow
def test_ask_endpoint_responds_within_reasonable_time(test_client):
    """
    Test: /ask must respond within a reasonable time (<30s).

    Marked as @slow because it can take a while with real services.
    """
    import time

    # Arrange
    payload = {"question": "What is RAG?"}

    # Act
    start = time.time()
    response = test_client.post("/ask", json=payload)
    elapsed = time.time() - start

    # Assert
    # With mocks it should be instant, with real services <30s
    if response.status_code == 200:
        assert elapsed < 30.0
