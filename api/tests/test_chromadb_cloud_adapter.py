# /api/tests/test_chromadb_cloud_adapter.py
"""
Tests de ChromaCloudAdapter - Ver ADR-007.

ChromaCloudAdapter hereda toda su lógica de negocio (store_chunks,
similarity_search, delete_document, ...) de ChromaDBAdapter sin cambios;
esa lógica ya se ejerce indirectamente vía mock_chromadb en
test_rag_service.py / test_sync_service.py. Aquí solo se prueba lo que
este adaptador SÍ cambia: cómo obtiene el cliente de conexión.
"""

import pytest
from unittest.mock import MagicMock, patch

from app.adapters.outbound.chromadb_cloud_adapter import ChromaCloudAdapter
from app.adapters.outbound.chromadb_adapter import ChromaDBAdapter


@pytest.mark.unit
def test_is_subclass_of_chromadb_adapter():
    """Confirma que hereda (y por tanto reutiliza) toda la lógica de VectorDBPort."""
    assert issubclass(ChromaCloudAdapter, ChromaDBAdapter)


@pytest.mark.unit
def test_get_client_requires_api_key(monkeypatch):
    monkeypatch.setattr("app.adapters.outbound.chromadb_cloud_adapter.settings.chroma_cloud_api_key", None)
    adapter = ChromaCloudAdapter()

    with pytest.raises(RuntimeError, match="CHROMA_CLOUD_API_KEY"):
        adapter._get_client()


@pytest.mark.unit
def test_get_client_requires_tenant_and_database(monkeypatch):
    monkeypatch.setattr("app.adapters.outbound.chromadb_cloud_adapter.settings.chroma_cloud_api_key", "test-key")
    monkeypatch.setattr("app.adapters.outbound.chromadb_cloud_adapter.settings.chroma_cloud_tenant", None)
    monkeypatch.setattr("app.adapters.outbound.chromadb_cloud_adapter.settings.chroma_cloud_database", None)
    adapter = ChromaCloudAdapter()

    with pytest.raises(RuntimeError, match="CHROMA_CLOUD_TENANT, CHROMA_CLOUD_DATABASE"):
        adapter._get_client()


@pytest.mark.unit
def test_get_client_uses_cloud_client_with_settings(monkeypatch):
    monkeypatch.setattr("app.adapters.outbound.chromadb_cloud_adapter.settings.chroma_cloud_api_key", "test-key")
    monkeypatch.setattr("app.adapters.outbound.chromadb_cloud_adapter.settings.chroma_cloud_tenant", "my-tenant")
    monkeypatch.setattr("app.adapters.outbound.chromadb_cloud_adapter.settings.chroma_cloud_database", "my-db")

    adapter = ChromaCloudAdapter()
    fake_client = MagicMock()

    with patch(
        "app.adapters.outbound.chromadb_cloud_adapter.chromadb.CloudClient",
        return_value=fake_client,
    ) as mock_cloud_client:
        client = adapter._get_client()

    assert client is fake_client
    mock_cloud_client.assert_called_once()
    call_kwargs = mock_cloud_client.call_args.kwargs
    assert call_kwargs["tenant"] == "my-tenant"
    assert call_kwargs["database"] == "my-db"
    assert call_kwargs["api_key"] == "test-key"


@pytest.mark.unit
def test_get_client_is_cached(monkeypatch):
    """Segunda llamada no debe reconectar (mismo patrón lazy-singleton que ChromaDBAdapter)."""
    monkeypatch.setattr("app.adapters.outbound.chromadb_cloud_adapter.settings.chroma_cloud_api_key", "test-key")
    monkeypatch.setattr("app.adapters.outbound.chromadb_cloud_adapter.settings.chroma_cloud_tenant", "my-tenant")
    monkeypatch.setattr("app.adapters.outbound.chromadb_cloud_adapter.settings.chroma_cloud_database", "my-db")

    adapter = ChromaCloudAdapter()

    with patch(
        "app.adapters.outbound.chromadb_cloud_adapter.chromadb.CloudClient",
        return_value=MagicMock(),
    ) as mock_cloud_client:
        adapter._get_client()
        adapter._get_client()

    mock_cloud_client.assert_called_once()
