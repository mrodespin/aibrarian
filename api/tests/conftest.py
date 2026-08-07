# /api/tests/conftest.py
"""
Shared fixtures for all tests.

pytest automatically looks for fixtures in conftest.py and makes them
available to every test file with no need to import them.

Main fixtures:
- mock_ollama: Mock of the Ollama adapter (avoids real LLM calls)
- mock_chromadb: Mock of ChromaDB (avoids real vector DB calls)
- test_client: FastAPI client for API tests
- sample_document: Sample document for tests
"""

import os

# JWT_SECRET_KEY must exist BEFORE "from app.main import app": Settings()
# is instantiated when app.main is imported (via app.config.settings),
# and even though jwt_secret_key is Optional, the auth tests need a real
# value to sign/verify tokens. Set a test one here, before any other
# import triggers loading settings.
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-not-for-prod")

import bcrypt
import pytest
from datetime import datetime
from unittest.mock import Mock, AsyncMock, MagicMock
from fastapi.testclient import TestClient
from typing import List, Optional, Dict

from app.core.domain.models import Document, Chunk, QueryResult, SourceDocument, User, DocumentSummary
from app.main import app


# ============================================================================
# TEST DATA FIXTURES
# ============================================================================

@pytest.fixture
def sample_document() -> Document:
    """
    Sample document for tests.

    Returns:
        Document with sample content about RAG
    """
    return Document(
        content="RAG is Retrieval-Augmented Generation. It's a technique that combines "
                "information retrieval with text generation using LLMs. "
                "It first searches for relevant context and then generates an answer based on that context.",
        metadata={
            "source": "test_document.txt",
            "chunk_index": 0,
            "total_chunks": 1
        }
    )


@pytest.fixture
def sample_chunks() -> List[Chunk]:
    """
    List of sample chunks for RAG tests.

    Returns:
        A list of 3 chunks with RAG-related content
    """
    return [
        Chunk(
            content="RAG is Retrieval-Augmented Generation. It's a technique that combines search with LLMs.",
            metadata={"source": "doc1.pdf", "page": 1},
            embedding=[0.1, 0.2, 0.3]  # Simplified embedding
        ),
        Chunk(
            content="Embeddings are vector representations of text that capture semantic meaning.",
            metadata={"source": "doc2.pdf", "page": 2},
            embedding=[0.2, 0.3, 0.4]
        ),
        Chunk(
            content="ChromaDB is a vector database that enables similarity search.",
            metadata={"source": "doc3.pdf", "page": 1},
            embedding=[0.3, 0.4, 0.5]
        )
    ]


@pytest.fixture
def sample_query():
    """Sample query for tests."""
    from app.core.domain.models import Query
    return Query(question="What is RAG?")


@pytest.fixture
def sample_query_response() -> QueryResult:
    """
    Sample RAG response for tests.

    Returns:
        QueryResult with a simulated answer
    """
    return QueryResult(
        question="What is RAG?",
        answer="RAG (Retrieval-Augmented Generation) is a technique that combines "
               "relevant information retrieval with text generation using LLMs.",
        source_documents=[
            SourceDocument(
                document_id="doc1",
                chunk_content="RAG is Retrieval-Augmented...",
                metadata={"source": "doc1.pdf", "page": 1},
                relevance_score=0.95
            )
        ],
        processing_time=1.23
    )


# ============================================================================
# SERVICE MOCK FIXTURES
# ============================================================================

