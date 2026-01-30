# /api/app/core/services/rag_service.py

"""
RAG (Retrieval-Augmented Generation) service for answering questions (Phase 1).
Orchestrates: query -> retrieve context -> generate answer.
"""

import logging
import time
from typing import Optional

from app.core.ports.llm_port import LLMPort
from app.core.ports.vector_db_port import VectorDBPort
from app.core.domain.models import Query, QueryResult, SourceDocument
from app.config.settings import settings


logger = logging.getLogger(__name__)


class RAGService:
    """Service for answering questions using RAG pipeline."""

    def __init__(
        self,
        llm: LLMPort,
        vector_db: VectorDBPort
    ):
        """
        Initialize RAG service with required dependencies.

        Args:
            llm: LLM adapter for generating responses and embeddings
            vector_db: Vector database adapter for retrieving context
        """
        self.llm = llm
        self.vector_db = vector_db

    async def ask_question(
        self,
        query: Query,
        collection_name: Optional[str] = None
    ) -> QueryResult:
        """
        Answer a question using RAG pipeline.

        Pipeline:
        1. Generate embedding for the question
        2. Retrieve relevant context from vector database
        3. Build prompt with context
        4. Generate answer using LLM
        5. Return answer with source documents

        Args:
            query: User query
            collection_name: Optional collection name (defaults to config)

        Returns:
            QueryResult with answer and sources
        """
        start_time = time.time()
        collection = collection_name or settings.chromadb_collection_name

        try:
            logger.info(f"Processing question: {query.question[:50]}...")

            # Step 1: Generate embedding for the question
            query_embedding = await self.llm.generate_embedding(query.question)
            logger.debug(f"Generated query embedding of dimension: {len(query_embedding)}")

            # Step 2: Retrieve relevant context
            source_documents = await self.vector_db.similarity_search(
                query_embedding=query_embedding,
                collection_name=collection,
                top_k=query.max_results
            )

            if not source_documents:
                logger.warning("No relevant context found in database")
                return QueryResult(
                    question=query.question,
                    answer="Lo siento, no encontré información relevante en la base de conocimientos para responder a tu pregunta.",
                    source_documents=[],
                    session_id=query.session_id,
                    processing_time=time.time() - start_time
                )

            logger.info(f"Retrieved {len(source_documents)} relevant documents")

            # Step 3: Build context from retrieved documents
            context = self._build_context(source_documents)

            # Step 4: Generate answer using LLM with context
            answer = await self.llm.generate_response(
                prompt=query.question,
                context=context,
                temperature=settings.llm_temperature,
                max_tokens=settings.llm_max_tokens
            )

            processing_time = time.time() - start_time
            logger.info(f"Generated answer in {processing_time:.2f}s")

            return QueryResult(
                question=query.question,
                answer=answer,
                source_documents=source_documents,
                session_id=query.session_id,
                processing_time=processing_time
            )

        except Exception as e:
            error_msg = f"Failed to process question: {str(e)}"
            logger.error(error_msg, exc_info=True)

            return QueryResult(
                question=query.question,
                answer=f"Lo siento, ocurrió un error al procesar tu pregunta: {str(e)}",
                source_documents=[],
                session_id=query.session_id,
                processing_time=time.time() - start_time
            )

    def _build_context(self, source_documents: list[SourceDocument]) -> str:
        """
        Build context string from retrieved documents.

        Args:
            source_documents: List of relevant source documents

        Returns:
            Formatted context string
        """
        context_parts = []

        for i, doc in enumerate(source_documents, 1):
            # Format each source document
            context_part = f"[Fuente {i}]\n{doc.chunk_content}"
            context_parts.append(context_part)

        # Join all parts with separators
        context = "\n\n---\n\n".join(context_parts)

        logger.debug(f"Built context with {len(source_documents)} sources")
        return context

    async def get_collection_info(
        self,
        collection_name: Optional[str] = None
    ) -> dict:
        """
        Get information about the vector database collection.

        Args:
            collection_name: Optional collection name

        Returns:
            Dictionary with collection stats
        """
        collection = collection_name or settings.chromadb_collection_name

        try:
            stats = await self.vector_db.get_collection_stats(collection)
            return {
                "collection": collection,
                "stats": stats,
                "model_info": self.llm.get_model_info()
            }

        except Exception as e:
            logger.error(f"Failed to get collection info: {e}")
            return {
                "collection": collection,
                "stats": {"error": str(e)},
                "model_info": {}
            }
