# /api/app/adapters/outbound/chromadb_adapter.py
"""
ChromaDB Adapter - Concrete implementation of VectorDBPort - Bibliotecario-IA

This adapter connects the system to ChromaDB (vector database). It's
the REAL implementation of the contract defined by VectorDBPort.

What is ChromaDB?
- A database specialized in storing and searching vectors
- Enables semantic search (by meaning, not exact words)
- Runs as a separate server (similar to PostgreSQL)
- Reachable over HTTP at localhost:8000

What is a collection?
- Like a table in SQL, but for vectors
- Each collection stores chunks for one type of documentation
- Example: "tech_docs", "tutorials", "faq"

Data stored per chunk in ChromaDB:
- id: the chunk's unique identifier
- embedding: numeric vector [0.1, -0.2, 0.3, ...] (768 dimensions)
- document: the chunk's original text
- metadata: dict with extra info {document_id, source, page, ...}

Patterns implemented:
- Lazy Initialization: the client is only created when needed
- Collection cache: each collection is fetched only once
- Columnar format: ChromaDB needs data as parallel lists

TypeScript equivalent:
    class ChromaDBAdapter implements VectorDBPort {
        private client: ChromaClient | null = null;
        private collections: Map<string, Collection> = new Map();

        async storeChunks(chunks, collectionName): Promise<boolean> { ... }
        async similaritySearch(queryEmbedding, ...): Promise<SourceDocument[]> { ... }
        async deleteDocument(documentId, ...): Promise<boolean> { ... }
        async collectionExists(collectionName): Promise<boolean> { ... }
        async getCollectionStats(collectionName): Promise<Record<string, any>> { ... }
    }
"""

# ============================================================================
# IMPORTS
# ============================================================================
import time
import chromadb  # ChromaDB's official client
from chromadb.config import Settings as ChromaSettings  # ChromaDB configuration
from typing import List, Dict, Any, Optional

# Import the PORT (interface) we're implementing
from app.core.ports.vector_db_port import VectorDBPort
from app.core.domain.models import Chunk, SourceDocument, DocumentSummary
from app.config.settings import settings

# Observability: structured logging and metrics
from app.core.observability import get_logger, VECTOR_SEARCH_LATENCY


logger = get_logger(__name__)