@pytest.fixture
def mock_ollama():
    """
    Mock of the Ollama adapter to avoid real LLM calls.

    Simulates:
    - generate_response(): Generates text responses
    - generate_embedding(): Generates embeddings

    Returns:
        A configured Mock of OllamaAdapter
    """
    mock = Mock()

    # Mock of generate_response (LLM answers)
    async def mock_generate_response(
        prompt: str,
        context: Optional[str] = None,
        history: Optional[str] = None,
        max_tokens: Optional[int] = None,
        temperature: float = 0.7,
        **kwargs
    ) -> str:
        if context:
            return f"Based on the provided context, {prompt[:50]}"
        return "This is a simulated LLM response for the prompt: " + prompt[:50]

    # Mock of stream_response (same answer as mock_generate_response, but
    # chunked word by word to simulate real streaming)
    async def mock_stream_response(
        prompt: str,
        context: Optional[str] = None,
        history: Optional[str] = None,
        max_tokens: Optional[int] = None,
        temperature: float = 0.7,
        **kwargs
    ):
        full_response = await mock_generate_response(prompt, context, history, max_tokens, temperature, **kwargs)
        for word in full_response.split(" "):
            yield word + " "

    # Mock of generate_embedding (vectorization)
    async def mock_embedding(text: str) -> List[float]:
        # Returns a simple embedding based on the text's hash
        # In production, Ollama returns 768-4096 dimension vectors
        return [float(hash(text) % 100) / 100.0 for _ in range(10)]

    # Mock of generate_embeddings_batch (batch vectorization)
    async def mock_embeddings_batch(texts: List[str]) -> List[List[float]]:
        # Returns one embedding per text
        return [await mock_embedding(text) for text in texts]

    # Mock of extract_keywords (Query Expansion)
    async def mock_extract_keywords(question: str) -> List[str]:
        # Extracts simple words from the question as keywords
        # In production, the LLM extracts entities and proper nouns
        words = question.replace("?", "").split()
        # Filter out short words and question words
        stopwords = {"what", "is", "how", "which", "who", "where", "for", "the", "a", "an", "of", "are"}
        keywords = [w for w in words if len(w) > 2 and w.lower() not in stopwords]
        return keywords[:3]  # Max 3 keywords

    mock.generate_response = AsyncMock(side_effect=mock_generate_response)
    mock.stream_response = mock_stream_response  # async generator, no AsyncMock wrapper
    mock.generate_embedding = AsyncMock(side_effect=mock_embedding)
    mock.generate_embeddings_batch = AsyncMock(side_effect=mock_embeddings_batch)
    mock.extract_keywords = AsyncMock(side_effect=mock_extract_keywords)
    # Default: no question is "a catalog question" — tests that want to
    # exercise that path override this explicitly
    # (mock_ollama.is_catalog_question = AsyncMock(return_value=True)),
    # see RAGService.ask_question / test_rag_service.py.
    mock.is_catalog_question = AsyncMock(return_value=False)
    # Default: nothing to condense — returns the question as-is.
    # Tests that want to check real condensing override this
    # (mock_ollama.condense_question = AsyncMock(return_value="..."))
    mock.condense_question = AsyncMock(side_effect=lambda question, history: question)

    return mock


