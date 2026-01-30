# /api/app/adapters/outbound/chromadb_adapter.py

"""
ChromaDB adapter implementation for vector database operations.
"""

import chromadb
from chromadb.config import Settings as ChromaSettings
from typing import List, Dict, Any, Optional
import logging

from app.core.ports.vector_db_port import VectorDBPort
from app.core.domain.models import Chunk, SourceDocument
from app.config.settings import settings


logger = logging.getLogger(__name__)


class ChromaDBAdapter(VectorDBPort):
    """ChromaDB implementation of the VectorDBPort interface."""

    def __init__(self):
        """Initialize ChromaDB client."""
        self._client = None
        self._collections = {}

    def _get_client(self) -> chromadb.HttpClient:
        """Get or create ChromaDB client."""
        if self._client is None:
            try:
                self._client = chromadb.HttpClient(
                    host=settings.chromadb_host,
                    port=settings.chromadb_port,
                    settings=ChromaSettings(
                        anonymized_telemetry=False
                    )
                )
                logger.info(f"Connected to ChromaDB at {settings.chromadb_url}")
            except Exception as e:
                logger.error(f"Failed to connect to ChromaDB: {e}")
                raise
        return self._client

    def _get_or_create_collection(self, collection_name: str):
        """Get or create a ChromaDB collection."""
        if collection_name not in self._collections:
            client = self._get_client()
            try:
                self._collections[collection_name] = client.get_or_create_collection(
                    name=collection_name,
                    metadata={"description": "Bibliotecario-IA document embeddings"}
                )
                logger.info(f"Using collection: {collection_name}")
            except Exception as e:
                logger.error(f"Failed to get/create collection {collection_name}: {e}")
                raise
        return self._collections[collection_name]

    async def store_chunks(
        self,
        chunks: List[Chunk],
        collection_name: str = "documents"
    ) -> bool:
        """Store chunks with embeddings in ChromaDB."""
        try:
            if not chunks:
                logger.warning("No chunks to store")
                return False

            collection = self._get_or_create_collection(collection_name)

            # Prepare data for ChromaDB
            ids = [chunk.id for chunk in chunks]
            embeddings = [chunk.embedding for chunk in chunks if chunk.embedding]
            documents = [chunk.content for chunk in chunks]
            metadatas = [
                {**chunk.metadata, "document_id": chunk.document_id}
                for chunk in chunks
            ]

            if not embeddings or len(embeddings) != len(chunks):
                logger.error("All chunks must have embeddings")
                return False

            # Store in ChromaDB
            collection.add(
                ids=ids,
                embeddings=embeddings,
                documents=documents,
                metadatas=metadatas
            )

            logger.info(f"Stored {len(chunks)} chunks in collection '{collection_name}'")
            return True

        except Exception as e:
            logger.error(f"Failed to store chunks: {e}")
            return False

    async def similarity_search(
        self,
        query_embedding: List[float],
        collection_name: str = "documents",
        top_k: int = 4,
        filter_metadata: Optional[Dict[str, Any]] = None
    ) -> List[SourceDocument]:
        """Perform similarity search in ChromaDB."""
        try:
            collection = self._get_or_create_collection(collection_name)

            # Query ChromaDB
            results = collection.query(
                query_embeddings=[query_embedding],
                n_results=top_k,
                where=filter_metadata,
                include=["documents", "metadatas", "distances"]
            )

            # Convert to SourceDocument objects
            source_docs = []
            if results and results["ids"] and results["ids"][0]:
                for i, doc_id in enumerate(results["ids"][0]):
                    metadata = results["metadatas"][0][i] if results["metadatas"] else {}
                    document = results["documents"][0][i] if results["documents"] else ""
                    distance = results["distances"][0][i] if results["distances"] else 0.0

                    # Convert distance to similarity score (0-1 range)
                    # ChromaDB uses L2 distance, smaller is better
                    similarity_score = 1.0 / (1.0 + distance)

                    source_docs.append(
                        SourceDocument(
                            document_id=metadata.get("document_id", doc_id),
                            chunk_content=document,
                            metadata=metadata,
                            relevance_score=similarity_score
                        )
                    )

            logger.info(f"Found {len(source_docs)} similar documents")
            return source_docs

        except Exception as e:
            logger.error(f"Similarity search failed: {e}")
            return []

    async def delete_document(
        self,
        document_id: str,
        collection_name: str = "documents"
    ) -> bool:
        """Delete all chunks for a document."""
        try:
            collection = self._get_or_create_collection(collection_name)

            # Delete by metadata filter
            collection.delete(
                where={"document_id": document_id}
            )

            logger.info(f"Deleted chunks for document: {document_id}")
            return True

        except Exception as e:
            logger.error(f"Failed to delete document {document_id}: {e}")
            return False

    async def collection_exists(self, collection_name: str) -> bool:
        """Check if collection exists."""
        try:
            client = self._get_client()
            collections = client.list_collections()
            return any(col.name == collection_name for col in collections)
        except Exception as e:
            logger.error(f"Failed to check collection existence: {e}")
            return False

    async def get_collection_stats(
        self,
        collection_name: str = "documents"
    ) -> Dict[str, Any]:
        """Get collection statistics."""
        try:
            collection = self._get_or_create_collection(collection_name)
            count = collection.count()

            return {
                "collection_name": collection_name,
                "document_count": count,
                "status": "active"
            }

        except Exception as e:
            logger.error(f"Failed to get collection stats: {e}")
            return {
                "collection_name": collection_name,
                "document_count": 0,
                "status": "error",
                "error": str(e)
            }
