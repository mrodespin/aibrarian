# /api/app/core/ports/vector_db_port.py
"""
Port (Interface) for the Vector Database - AIbrarian

This file defines the CONTRACT that any vector database must fulfill.
It's an abstract interface (no implementation, just method definitions).

What is a Port in Hexagonal Architecture?
- Defines WHAT operations exist, but NOT HOW they're implemented
- Decouples business logic from the specific technology
- Makes it easy to swap ChromaDB for Pinecone without touching services

TypeScript equivalent:
    interface VectorDBPort {
        storeChunks(chunks: Chunk[]): Promise<boolean>;
        similaritySearch(queryEmbedding: number[]): Promise<SourceDocument[]>;
        deleteDocument(documentId: string): Promise<boolean>;
        collectionExists(name: string): Promise<boolean>;
        getCollectionStats(name: string): Promise<Record<string, any>>;
    }

The real implementation lives at: /adapters/outbound/chromadb_adapter.py
"""

# ============================================================================
# IMPORTS
# ============================================================================
# ABC (Abstract Base Class) lets you create abstract classes in Python
# abstractmethod marks methods as "required to implement"
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
from app.core.domain.models import Chunk, SourceDocument, DocumentSummary


# ============================================================================
# VECTOR DATABASE INTERFACE
# ============================================================================
class VectorDBPort(ABC):
    """
    Abstract interface for vector database operations.

    What is a vector database?
    - Stores texts as numeric vectors (embeddings)
    - Lets you search for similar texts using cosine distance
    - Examples: ChromaDB, Pinecone, Weaviate, Milvus

    How does it work?
    1. Text "the black cat" → Embedding model → Vector [0.1, -0.2, 0.3, ...]
    2. The vector is stored alongside the original text
    3. To search: question → vector → search for similar vectors

    Methods any adapter must implement:
    - store_chunks: Save text fragments
    - similarity_search: Search for similar texts (RAG's CORE operation)
    - delete_document: Delete a document
    - collection_exists: Check whether a collection exists
    - get_collection_stats: Get statistics

    Note: ABC = Abstract Base Class
    - Can't be instantiated directly: VectorDBPort() → Error
    - Only subclasses that implement the methods can be created
    """

    @abstractmethod
    async def store_chunks(
        self,
        chunks: List[Chunk],
        collection_name: str = "documents"
    ) -> bool:
        """
        Stores text chunks with their embeddings in the database.

        What is a chunk?
        - A ~500-1000 character fragment of a document
        - Includes: id, content, embedding (vector), metadata

        Args:
            chunks: List of Chunk objects to store
                   Each chunk must already have its embedding generated
            collection_name: Collection name (like a "table" in SQL)
                           Default: "documents"

        Returns:
            bool: True if stored successfully, False on error

        Example:
            chunks = [
                Chunk(id="doc1_0", content="Text...", embedding=[0.1, 0.2, ...]),
                Chunk(id="doc1_1", content="More text...", embedding=[0.3, 0.4, ...])
            ]
            success = await vector_db.store_chunks(chunks)

        Note: async def = asynchronous function (like async function in JavaScript)
        """
        pass  # pass = no implementation, the subclass must implement it

    @abstractmethod
    async def similarity_search(
        self,
        query_embedding: List[float],
        collection_name: str = "documents",
        top_k: int = 4,
        filter_metadata: Optional[Dict[str, Any]] = None,
        keyword_filter: Optional[str] = None
    ) -> List[SourceDocument]:
        """
        Searches for the chunks most similar to a query vector.

        THIS IS THE MOST IMPORTANT METHOD IN THE RAG SYSTEM.

        How does it work?
        1. Receives the embedding (vector) of the user's question
        2. Compares that vector against ALL stored vectors
        3. Uses cosine distance to measure similarity
        4. Returns the top_k most similar chunks

        What is cosine distance?
        - Measures the angle between two vectors
        - Score 1.0 = identical vectors (same meaning)
        - Score 0.0 = perpendicular vectors (nothing in common)
        - Example: "dog" and "cat" → ~0.7, "dog" and "airplane" → ~0.2

        Query Expansion (hybrid search):
        If keyword_filter is provided, it first filters documents
        containing that keyword, then ranks by semantic similarity.
        Useful for proper nouns and specific titles.

        Args:
            query_embedding: The question's vector (list of ~768 floats)
                           Generated by the embedding model (nomic-embed-text)
            collection_name: Collection to search
            top_k: Number of results to return (default: 4)
            filter_metadata: Optional filters, e.g.: {"source": "pdf"}
            keyword_filter: Keyword to filter documents by (Query Expansion)
                          Example: "Blade Runner" → only chunks containing that text

        Returns:
            List[SourceDocument]: Most relevant chunks with:
                - document_id: Source document ID
                - chunk_content: The chunk's text
                - metadata: Additional info
                - relevance_score: Similarity score (0-1)

        Example:
            # 1. User asks: "What is machine learning?"
            # 2. An embedding of the question is generated
            query_vec = await llm.generate_embedding("What is machine learning?")
            # query_vec = [0.1, -0.2, 0.3, ...] (768 numbers)

            # 3. Similar chunks are searched for
            results = await vector_db.similarity_search(query_vec, top_k=5)

            # 4. results[0] = most relevant chunk
            # results[0].relevance_score = 0.92
            # results[0].chunk_content = "Machine learning is a branch of AI..."
        """
        pass

    @abstractmethod
    async def delete_document(
        self,
        document_id: str,
        collection_name: str = "documents"
    ) -> bool:
        """
        Deletes all chunks associated with a document.

        Why delete by document_id and not by chunk_id?
        - A document can have MANY chunks (a 50-page PDF ≈ 100 chunks)
        - It's more practical to delete them all at once
        - Chunks have document_id as a "foreign key"

        Args:
            document_id: ID of the document to delete
            collection_name: Collection the document is in

        Returns:
            bool: True if deleted successfully

        Example:
            # Delete a PDF we no longer need
            await vector_db.delete_document("doc_123")
        """
        pass

    @abstractmethod
    async def collection_exists(self, collection_name: str) -> bool:
        """
        Checks whether a collection exists in the database.

        What is a collection?
        - Like a "table" in relational databases
        - Groups related chunks together
        - Lets you have multiple separate "knowledge bases"

        Args:
            collection_name: Name of the collection to check

        Returns:
            bool: True if it exists, False otherwise

        Useful for:
        - Checking the system's initial setup
        - Creating the collection if it doesn't exist
        - Validating configuration
        """
        pass

    @abstractmethod
    async def get_collection_stats(
        self,
        collection_name: str = "documents"
    ) -> Dict[str, Any]:
        """
        Gets statistics for a collection.

        Args:
            collection_name: Collection name

        Returns:
            Dict with statistics, example:
            {
                "count": 150,              # Total number of chunks
                "dimensions": 768,          # Embedding dimensions
                "collection_name": "documents"
            }

        Useful for:
        - The API's /stats endpoint
        - System monitoring
        - Checking that documents have been loaded
        - Debugging ("were my PDFs indexed?")
        """
        pass

    @abstractmethod
    async def list_documents(
        self,
        collection_name: str = "documents"
    ) -> List[DocumentSummary]:
        """
        Lists the distinct documents stored in a collection, grouping
        their chunks — without going through similarity_search.

        Why is this needed if similarity_search already exists?
        similarity_search always returns at most top_k chunks, the ones
        most similar to a question. It's the right tool for "what does
        book X say about Y?", but it's the WRONG tool for "how many
        documents do you have in total?" — with top_k you can never
        guarantee seeing the full catalog. list_documents queries the
        metadata directly, with no ranking or relevance threshold, so it
        always returns ALL the documents.

        Args:
            collection_name: Collection to query

        Returns:
            List[DocumentSummary]: One per distinct document_id, with its
            title, source and chunk count. Sorted alphabetically by title.

        Useful for:
        - The GET /documents endpoint (browsing the knowledge base from the UI)
        - RAGService answering questions like "what documents do you know?"
        """
        pass
