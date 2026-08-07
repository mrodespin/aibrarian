# 🧪 Testing Guide - AIbrarian

Full documentation of the backend test suite.

## 📂 Structure

```
api/tests/
├── conftest.py                     # Shared fixtures (mocks, test data)
├── test_rag_service.py             # RAGService tests
├── test_sync_service.py            # Ingestion pipeline tests
├── test_api.py                     # FastAPI endpoint tests
├── test_auth_service.py            # AuthService tests (login, JWT)
├── test_auth_endpoints.py          # /auth/* and endpoint-protection tests
├── test_notion_service.py          # Notion adapter/endpoint tests
├── test_groq_adapter.py            # Groq adapter tests (cloud LLMPort)
├── test_chromadb_cloud_adapter.py  # Chroma Cloud adapter tests (cloud VectorDBPort)
└── test_integration.py             # E2E tests with real services (Ollama + ChromaDB)
```

**Total:** 142 unit tests (`pytest -m unit`, what CI runs) + integration tests marked separately (need real Ollama/ChromaDB)

## 🚀 Quick Start

```bash
# 1. Activate the venv
cd api
source venv/bin/activate

# 2. Install pytest (already in requirements.txt)
pip install -r requirements.txt

# 3. Run all tests
pytest

# 4. Verbose mode
pytest -v
```

## 📝 Test Types

### 🔷 Unit Tests (`@pytest.mark.unit`)

**Fast** tests with mocks, no external dependencies.

```bash
# Run only unit tests
pytest -m unit

# Time: ~10-15 seconds total
```

**What they cover:**
- Business logic (RAGService, SyncService)
- Input validation
- Error handling
- Edge cases (empty queries, large documents, etc.)
- HTTP endpoints (mocked)

### 🔶 Integration Tests (`@pytest.mark.integration`)

Tests against **real services** (Ollama + ChromaDB).

**Prerequisites:**
```bash
# Terminal 1: Ollama
ollama serve

# Terminal 2: ChromaDB
docker-compose up chromadb
```

**Running:**
```bash
pytest -m integration

# Time: ~10-30 seconds
```

**What they cover:**
- Real connectivity to Ollama
- Real connectivity to ChromaDB
- E2E flow: ingestion → storage → query → response

## 🎯 Useful Commands

### Basic Execution

```bash
# All tests
pytest

# Only unit tests (fast)
pytest -m unit

# Only integration tests
pytest -m integration

# A single file
pytest tests/test_rag_service.py

# A single test function
pytest tests/test_rag_service.py::test_query_success
```

### Filtering

```bash
# Tests with "query" in the name
pytest -k "query"

# Skip slow tests
pytest -m "not slow"

# Skip integration (unit only)
pytest -m "not integration"

# E2E tests only
pytest -m e2e
```

### Debugging

```bash
# Show prints/logs during the run
pytest -s

# Verbose + show local variables on failures
pytest -vv --showlocals

# Stop at the first failure
pytest -x

# Re-run only the last failed tests
pytest --lf

# Drop into the Python debugger on failure
pytest --pdb
```

### Coverage

```bash
# Generate a coverage report
pytest --cov=app tests/

# Coverage with an HTML report
pytest --cov=app --cov-report=html tests/
# View at: htmlcov/index.html
```

## 📊 Test Coverage

| File | What it tests |
|---------|------------|
| `test_rag_service.py` | RAGService: happy-path query, embeddings, vector search, generation, validation, context limit, Ollama/ChromaDB errors, edge cases |
| `test_sync_service.py` | SyncService: full ingestion, path validation, processor/embedding/ChromaDB errors, chunking |
| `test_api.py` | FastAPI endpoints (using an already-authenticated `test_client`, see conftest.py): request validation, HTTP error codes, CORS |
| `test_auth_service.py` | AuthService: correct/incorrect login, repository-error propagation (not confused with invalid credentials), JWT issuance/validation, expired token, token signed with a different secret |
| `test_auth_endpoints.py` | `/auth/login`, `/auth/logout`, `/auth/me`, and that protected endpoints return 401 with no session / non-401 with `dependency_overrides` |
| `test_notion_service.py` | Notion adapter + `/sync/notion*` endpoints |
| `test_groq_adapter.py` | Groq adapter (cloud LLMPort): generation, keyword extraction, local embeddings (ONNX/sentence-transformers) |
| `test_chromadb_cloud_adapter.py` | Chroma Cloud adapter (cloud VectorDBPort): credential validation, client caching |
| `test_integration.py` | E2E with real Ollama + ChromaDB: full pipeline, connectivity |

