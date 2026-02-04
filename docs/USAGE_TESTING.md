# 🧪 Guía de Testing - Bibliotecario-IA

Documentación completa de la suite de tests del backend.

## 📂 Estructura

```
api/tests/
├── conftest.py            # Fixtures compartidas (mocks, test data)
├── test_rag_service.py    # Tests del servicio RAG (20+ tests)
├── test_sync_service.py   # Tests del pipeline de ingesta (15+ tests)
├── test_api.py            # Tests de endpoints FastAPI (25+ tests)
└── test_integration.py    # Tests E2E con servicios reales (4 tests)
```

**Total:** 60+ tests unitarios + 4 tests de integración

## 🚀 Quick Start

```bash
# 1. Activar venv
cd api
source venv/bin/activate

# 2. Instalar pytest (ya incluido en requirements.txt)
pip install -r requirements.txt

# 3. Ejecutar todos los tests
pytest

# 4. Ver tests en modo verbose
pytest -v
```

## 📝 Tipos de Tests

### 🔷 Tests Unitarios (`@pytest.mark.unit`)

Tests **rápidos** con mocks, sin dependencias externas.

```bash
# Ejecutar solo tests unitarios
pytest -m unit

# Tiempo: ~1-2 segundos total
```

**Qué testean:**
- Lógica de negocio (RAGService, SyncService)
- Validación de inputs
- Manejo de errores
- Edge cases (queries vacías, documentos grandes, etc.)
- Endpoints HTTP (con mocks)

### 🔶 Tests de Integración (`@pytest.mark.integration`)

Tests con **servicios reales** (Ollama + ChromaDB).

**Prerequisitos:**
```bash
# Terminal 1: Ollama
ollama serve

# Terminal 2: ChromaDB
docker-compose up chromadb
```

**Ejecución:**
```bash
pytest -m integration

# Tiempo: ~10-30 segundos
```

**Qué testean:**
- Conectividad real con Ollama
- Conectividad real con ChromaDB
- Flujo E2E: ingesta → storage → query → respuesta

## 🎯 Comandos Útiles

### Ejecución Básica

```bash
# Todos los tests
pytest

# Solo tests unitarios (rápidos)
pytest -m unit

# Solo tests de integración
pytest -m integration

# Solo un archivo específico
pytest tests/test_rag_service.py

# Solo una función
pytest tests/test_rag_service.py::test_query_success
```

### Filtrado

```bash
# Tests que contengan "query" en el nombre
pytest -k "query"

# Excluir tests lentos
pytest -m "not slow"

# Excluir integración (solo unitarios)
pytest -m "not integration"

# Tests E2E únicamente
pytest -m e2e
```

### Debugging

```bash
# Ver prints/logs durante ejecución
pytest -s

# Verbose + mostrar variables locales en failures
pytest -vv --showlocals

# Parar en el primer fallo
pytest -x

# Ejecutar solo los últimos tests que fallaron
pytest --lf

# Entrar en debugger Python al fallar
pytest --pdb
```

### Cobertura

```bash
# Generar reporte de cobertura
pytest --cov=app tests/

# Cobertura con reporte HTML
pytest --cov=app --cov-report=html tests/
# Ver en: htmlcov/index.html
```

## 📊 Cobertura de Tests

### test_rag_service.py - RAGService

| Funcionalidad | Tests | Descripción |
|---------------|-------|-------------|
| Query básica | ✅ 3 tests | Query exitosa, respuesta con sources |
| Embeddings | ✅ 1 test | Generación de embedding de query |
| Vector search | ✅ 1 test | Búsqueda en ChromaDB |
| LLM generation | ✅ 1 test | Generación de respuesta |
| Validación | ✅ 2 tests | Query vacía, query None |
| Sin resultados | ✅ 1 test | BD sin chunks relevantes |
| Límite contexto | ✅ 1 test | max_chunks respetado |
| Metadata | ✅ 1 test | Sources con metadata |
| Errores | ✅ 2 tests | Error Ollama, error ChromaDB |
| Edge cases | ✅ 3 tests | Query larga, caracteres especiales |

**Total:** 16+ tests

### test_sync_service.py - SyncService

| Funcionalidad | Tests | Descripción |
|---------------|-------|-------------|
| Ingesta básica | ✅ 4 tests | Flujo completo, chunks, embeddings |
| Validación | ✅ 3 tests | Path vacío, None, inexistente |
| Errores | ✅ 3 tests | Processor, embedding, ChromaDB |
| Edge cases | ✅ 3 tests | Doc vacío, muy largo, caracteres especiales |
| Chunking | ✅ 1 test | Configuración CHUNK_SIZE |

**Total:** 14+ tests

### test_api.py - Endpoints FastAPI