@pytest.fixture
def mock_chromadb():
    """
    Mock of the ChromaDB adapter to avoid real vector DB calls.

    Simulates:
    - store_chunks(): Adds documents (does nothing in tests)
    - similarity_search(): Returns sample SourceDocuments
    - get_collection_stats(): Returns simulated statistics

    Returns:
        A configured Mock of ChromaDBAdapter
    """
    mock = Mock()

    # Mock of store_chunks
    async def mock_store(chunks: List[Chunk], collection_name: str = "documents") -> bool:
        return True  # Simulates a successful store

    # Mock of similarity_search (similarity search with Query Expansion)
    async def mock_similarity_search(
        query_embedding: List[float],
        collection_name: str = "documents",
        top_k: int = 4,
        filter_metadata: Optional[Dict] = None,
        keyword_filter: Optional[str] = None
    ) -> List[SourceDocument]:
        # Returns sample SourceDocuments regardless of the query
        # If there's a keyword_filter, simulates filtering (in tests it always returns results)
        return [
            SourceDocument(
                document_id="doc_001",
                chunk_content="RAG combines search with text generation.",
                metadata={"source": "test.pdf", "page": 1},
                relevance_score=0.95
            ),
            SourceDocument(
                document_id="doc_001",
                chunk_content="LLMs are large language models.",
                metadata={"source": "test.pdf", "page": 2},
                relevance_score=0.87
            )
        ][:top_k]  # Respect the top_k limit

    # Mock of get_collection_stats
    async def mock_stats(collection_name: str = "documents") -> dict:
        return {
            "count": 50,
            "dimensions": 768,
            "collection_name": collection_name
        }

    # Mock of list_documents (full catalog, doesn't go through similarity_search)
    async def mock_list_documents(collection_name: str = "documents") -> List[DocumentSummary]:
        return [
            DocumentSummary(document_id="doc_001", title="1984", source="notion", chunk_count=3),
            DocumentSummary(document_id="doc_002", title="Deep Learning", source="notion", chunk_count=4),
        ]

    mock.store_chunks = AsyncMock(side_effect=mock_store)
    mock.similarity_search = AsyncMock(side_effect=mock_similarity_search)
    mock.get_collection_stats = AsyncMock(side_effect=mock_stats)
    mock.list_documents = AsyncMock(side_effect=mock_list_documents)

    return mock


@pytest.fixture
def mock_pdf_processor():
    """
    Mock of the PDF processor.

    Simulates extracting text from a PDF without needing real files.

    Returns:
        A configured Mock of PDFProcessorAdapter
    """
    mock = Mock()

    async def mock_process(
        source: str,
        chunk_size: int = 1000,
        chunk_overlap: int = 200
    ) -> tuple:
        from app.core.domain.models import DocumentSource
        # Create the mocked document
        document = Document(
            id="test_doc_001",
            source=DocumentSource.PDF,
            content=f"Content extracted from the PDF: {source}",
            metadata={"source": source, "pages": 1}
        )
        # Create mocked chunks
        chunks = [
            Chunk(
                id="chunk_001",
                document_id="test_doc_001",
                content="First chunk of the document",
                metadata={"page": 1, "position": 0}
            ),
            Chunk(
                id="chunk_002",
                document_id="test_doc_001",
                content="Second chunk of the document",
                metadata={"page": 1, "position": 1}
            )
        ]
        return (document, chunks)

    mock.process_document = AsyncMock(side_effect=mock_process)

    return mock


# ============================================================================
# MOCKED-SERVICE FIXTURES
# ============================================================================

@pytest.fixture
def rag_service_with_mocks(mock_ollama, mock_chromadb):
    """
    RAGService configured with mocks for unit tests.

    Args:
        mock_ollama: Mock of the Ollama adapter
        mock_chromadb: Mock of the ChromaDB adapter

    Returns:
        RAGService configured with mocked dependencies
    """
    from app.core.services.rag_service import RAGService

    return RAGService(
        llm=mock_ollama,
        vector_db=mock_chromadb
    )


@pytest.fixture
def sync_service_with_mocks(mock_ollama, mock_chromadb, mock_pdf_processor):
    """
    SyncService configured with mocks for unit tests.

    Args:
        mock_ollama: Mock of the Ollama adapter
        mock_chromadb: Mock of the ChromaDB adapter
        mock_pdf_processor: Mock of the PDF processor

    Returns:
        SyncService configured with mocked dependencies
    """
    from app.core.services.sync_service import SyncService

    return SyncService(
        document_processor=mock_pdf_processor,
        vector_db=mock_chromadb,
        llm=mock_ollama
    )


# ============================================================================
# AUTHENTICATION FIXTURES
# ============================================================================

