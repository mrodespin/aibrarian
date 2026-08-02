# 🧪 Guía de Testing - Bibliotecario-IA

Documentación completa de la suite de tests del backend.

## 📂 Estructura

```
api/tests/
├── conftest.py                     # Fixtures compartidas (mocks, test data)
├── test_rag_service.py             # Tests del servicio RAG
├── test_sync_service.py            # Tests del pipeline de ingesta
├── test_api.py                     # Tests de endpoints FastAPI
├── test_auth_service.py            # Tests de AuthService (login, JWT)
├── test_auth_endpoints.py          # Tests de /auth/* y protección de endpoints
├── test_notion_service.py          # Tests del adaptador/endpoints de Notion
├── test_groq_adapter.py            # Tests del adaptador Groq (LLMPort cloud)
├── test_chromadb_cloud_adapter.py  # Tests del adaptador Chroma Cloud (VectorDBPort cloud)
└── test_integration.py             # Tests E2E con servicios reales (Ollama + ChromaDB)
```

**Total:** 90 tests unitarios (`pytest -m unit`, lo que corre CI) + tests de integración marcados aparte (necesitan Ollama/ChromaDB reales)

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

| Fichero | Qué testea |
|---------|------------|
| `test_rag_service.py` | RAGService: query feliz, embeddings, vector search, generación, validación, límite de contexto, errores de Ollama/ChromaDB, edge cases |
| `test_sync_service.py` | SyncService: ingesta completa, validación de paths, errores de processor/embedding/ChromaDB, chunking |
| `test_api.py` | Endpoints FastAPI (con `test_client` ya autenticado, ver conftest.py): validación de requests, códigos de error HTTP, CORS |
| `test_auth_service.py` | AuthService: login correcto/incorrecto, propagación de errores del repositorio (no se confunden con credenciales inválidas), emisión/validación de JWT, token expirado, token con secreto distinto |
| `test_auth_endpoints.py` | `/auth/login`, `/auth/logout`, `/auth/me`, y que endpoints protegidos devuelvan 401 sin sesión / no-401 con `dependency_overrides` |
| `test_notion_service.py` | Adaptador de Notion + endpoints `/sync/notion*` |
| `test_groq_adapter.py` | Adaptador Groq (LLMPort cloud): generación, extracción de keywords, embeddings locales (ONNX/sentence-transformers) |
| `test_chromadb_cloud_adapter.py` | Adaptador Chroma Cloud (VectorDBPort cloud): validación de credenciales, caché de cliente |
| `test_integration.py` | E2E con Ollama + ChromaDB reales: pipeline completo, conectividad |

Conteo exacto y actualizado: `pytest --collect-only -q` (90 tests unitarios a fecha de este documento, ver badge del [README](../README.md)).

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
- `mock_user_repository`: Mock de UserRepositoryPort (un usuario de prueba: `test@example.com` / `testpass123`)

**Servicios con mocks:**
- `rag_service_with_mocks`: RAGService listo para tests
- `sync_service_with_mocks`: SyncService listo para tests
- `auth_service_with_mocks`: AuthService listo para tests

**Cliente API:**
- `test_client`: TestClient de FastAPI, **ya autenticado** (override de `get_current_user` con un usuario de prueba) — pensado para tests que verifican lógica de negocio, no el login en sí. Los tests que sí prueban autenticación (`test_auth_endpoints.py`) usan su propio fixture `client`, sin este override.

**Datos de prueba:**
- `sample_document`: Document de ejemplo
- `sample_chunks`: Lista de Chunks
- `sample_query`: Query de ejemplo
- `sample_query_response`: QueryResponse de ejemplo

> `JWT_SECRET_KEY` se fija a un valor de test (`os.environ.setdefault(...)`) al principio de `conftest.py`, antes de importar `app.main` — necesario porque `Settings()` se instancia en el import y los tests de auth necesitan un secreto real para firmar/verificar tokens.

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
curl http://localhost:8001/api/v2/heartbeat

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

- [x] `pytest-cov`: Coverage reports (ya en `requirements.txt`)
- [ ] `pytest-xdist`: Tests en paralelo (`pytest -n auto`)
- [ ] `pytest-benchmark`: Performance benchmarks
- [ ] `pytest-html`: Reportes HTML bonitos

---

**Cobertura actual:** 90 tests unitarios, 62% de cobertura (concentrada en los *services*, mockeados — los adapters que hablan con servicios reales están peor cubiertos, ver [README](../README.md#-trabajo-futuro))
**Tiempo ejecución:** ~7-12s (unitarios, según máquina), variable en integración (dependen de Ollama/ChromaDB reales)