| Endpoint | Tests | Descripción |
|----------|-------|-------------|
| GET /health | ✅ 2 tests | Status 200, JSON response |
| POST /ask | ✅ 5 tests | Accept POST, validación, response |
| POST /sync | ✅ 3 tests | Accept POST, validación |
| POST /sync/directory | ✅ 2 tests | Accept POST, default path |
| POST /sync/notion | ✅ 2 tests | Validación page_id, database_id |
| GET /stats | ✅ 2 tests | Status 200, collection info |
| CORS/Headers | ✅ 2 tests | CORS, Content-Type |
| Errores HTTP | ✅ 3 tests | 404, 405, 422 |
| Performance | ✅ 1 test | Timeout razonable |

**Total:** 22+ tests

### test_integration.py - Tests E2E

| Test | Descripción |
|------|-------------|
| `test_full_rag_pipeline` | Flujo completo: ingest PDF → query → verify |
| `test_rag_with_empty_database` | Manejo de BD vacía |
| `test_ollama_connectivity` | Pre-check Ollama |
| `test_chromadb_connectivity` | Pre-check ChromaDB |

**Total:** 4 tests E2E

## 🔧 Configuración

### pytest.ini

Ubicación: `/api/pytest.ini`

**Marcadores personalizados:**
- `@pytest.mark.unit`: Tests unitarios (rápidos)
- `@pytest.mark.integration`: Tests con servicios reales
- `@pytest.mark.slow`: Tests lentos (>1s)
- `@pytest.mark.e2e`: Tests end-to-end

**Configuración:**
```ini
[pytest]
testpaths = tests
python_files = test_*.py
addopts = -v --tb=short --strict-markers
```

### conftest.py

Fixtures compartidas automáticamente disponibles:

**Mocks:**
- `mock_ollama`: Mock del adaptador Ollama
- `mock_chromadb`: Mock de ChromaDB
- `mock_pdf_processor`: Mock del procesador PDF

**Servicios con mocks:**
- `rag_service_with_mocks`: RAGService listo para tests
- `sync_service_with_mocks`: SyncService listo para tests

**Cliente API:**
- `test_client`: TestClient de FastAPI

**Datos de prueba:**
- `sample_document`: Document de ejemplo
- `sample_chunks`: Lista de Chunks
- `sample_query`: Query de ejemplo
- `sample_query_response`: QueryResponse de ejemplo

## 🐛 Debugging Tests

### Test falla con "AssertionError"

```bash
# Ver traceback completo + variables locales
pytest -vv --showlocals tests/test_rag_service.py::test_query_success

# Añadir prints para debugging
pytest -s tests/test_rag_service.py::test_query_success
```

### Tests de integración fallan

**Error: "Ollama connection failed"**
```bash
# Verificar Ollama
curl http://localhost:11434/api/tags

# Si no responde, iniciarlo
ollama serve
```

**Error: "ChromaDB connection failed"**
```bash
# Verificar ChromaDB
curl http://localhost:8001/api/v1/heartbeat

# Si no responde, iniciarlo
docker-compose up -d chromadb
```

**Error: "test_document.pdf not found"**
```bash
# Generar PDF de prueba
python scripts/generate_test_pdf.py

# Verificar
ls -la data/test_document.pdf
```

### ImportError o ModuleNotFoundError

```bash
# Asegurarte de estar en el venv
source venv/bin/activate

# Reinstalar dependencias
pip install -r requirements.txt
```

## ✅ CI/CD Integration

Ejemplo para GitHub Actions:

```yaml
# .github/workflows/test.yml
name: Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest

    steps:
      - uses: actions/checkout@v3

      - name: Set up Python 3.11
        uses: actions/setup-python@v4
        with:
          python-version: '3.11'

      - name: Install dependencies
        run: |
          cd api
          pip install -r requirements.txt

      - name: Run unit tests
        run: |
          cd api
          pytest -m unit -v

      # Tests de integración requieren servicios
      # (configurar Ollama/ChromaDB en CI si necesario)
```

## 📈 Próximos Pasos

### Expandir Cobertura

- [ ] Tests de adaptadores (ChromaDB, Ollama, PDF)
- [ ] Tests de models (Document, Chunk, etc.)
- [ ] Tests de configuración (settings.py)
- [ ] Tests de errores específicos de LangChain

### Mejorar Tests de Integración

- [ ] Test con múltiples PDFs
- [ ] Test con Notion real
- [ ] Test de performance (queries por segundo)
- [ ] Test de carga (muchos documentos)

### Herramientas Adicionales

- [ ] `pytest-cov`: Coverage reports
- [ ] `pytest-xdist`: Tests en paralelo (`pytest -n auto`)
- [ ] `pytest-benchmark`: Performance benchmarks
- [ ] `pytest-html`: Reportes HTML bonitos


---

**Cobertura actual:** 60+ tests
**Tiempo ejecución:** ~2s (unitarios), ~30s (integración)