# Precomputed bcrypt hash of "testpass123", used by mock_user_repository.
# Computed once at module scope (bcrypt.hashpw is relatively slow) and
# reused by every test that needs a valid login.
TEST_USER_PASSWORD = "testpass123"
TEST_USER_PASSWORD_HASH = bcrypt.hashpw(TEST_USER_PASSWORD.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


@pytest.fixture
def mock_user_repository():
    """
    Mock of UserRepositoryPort for AuthService unit tests.

    Simulates a single existing user: test@example.com / testpass123
    (TEST_USER_PASSWORD / TEST_USER_PASSWORD_HASH above).
    """
    mock = Mock()

    async def mock_get_by_email(email: str):
        if email == "test@example.com":
            return User(
                id=1,
                email=email,
                password_hash=TEST_USER_PASSWORD_HASH,
                is_active=True,
            )
        return None

    async def mock_create_user(email: str, password_hash: str):
        return User(id=1, email=email, password_hash=password_hash)

    mock.get_by_email = AsyncMock(side_effect=mock_get_by_email)
    mock.create_user = AsyncMock(side_effect=mock_create_user)

    return mock


@pytest.fixture
def auth_service_with_mocks(mock_user_repository):
    """AuthService configured with a mocked UserRepositoryPort."""
    from app.core.services.auth_service import AuthService

    return AuthService(user_repository=mock_user_repository)


# ============================================================================
# CONVERSATION HISTORY FIXTURES
# ============================================================================

@pytest.fixture
def mock_conversation_repository():
    """
    Mock of ConversationRepositoryPort for ConversationService unit tests.

    Simulates a simple in-memory store: append_message() saves into an
    internal dict (keyed by session_id), get_recent_messages() reads from it.
    """
    from app.core.domain.models import ConversationMessage

    mock = Mock()
    storage: Dict[str, List[ConversationMessage]] = {}

    async def mock_append_message(session_id: str, user_id: int, role: str, content: str) -> None:
        storage.setdefault(session_id, []).append(
            ConversationMessage(role=role, content=content, created_at=datetime.now())
        )

    async def mock_get_recent_messages(session_id: str, user_id: int, limit: int):
        return storage.get(session_id, [])[-limit:]

    mock.append_message = AsyncMock(side_effect=mock_append_message)
    mock.get_recent_messages = AsyncMock(side_effect=mock_get_recent_messages)
    mock._storage = storage  # exposed for direct inspection in tests

    return mock


@pytest.fixture
def conversation_service_with_mocks(mock_conversation_repository):
    """ConversationService configured with a mocked ConversationRepositoryPort."""
    from app.core.services.conversation_service import ConversationService

    return ConversationService(conversation_repository=mock_conversation_repository)


# ============================================================================
# FASTAPI TEST CLIENT FIXTURES
# ============================================================================

@pytest.fixture
def test_client():
    """
    FastAPI test client, ALREADY AUTHENTICATED.

    Lets you make HTTP requests to the API without spinning up a real
    server. Every test using this fixture (test_api.py,
    test_notion_service.py, etc.) was written before authentication
    existed and checks business logic (validation, specific error
    codes), not login itself — so get_current_user is overridden with a
    test user so they keep testing what they tested before.

    Tests that DO want to exercise authentication (test_auth_endpoints.py)
    use their own `client` fixture, without this override.

    Returns:
        TestClient configured with the FastAPI app

    Usage:
        def test_endpoint(test_client):
            response = test_client.get("/health")
            assert response.status_code == 200
    """
    from app.main import get_current_user
    from app.core.services.auth_service import TokenPayload

    app.dependency_overrides[get_current_user] = lambda: TokenPayload(user_id=1, email="test@example.com")
    yield TestClient(app)
    app.dependency_overrides.clear()


# ============================================================================
# PYTEST HOOKS (setup/teardown)
# ============================================================================

@pytest.fixture(autouse=True)
def reset_mocks():
    """
    Fixture that runs automatically before every test.

    Resets mock state to avoid contamination between tests.
    autouse=True means it's applied automatically to every test.
    """
    yield  # The test runs here
    # After the test, any cleanup if needed
    pass
