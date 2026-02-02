# /api/tests/__init__.py
"""
Test Suite para Bibliotecario-IA API

Estructura de tests:
- test_rag_service.py: Tests del servicio RAG (queries)
- test_sync_service.py: Tests del pipeline de ingesta
- test_api.py: Tests de endpoints FastAPI
- test_integration.py: Tests E2E del flujo completo
- conftest.py: Fixtures compartidas

Ejecución:
    cd api
    source venv/bin/activate
    pytest                          # Todos los tests
    pytest tests/test_rag_service.py    # Tests específicos
    pytest -m unit                  # Solo tests unitarios
    pytest -m integration           # Solo tests de integración
    pytest -v                       # Modo verbose
    pytest -k "test_query"          # Tests que contengan "query"
"""