Exact, up-to-date count: `pytest --collect-only -q` (142 unit tests as of this document, see the [README](../README.md) badge).

## 🔧 Configuration

### pytest.ini

Location: `/api/pytest.ini`

**Custom markers:**
- `@pytest.mark.unit`: unit tests (fast)
- `@pytest.mark.integration`: tests against real services
- `@pytest.mark.slow`: slow tests (>1s)
- `@pytest.mark.e2e`: end-to-end tests

**Configuration:**
```ini
[pytest]
testpaths = tests
python_files = test_*.py
addopts = -v --tb=short --strict-markers
```

### conftest.py

Shared fixtures automatically available:

**Mocks:**
- `mock_ollama`: mock of the Ollama adapter
- `mock_chromadb`: mock of ChromaDB
- `mock_pdf_processor`: mock of the PDF processor
- `mock_user_repository`: mock of UserRepositoryPort (one test user: `test@example.com` / `testpass123`)

**Services with mocks:**
- `rag_service_with_mocks`: RAGService ready for tests
- `sync_service_with_mocks`: SyncService ready for tests
- `auth_service_with_mocks`: AuthService ready for tests

**API client:**
- `test_client`: FastAPI `TestClient`, **already authenticated** (overrides `get_current_user` with a test user) — meant for tests that check business logic, not login itself. Tests that actually exercise authentication (`test_auth_endpoints.py`) use their own `client` fixture, without this override.

**Test data:**
- `sample_document`: a sample Document
- `sample_chunks`: a list of Chunks
- `sample_query`: a sample Query
- `sample_query_response`: a sample QueryResponse

> `JWT_SECRET_KEY` is pinned to a test value (`os.environ.setdefault(...)`) at the top of `conftest.py`, before `app.main` is imported — needed because `Settings()` is instantiated at import time and the auth tests need a real secret to sign/verify tokens.

## 🐛 Debugging Tests

### Test fails with "AssertionError"

```bash
# Full traceback + local variables
pytest -vv --showlocals tests/test_rag_service.py::test_query_success

# Add prints for debugging
pytest -s tests/test_rag_service.py::test_query_success
```

### Integration tests fail

**Error: "Ollama connection failed"**
```bash
# Check Ollama
curl http://localhost:11434/api/tags

# If it doesn't respond, start it
ollama serve
```

**Error: "ChromaDB connection failed"**
```bash
# Check ChromaDB
curl http://localhost:8001/api/v2/heartbeat

# If it doesn't respond, start it
docker-compose up -d chromadb
```

**Error: "test_document.pdf not found"**
```bash
# Generate the test PDF
python scripts/generate_test_pdf.py

# Verify
ls -la data/test_document.pdf
```

### ImportError or ModuleNotFoundError

```bash
# Make sure you're in the venv
source venv/bin/activate

# Reinstall dependencies
pip install -r requirements.txt
```

## ✅ CI/CD Integration

Example for GitHub Actions:

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

      # Integration tests need real services running
      # (set up Ollama/ChromaDB in CI if needed)
```

## 📈 Next Steps

### Expand Coverage

- [ ] Adapter tests (ChromaDB, Ollama, PDF)
- [ ] Model tests (Document, Chunk, etc.)
- [ ] Configuration tests (settings.py)
- [ ] LangChain-specific error tests

### Improve Integration Tests

- [ ] Test with multiple PDFs
- [ ] Test against real Notion
- [ ] Performance test (queries per second)
- [ ] Load test (many documents)

### Additional Tooling

- [x] `pytest-cov`: coverage reports (already in `requirements.txt`)
- [ ] `pytest-xdist`: parallel tests (`pytest -n auto`)
- [ ] `pytest-benchmark`: performance benchmarks
- [ ] `pytest-html`: nicer HTML reports

---

**Current coverage:** 142 unit tests, 68% coverage (concentrated in the *services*, which are mocked — the adapters that talk to real services are less well covered, see [README](../README.md#-trabajo-futuro))
**Run time:** ~10-15s (unit, machine-dependent), variable for integration (depends on real Ollama/ChromaDB)