# ============================================================================
# CHROMADB ADAPTER
# ============================================================================
class ChromaDBAdapter(VectorDBPort):
    """
    Concrete implementation of VectorDBPort using ChromaDB.

    This class is the ONLY place in the system that knows ChromaDB-
    specific details. Everywhere else in the code only talks to the
    VectorDBPort interface.

    If you switch to Pinecone or Weaviate someday, you only change this file.

    Internal state:
    - _client: connection to the ChromaDB server (lazy, created the first time)
    - _collections: collection cache (avoids re-fetching the same collection repeatedly)
    """

    def __init__(self):
        """
        Initializes the adapter with lazy initialization.

        Does NOT connect to ChromaDB here. The connection is created the
        first time it's needed (_get_client).

        _collections is a dict acting as a cache:
        { "tech_docs": <Collection>, "tutorials": <Collection> }
        JS equivalent: private collections = new Map<string, Collection>()
        """
        self._client = None
        self._collections = {}

    def _get_client(self) -> chromadb.HttpClient:
        """
        Gets or creates the connection to the ChromaDB server (Lazy Singleton).

        Same pattern as OllamaAdapter: the connection is created once and
        reused across all operations.

        HttpClient connects to the ChromaDB server over HTTP.
        anonymized_telemetry=False: disables telemetry (privacy).

        Returns:
            chromadb.HttpClient: Client connected to the ChromaDB server
        """
        if self._client is None:
            try:
                self._client = chromadb.HttpClient(
                    host=settings.chromadb_host,  # localhost
                    port=settings.chromadb_port,  # 8000
                    settings=ChromaSettings(
                        anonymized_telemetry=False  # Doesn't send data to Chroma
                    )
                )
                logger.info("Connected to ChromaDB", url=settings.chromadb_url)
            except Exception as e:
                logger.error("Failed to connect to ChromaDB", error=str(e), url=settings.chromadb_url)
                raise
        return self._client

    def _get_or_create_collection(self, collection_name: str):
        """
        Gets an existing collection or creates it if it doesn't exist.

        Double pattern:
        1. Local cache: if we already have it in _collections, return it
        2. ChromaDB get_or_create: if it doesn't exist on the server, create it

        get_or_create_collection is a ChromaDB method that does:
        - If the collection exists → returns it
        - If it doesn't exist → creates it and returns it
        It's like an "upsert" but for collections.

        Args:
            collection_name: Collection name (e.g. "tech_docs")

        Returns:
            Collection: ChromaDB collection object
        """
        # First check the local cache
        if collection_name not in self._collections:
            client = self._get_client()
            try:
                # get_or_create_collection: creates if missing, returns if it exists
                self._collections[collection_name] = client.get_or_create_collection(
                    name=collection_name,
                    metadata={"description": "Bibliotecario-IA document embeddings"}
                )
                logger.info("Using collection", collection_name=collection_name)
            except Exception as e:
                logger.error("Failed to get/create collection", collection_name=collection_name, error=str(e))
                raise
        return self._collections[collection_name]

    # ========================================================================
    # MAIN METHODS - VectorDBPort implementation
    # ========================================================================

    async def store_chunks(
        self,
        chunks: List[Chunk],
        collection_name: str = "documents"
    ) -> bool:
        """
        Stores chunks with their embeddings in ChromaDB.

        This method converts the Chunk objects into the COLUMNAR FORMAT
        ChromaDB needs: 4 parallel lists where position i in each list
        corresponds to the same chunk.

        Columnar format:
            ids        = ["chunk_0", "chunk_1", "chunk_2"]
            embeddings = [[0.1,...], [0.2,...], [0.3,...]]
            documents  = ["text 0", "text 1", "text 2"]
            metadatas  = [{...},     {...},     {...}    ]

            ids[0] ↔ embeddings[0] ↔ documents[0] ↔ metadatas[0] = same chunk

        Why columnar instead of row-based?
        ChromaDB is internally optimized to store vectors in contiguous
        memory arrays. The columnar format enables this.

        Args:
            chunks: List of chunks WITH embeddings already generated
            collection_name: Target collection in ChromaDB

        Returns:
            bool: True if stored successfully
        """
        try:
            if not chunks:
                logger.warning("No chunks to store")
                return False

            collection = self._get_or_create_collection(collection_name)

            # ============================================================
            # PREPARE DATA IN COLUMNAR FORMAT
            # ============================================================
            # List comprehension to extract each field from the chunks
            # JS equivalent: chunks.map(chunk => chunk.id)
            ids = [chunk.id for chunk in chunks]
            embeddings = [chunk.embedding for chunk in chunks if chunk.embedding]
            documents = [chunk.content for chunk in chunks]

            # Metadatas: spread operator {**chunk.metadata} copies the metadata
            # and adds document_id so it can later be deleted by document
            # JS equivalent: chunks.map(c => ({...c.metadata, documentId: c.documentId}))
            metadatas = [
                {**chunk.metadata, "document_id": chunk.document_id}
                for chunk in chunks
            ]

            # Validation: every chunk must have an embedding
            # If one is missing, ChromaDB would fail with a confusing error
            if not embeddings or len(embeddings) != len(chunks):
                logger.error("All chunks must have embeddings")
                return False

            # ============================================================
            # STORE IN CHROMADB
            # ============================================================
            # collection.add() is ChromaDB's main method
            # Receives the 4 lists in parallel
            collection.add(
                ids=ids,
                embeddings=embeddings,
                documents=documents,
                metadatas=metadatas
            )

            logger.info(
                "Stored chunks in collection",
                count=len(chunks),
                collection_name=collection_name
            )
            return True

        except Exception as e:
            logger.error("Failed to store chunks", error=str(e), count=len(chunks))
            return False

    async def similarity_search(
        self,
        query_embedding: List[float],
        collection_name: str = "documents",
        top_k: int = 4,
        filter_metadata: Optional[Dict[str, Any]] = None,
        keyword_filter: Optional[str] = None
    ) -> List[SourceDocument]:
        """
        Runs a similarity search in ChromaDB with Query Expansion support.

        THIS IS THE SYSTEM'S MOST IMPORTANT METHOD.
        This is where semantic search happens: given a question's vector,
        it finds the most semantically similar chunks.

        QUERY EXPANSION (hybrid search):
        If keyword_filter is given, it first filters documents containing
        that keyword (case-insensitive), then ranks by semantic
        similarity. This improves results for proper nouns and specific
        titles.

        How does it work internally?
        1. ChromaDB computes the L2 distance between the question's
           vector and ALL vectors stored in the collection
        2. Sorts by distance (smaller distance = more similar)
        3. Returns the top_k closest ones

        ChromaDB's response format (nested):
            results["ids"]       = [["id_0", "id_1", "id_2"]]      # [0] = first query
            results["documents"] = [["text_0", "text_1", ...]]
            results["distances"] = [[0.1, 0.3, 0.7]]               # smaller = more similar
            results["metadatas"] = [[{...}, {...}, {...}]]

        Why nested results with [0]?
        ChromaDB supports multiple simultaneous queries.
        Since we send a single query, the results are at index [0].

        Args:
            query_embedding: The user's question, as a vector
            collection_name: Collection to search
            top_k: Maximum number of results (e.g. the 3 most relevant chunks)
            filter_metadata: Optional filter by metadata
                           Example: {"source": "pdf"} → only PDF chunks
            keyword_filter: Keyword to filter documents by (Query Expansion)
                           Example: "Blade Runner" → only chunks containing that text

        Returns:
            List[SourceDocument]: Relevant chunks, sorted by similarity
        """
        try:
            collection = self._get_or_create_collection(collection_name)

            # ============================================================
            # QUERY TO CHROMADB (with Query Expansion support)
            # ============================================================
            # query_embeddings is a list because ChromaDB accepts batch queries
            # include: which fields to return (only ids by default)
            # where: filter by metadata (like WHERE in SQL)
            # where_document: filter by document content (keyword search)

            # Build the document filter if a keyword was given
            where_document = None
            if keyword_filter:
                # $contains searches for a substring in the document's content
                where_document = {"$contains": keyword_filter}
                logger.info("Applying keyword filter", keyword=keyword_filter)

            start_time = time.perf_counter()

            results = collection.query(
                query_embeddings=[query_embedding],  # List with a single query
                n_results=top_k,                     # Max number of results
                where=filter_metadata,               # Optional filter (None = no filter)
                where_document=where_document,       # Filter by content (Query Expansion)
                include=["documents", "metadatas", "distances"]  # Fields to include
            )

            # ============================================================
            # CONVERT RESULTS INTO SourceDocument
            # ============================================================
            source_docs = []
            # Check there are results before iterating
            if results and results["ids"] and results["ids"][0]:
                # enumerate to get index i alongside each doc_id
                for i, doc_id in enumerate(results["ids"][0]):
                    # Accessed with [0][i] because: [0] = first query, [i] = i-th result
                    metadata = results["metadatas"][0][i] if results["metadatas"] else {}
                    document = results["documents"][0][i] if results["documents"] else ""
                    distance = results["distances"][0][i] if results["distances"] else 0.0

                    # ============================================================
                    # CONVERSION: L2 distance → similarity score (0 to 1)
                    # ============================================================
                    # ChromaDB uses L2 distance (smaller = closer = more similar)
                    # But we want a score where HIGHER = more similar
                    # Formula: similarity = 1 / (1 + distance)
                    #   distance = 0   → similarity = 1.0 (perfect match)
                    #   distance = 1   → similarity = 0.5
                    #   distance = 9   → similarity = 0.1 (very different)
                    similarity_score = 1.0 / (1.0 + distance)

                    source_docs.append(
                        SourceDocument(
                            document_id=metadata.get("document_id", doc_id),
                            chunk_content=document,
                            metadata=metadata,
                            relevance_score=similarity_score
                        )
                    )

            # Record metrics
            duration = time.perf_counter() - start_time
            VECTOR_SEARCH_LATENCY.observe(duration)

            logger.info(
                "Similarity search completed",
                results_found=len(source_docs),
                duration_seconds=round(duration, 3),
                keyword_filter=keyword_filter
            )
            return source_docs

        except Exception as e:
            logger.error("Similarity search failed", error=str(e))
            return []  # On error, return an empty list (doesn't raise an exception)

    async def delete_document(
        self,
        document_id: str,
        collection_name: str = "documents"
    ) -> bool:
        """
        Deletes all chunks associated with a document.

        Uses a metadata filter to find and delete every chunk belonging
        to that document_id.

        Why by metadata and not by ID?
        - A document produces MULTIPLE chunks (e.g. a 50-page PDF)
        - Each chunk has its own unique ID
        - But they all share the same document_id in their metadata
        - With where={"document_id": X} we delete them all at once

        Args:
            document_id: Document ID (all its chunks get deleted)
            collection_name: Collection the document is in

        Returns:
            bool: True if the operation succeeded
        """
        try:
            collection = self._get_or_create_collection(collection_name)

            # where works like a WHERE filter in SQL
            # Deletes every chunk with that document_id in its metadata
            collection.delete(
                where={"document_id": document_id}
            )

            logger.info("Deleted chunks for document", document_id=document_id)
            return True

        except Exception as e:
            logger.error("Failed to delete document", document_id=document_id, error=str(e))
            return False

    async def collection_exists(self, collection_name: str) -> bool:
        """
        Checks whether a collection exists in ChromaDB.

        Fetches the list of all collections on the server and checks
        whether any of them has the name we're looking for.

        any(): returns True if at least one element satisfies the condition
        JS equivalent: collections.some(col => col.name === collectionName)

        Args:
            collection_name: Name of the collection to look for

        Returns:
            bool: True if the collection exists
        """
        try:
            client = self._get_client()
            collections = client.list_collections()
            # any() with a generator expression: efficient because it stops
            # at the first match (doesn't scan the whole list once found)
            return any(col.name == collection_name for col in collections)
        except Exception as e:
            logger.error("Failed to check collection existence", error=str(e), collection_name=collection_name)
            return False

    async def get_collection_stats(
        self,
        collection_name: str = "documents"
    ) -> Dict[str, Any]:
        """
        Gets statistics for a ChromaDB collection.

        collection.count() returns the total number of stored chunks.
        Useful for:
        - Showing the user how many documents are indexed
        - The API's GET /info endpoint
        - Verifying ingestion worked correctly

        Args:
            collection_name: Collection to query

        Returns:
            Dict with the collection's statistics
        """
        try:
            collection = self._get_or_create_collection(collection_name)
            # count() returns the total number of embeddings in the collection
            count = collection.count()

            return {
                "collection_name": collection_name,
                "document_count": count,  # Total stored chunks
                "status": "active"
            }

        except Exception as e:
            logger.error("Failed to get collection stats", error=str(e), collection_name=collection_name)
            # On error, return a valid structure with the error included
            # This way the frontend doesn't fail to parse it
            return {
                "collection_name": collection_name,
                "document_count": 0,
                "status": "error",
                "error": str(e)
            }

    async def list_documents(
        self,
        collection_name: str = "documents"
    ) -> List[DocumentSummary]:
        """
        Lists the distinct documents in a collection, grouping chunks by
        their "document_id" in metadata.

        Unlike similarity_search, this does NOT rank by similarity or
        apply top_k: it fetches ALL chunks in the collection
        (collection.get(), with no query_embeddings) and groups them. At
        this scale (tens/hundreds of chunks) it's cheap; if the
        collection grew a lot (thousands of chunks) it would need
        limit/offset pagination — not implemented in this MVP.

        How are each document's "title" and "source" obtained?
        - title: metadata["title"] if it exists and isn't "Untitled"
          (Notion pages with no title — see
          NotionProcessorAdapter._extract_title), otherwise
          metadata["filename"] (PDFs), otherwise the document_id itself.
        - source: doesn't come as an explicit field in each chunk's
          metadata, so it's inferred from the document_id's deterministic
          prefix ("pdf_..." / "notion_...", see how
          PDFProcessorAdapter.load_document and
          NotionProcessorAdapter.load_document generate it).

        Args:
            collection_name: Collection to query

        Returns:
            List[DocumentSummary]: one per document_id, alphabetically sorted by title
        """
        try:
            collection = self._get_or_create_collection(collection_name)

            # include=["metadatas"]: no need to fetch embeddings or
            # documents (the chunks' text), just their metadata
            result = collection.get(include=["metadatas"])

            ids = result.get("ids") or []
            metadatas = result.get("metadatas") or []

            # Groups chunks by document_id, counting how many there are of
            # each and keeping the metadata of the first one we see (every
            # chunk of the same document shares title/filename)
            grouped: Dict[str, Dict[str, Any]] = {}
            for chunk_id, metadata in zip(ids, metadatas):
                metadata = metadata or {}
                document_id = metadata.get("document_id", chunk_id)
                if document_id not in grouped:
                    grouped[document_id] = {"chunk_count": 0, "metadata": metadata}
                grouped[document_id]["chunk_count"] += 1

            summaries = []
            for document_id, info in grouped.items():
                metadata = info["metadata"]

                title = metadata.get("title")
                if not title or title == "Untitled":
                    title = metadata.get("filename") or document_id

                if document_id.startswith("pdf_"):
                    source = "pdf"
                elif document_id.startswith("notion_"):
                    source = "notion"
                else:
                    source = "unknown"

                summaries.append(DocumentSummary(
                    document_id=document_id,
                    title=title,
                    source=source,
                    chunk_count=info["chunk_count"]
                ))

            summaries.sort(key=lambda doc: doc.title.lower())

            logger.info(
                "Listed documents in collection",
                collection_name=collection_name,
                document_count=len(summaries)
            )
            return summaries

        except Exception as e:
            logger.error("Failed to list documents", error=str(e), collection_name=collection_name)
            return []
