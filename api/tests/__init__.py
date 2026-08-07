# /api/tests/__init__.py
"""
Test Suite for the Bibliotecario-IA API

Test structure:
- test_rag_service.py: RAG service tests (queries)
- test_sync_service.py: Ingestion pipeline tests
- test_api.py: FastAPI endpoint tests
- test_integration.py: E2E tests of the full flow
- conftest.py: Shared fixtures

Running:
    cd api
    source venv/bin/activate
    pytest                          # All tests
    pytest tests/test_rag_service.py    # Specific tests
    pytest -m unit                  # Unit tests only
    pytest -m integration           # Integration tests only
    pytest -v                       # Verbose mode
    pytest -k "test_query"          # Tests matching "query"
"""
