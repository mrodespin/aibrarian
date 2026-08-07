# /api/app/core/services/rag_service.py
"""
RAG (Retrieval-Augmented Generation) Service - Bibliotecario-IA

This service is the HEART of the system. It implements the full RAG
pattern: receives a user question and returns an answer grounded in
documents.

What is RAG?
- Retrieval-Augmented Generation
- Combines vector search (ChromaDB) with text generation (LLM)
- The LLM does NOT make up answers: it grounds them in real chunks from the documents

Difference from SyncService?
- SyncService: Data → ChromaDB (INGESTION pipeline)
- RAGService:  ChromaDB → Answer (QUERY pipeline)

Full RAG pipeline:
    Question → Embedding → Search → Context → LLM → Answer

Only needs 2 ports (not DocumentProcessor, since it doesn't process docs):
- LLMPort: To generate embeddings and answers
- VectorDBPort: To search for relevant chunks

TypeScript equivalent:
    class RAGService {
        constructor(
            private llm: LLMPort,
            private vectorDb: VectorDBPort
        ) {}

        async askQuestion(query: Query): Promise<QueryResult> { ... }
        private buildContext(docs: SourceDocument[]): string { ... }
        async getCollectionInfo(): Promise<Record<string, any>> { ... }
    }

Endpoints that use this service:
- POST /query → ask_question()
- GET /info  → get_collection_info()
"""

# ============================================================================
# IMPORTS
# ============================================================================
import logging
import time
from typing import AsyncIterator, Dict, Any, Optional

# We only import LLM and VectorDB (we don't need DocumentProcessor)
from app.core.ports.llm_port import LLMPort
from app.core.ports.vector_db_port import VectorDBPort
from app.core.domain.models import Query, QueryResult, SourceDocument, DocumentSummary
from app.config.settings import settings


logger = logging.getLogger(__name__)


# ============================================================================
# RAG SERVICE
# ============================================================================
class RAGService:
    """
    Service for answering questions using the RAG pipeline.

    This is the main service users interact with indirectly. When
    someone asks a question through the API, this service:
    1. Searches ChromaDB for relevant information
    2. Builds a context from that information
    3. Asks the LLM to answer based on that context

    Advantage of the RAG pattern over a bare LLM:
    - Without RAG: the LLM answers from its general knowledge (can make things up)
    - With RAG: the LLM answers grounded in YOUR documents (more accurate)
    """

    def __init__(
        self,
        llm: LLMPort,
        vector_db: VectorDBPort
    ):
        """
        Initializes the RAG service with its required dependencies.

        Only needs 2 ports (unlike SyncService, which needs 3):
        - LLM: To vectorize the question and generate the answer
        - VectorDB: To search for relevant chunks

        Args:
            llm: Language model adapter (Ollama)
            vector_db: Vector database adapter (ChromaDB)
        """
        self.llm = llm
        self.vector_db = vector_db

    async def ask_question(
        self,
        query: Query,
        collection_name: Optional[str] = None,
        history: Optional[str] = None
    ) -> QueryResult:
        """
        Answers a question using the full RAG pipeline with Query Expansion.

        THIS IS THE SYSTEM'S MAIN METHOD.
        It's the one invoked when a user asks a question.

        Earlier shortcut (before ①): before touching the vector DB,
        LLMPort.is_catalog_question() checks whether the question is
        about the catalog itself ("how many documents do you have?") →
        if so, it's answered with _build_meta_answer(), with no retrieval.

        If it's NOT a catalog question and there's `history`, the
        question first goes through LLMPort.condense_question() —
        standard conversational RAG pattern ("query rewriting" /
        "condense question", see LangChain's
        `create_history_aware_retriever` for the same idea): rewrites a
        short follow-up question ("what year was it published?") as a
        standalone question ("what year was One Hundred Years of
        Solitude published?") using the history. It exists because a
        follow-up question with no proper nouns can make
        similarity_search return a chunk from a DIFFERENT document with
        a score high enough to "look" relevant — seen in production, not
        hypothetical — and by then there's no signal anything went wrong
        after the fact. With the question already standalone, the usual
        retrieval pipeline (extract_keywords + similarity_search) works
        again without needing any special path.

        Pipeline with Query Expansion:
            ⓪ Condense if there's history → condense_question() [NEW]
            ① Extract keywords         → extract_keywords()
            ② Vectorize the question   → generate_embedding()
            ③ Search with keywords     → similarity_search(keyword_filter)
            ④ Semantic fallback        → similarity_search() with no filter
            ⑤ Build context            → _build_context()
            ⑥ Generate the answer      → generate_response()
            ⑦ Return the result        → QueryResult

        What is Query Expansion?
        A technique that improves search for proper nouns and titles:
        - We extract keywords from the question (e.g. "Blade Runner 2049")
        - We search for documents containing those keywords
        - If there are no results, we fall back to pure semantic search

        Args:
            query: Query object with:
                   - question: the user's question
                   - max_results: max number of chunks to retrieve
                   - session_id: session ID (used by the /ask endpoint to
                     fetch `history`, not read directly here)
            collection_name: ChromaDB collection (optional)
            history: Text block with previous conversation turns
                     (already formatted by
                     ConversationService.get_history_prompt_block), or
                     None if there's no history / the conversation has no
                     session_id. Feeds both question condensing
                     (retrieval) and the final generation prompt.

        Returns:
            QueryResult with:
                - answer: the LLM's generated answer
                - source_documents: chunks used as context
                - processing_time: total operation time

        Example:
            query = Query(question="What is Docker?", max_results=3)
            result = await rag_service.ask_question(query)
            print(result.answer)  # "Docker is a platform..."
            print(len(result.source_documents))  # 3 sources used
        """
        start_time = time.time()
        collection = collection_name or settings.chromadb_collection_name

        try:
            if await self.llm.is_catalog_question(query.question):
                answer = await self._build_meta_answer(collection)
                return QueryResult(
                    question=query.question,
                    answer=answer,
                    source_documents=[],
                    session_id=query.session_id,
                    processing_time=time.time() - start_time
                )

            retrieval_question = await self._condense_if_needed(query.question, history)
            source_documents = await self._retrieve(retrieval_question, query.max_results, collection)

            # If there are no relevant results, we don't call the LLM
            # Saves resources and avoids it making up an answer
            if not source_documents:
                logger.warning("No relevant context found in database")
                return QueryResult(
                    question=query.question,
                    answer="Sorry, I couldn't find relevant information in the knowledge base to answer your question.",
                    source_documents=[],
                    session_id=query.session_id,
                    processing_time=time.time() - start_time
                )

            logger.info(f"Retrieved {len(source_documents)} relevant documents")

            # ================================================================
            # STEP 3: Build the context from the chunks
            # ================================================================
            # Converts the list of SourceDocuments into formatted text
            # that will be injected into the LLM as context
            context = self._build_context(source_documents)

            # ================================================================
            # STEP 4: Generate the answer using the LLM with context
            # ================================================================
            # The LLM receives:
            # - prompt: retrieval_question (the question already condensed
            #   if it needed to be — standalone, reads the same as the
            #   original if it didn't need rewriting)
            # - context: the relevant chunks, formatted
            # The LLM must base its answer ONLY on that context
            answer = await self.llm.generate_response(
                prompt=retrieval_question,
                context=context,
                history=history,                          # Previous turns, or None
                temperature=settings.rag_temperature,    # 0.3 by default, for precision
                max_tokens=settings.llm_max_tokens       # Response limit
            )

            processing_time = time.time() - start_time
            logger.info(f"Generated answer in {processing_time:.2f}s")

            # ================================================================
            # STEP 5: Return the result with the answer and sources
            # ================================================================
            # QueryResult includes source_documents so the frontend can
            # show "this answer was based on these sources"
            return QueryResult(
                question=query.question,
                answer=answer,
                source_documents=source_documents,
                session_id=query.session_id,
                processing_time=processing_time
            )

        except Exception as e:
            # On error, we return a QueryResult with a message for the
            # user (we don't raise the exception)
            error_msg = f"Failed to process question: {str(e)}"
            logger.error(error_msg, exc_info=True)

            return QueryResult(
                question=query.question,
                answer=f"Sorry, an error occurred while processing your question: {str(e)}",
                source_documents=[],
                session_id=query.session_id,
                processing_time=time.time() - start_time
            )

    async def ask_question_stream(
        self,
        query: Query,
        collection_name: Optional[str] = None,
        history: Optional[str] = None
    ) -> AsyncIterator[Dict[str, Any]]:
        """
        Streaming version of ask_question(): yields the answer chunk by
        chunk instead of waiting to have the whole thing before returning anything.

        Uses exactly the same retrieval as ask_question() (see
        _retrieve), so the relevance filter and the Query Expansion
        fallback behave the same in both methods — only how the
        generation is consumed changes (stream_response() instead of
        generate_response()).

        Yields (in this order):
            {"type": "sources", "source_documents": [...]}
                Once, right after retrieval, before generating.
            {"type": "token", "text": "..."}
                One per generated text fragment, in order. If there were
                no relevant chunks, a single token is emitted with the
                fallback message (same text ask_question returns in that
                case) instead of actually trying to generate.
            {"type": "done", "processing_time": ..., "session_id": ...}
                Once, at the end.

        Args:
            Same as ask_question() — see there for details.
        """
        start_time = time.time()
        collection = collection_name or settings.chromadb_collection_name

        # Same catalog shortcut as ask_question() — see LLMPort.is_catalog_question.
        if await self.llm.is_catalog_question(query.question):
            answer = await self._build_meta_answer(collection)
            yield {"type": "sources", "source_documents": []}
            yield {"type": "token", "text": answer}
            yield {
                "type": "done",
                "processing_time": time.time() - start_time,
                "session_id": query.session_id
            }
            return

        # Same condense_question() as ask_question() — see there for why.
        retrieval_question = await self._condense_if_needed(query.question, history)
        source_documents = await self._retrieve(retrieval_question, query.max_results, collection)
        yield {"type": "sources", "source_documents": source_documents}

        if not source_documents:
            logger.warning("No relevant context found in database")
            yield {
                "type": "token",
                "text": "Sorry, I couldn't find relevant information in the knowledge base to answer your question."
            }
            yield {
                "type": "done",
                "processing_time": time.time() - start_time,
                "session_id": query.session_id
            }
            return

        logger.info(f"Retrieved {len(source_documents)} relevant documents")
        context = self._build_context(source_documents)

        async for chunk in self.llm.stream_response(
            prompt=retrieval_question,
            context=context,
            history=history,
            temperature=settings.rag_temperature,
            max_tokens=settings.llm_max_tokens
        ):
            yield {"type": "token", "text": chunk}

        processing_time = time.time() - start_time
        logger.info(f"Streamed answer in {processing_time:.2f}s")
        yield {
            "type": "done",
            "processing_time": processing_time,
            "session_id": query.session_id
        }

    async def _condense_if_needed(self, question: str, history: Optional[str]) -> str:
        """
        Rewrites `question` as a standalone question via
        LLMPort.condense_question() if there's history — if there's no
        history there's nothing to condense, it's returned unchanged
        without calling the LLM.

        Extracted into its own method because ask_question() and
        ask_question_stream() need it exactly the same way, before
        _retrieve() in both cases.

        Args:
            question: The user's question, as-is
            history: Previous conversation turns, or None

        Returns:
            str: question ready for retrieval (condensed, or the
                 original if there was no history to consult)
        """
        if not history:
            return question
        return await self.llm.condense_question(question, history)

    async def _retrieve(self, question: str, max_results: int, collection: str) -> list[SourceDocument]:
        """
        Runs retrieval with Query Expansion (keyword + semantic
        fallback) and applies the relevance filter — shared between
        ask_question() and ask_question_stream(), which only differ in
        how the subsequent generation is consumed.

        Pipeline:
            ① Extract keywords         → extract_keywords()
            ② Vectorize the question   → generate_embedding()
            ③ Search with keywords     → similarity_search(keyword_filter)
            ④ Semantic fallback        → similarity_search() with no filter
            (③ and ④ always go through _filter_by_relevance)

        Args:
            question: Question to use for retrieval — ALREADY condensed
                      if it needed to be (see _condense_if_needed), not
                      necessarily the original question exactly as the
                      user typed it
            max_results: top_k to request from similarity_search (from Query.max_results)
            collection: Name of the ChromaDB collection to search

        Returns:
            list[SourceDocument]: relevant chunks (can be empty)
        """
        # Truncate the question to 50 chars just for the log
        # [:50] is Python slicing (like substring in JS)
        logger.info(f"Processing question: {question[:50]}...")

        # ================================================================
        # STEP 1: Extract keywords for Query Expansion
        # ================================================================
        # The LLM identifies proper nouns, titles, etc.
        # Example: "Who directed Blade Runner?" → ["Blade Runner"]
        keywords = await self.llm.extract_keywords(question)
        logger.info(f"Extracted keywords: {keywords}")

        # ================================================================
        # STEP 2: Vectorize the question
        # ================================================================
        # The question is converted into a numeric vector
        # This vector will be used to search for similar chunks
        query_embedding = await self.llm.generate_embedding(question)
        logger.debug(f"Generated query embedding of dimension: {len(query_embedding)}")

        # ================================================================
        # STEP 3: Search with Query Expansion (keyword + semantic)
        # ================================================================
        # We try searching with each extracted keyword
        # If we find results, we use those; otherwise, semantic fallback
        source_documents = []

        if keywords:
            # Try searching with the most relevant keyword first
            # (usually the proper noun or title)
            for keyword in keywords:
                source_documents = await self.vector_db.similarity_search(
                    query_embedding=query_embedding,
                    collection_name=collection,
                    top_k=max_results,
                    keyword_filter=keyword
                )
                source_documents = self._filter_by_relevance(source_documents)
                if source_documents:
                    logger.info(f"Found {len(source_documents)} docs with keyword '{keyword}'")
                    break  # We found results, stop searching

        # ================================================================
        # STEP 4: Fall back to pure semantic search
        # ================================================================
        # If there are no keywords or we found no results with keywords,
        # we do a semantic search with no filters
        if not source_documents:
            logger.info("No results with keywords, falling back to semantic search")
            source_documents = await self.vector_db.similarity_search(
                query_embedding=query_embedding,
                collection_name=collection,
                top_k=max_results
            )
            source_documents = self._filter_by_relevance(source_documents)

        return source_documents

    async def _build_meta_answer(self, collection: str) -> str:
        """
        Builds a deterministic answer listing the full catalog.

        Unlike the earlier classification (LLMPort.is_catalog_question,
        which does use the LLM to decide WHETHER to route the question
        here), this method does NOT go through the LLM to build the
        answer itself: for "how many documents do you have?" there's
        nothing to generate, just list — which removes any risk of
        hallucination in the answer's CONTENT (the listing is always
        exact, it comes straight from list_documents()).

        Args:
            collection: ChromaDB collection to query

        Returns:
            str: Numbered list of documents, or a message if there are none
        """
        documents = await self.vector_db.list_documents(collection)
        if not documents:
            return "I don't have any documents indexed in my knowledge base yet."

        lines = [f"I know {len(documents)} documents in my knowledge base:\n"]
        lines += [f"{i}. {doc.title}" for i, doc in enumerate(documents, 1)]
        return "\n".join(lines)

    def _filter_by_relevance(self, source_documents: list[SourceDocument]) -> list[SourceDocument]:
        """
        Drops chunks whose relevance_score is below the minimum threshold.

        Why is this needed?
        ChromaDB always returns exactly top_k results (the closest ones
        available), even if none of them are actually relevant to the
        question. Without this filter, those low-relevance chunks would
        still be used as context and the LLM would end up fabricating an
        answer instead of admitting it has no information — exactly the
        bug this method fixes.

        Args:
            source_documents: Chunks retrieved from ChromaDB (already ranked)

        Returns:
            list[SourceDocument]: Only the chunks with relevance_score >= threshold
        """
        filtered = [
            doc for doc in source_documents
            if doc.relevance_score is None or doc.relevance_score >= settings.min_relevance_score
        ]
        if len(filtered) < len(source_documents):
            logger.info(
                f"Filtered out {len(source_documents) - len(filtered)} low-relevance chunks "
                f"(threshold={settings.min_relevance_score})"
            )
        return filtered

    def _build_context(self, source_documents: list[SourceDocument]) -> str:
        """
        Builds the context text from the retrieved chunks.

        PRIVATE METHOD (the leading underscore _ marks it as internal use only).
        Not called from outside the class.

        What does it do?
        Takes the relevant chunks from ChromaDB and formats them into
        text the LLM can understand as context to ground its answer.

        Example output:
            [Source 1]
            Docker is a container platform that lets you...

            ---

            [Source 2]
            Containers differ from VMs in that...

        Why number the sources?
        - Lets the LLM reference specific sources
        - The frontend can show "according to source 1..."
        - Makes the answer traceable back to its sources

        Args:
            source_documents: List of retrieved relevant chunks

        Returns:
            str: Formatted text with all the sources
        """
        context_parts = []

        # enumerate(list, 1) iterates with an index starting at 1
        # JS equivalent: source_documents.forEach((doc, i) => ...)
        # but i starts at 1 instead of 0
        for i, doc in enumerate(source_documents, 1):
            # Format: [Source N] + chunk content
            context_part = f"[Source {i}]\n{doc.chunk_content}"
            context_parts.append(context_part)

        # join() combines all the parts with a visual separator
        # "\n\n---\n\n" = blank line + dashes + blank line
        # JS equivalent: context_parts.join("\n\n---\n\n")
        context = "\n\n---\n\n".join(context_parts)

        logger.debug(f"Built context with {len(source_documents)} sources")
        return context

    async def get_collection_info(
        self,
        collection_name: Optional[str] = None
    ) -> dict:
        """
        Gets information about the vector database's collection.

        Helper method for the API's info/status endpoints.
        Returns ChromaDB stats + info about the active LLM model.

        Args:
            collection_name: Collection to query (optional)

        Returns:
            dict with:
                - collection: collection name
                - stats: statistics (total chunks, documents, etc.)
                - model_info: info about the active LLM model

        Example return value:
            {
                "collection": "tech_docs",
                "stats": {"total_chunks": 1500, "unique_documents": 12},
                "model_info": {"model_name": "llama3.2", "provider": "ollama"}
            }
        """
        collection = collection_name or settings.chromadb_collection_name

        try:
            # Gets stats from ChromaDB
            stats = await self.vector_db.get_collection_stats(collection)
            return {
                "collection": collection,
                "stats": stats,
                # get_model_info() isn't async, returns cached info
                "model_info": self.llm.get_model_info()
            }

        except Exception as e:
            # On error, return a valid structure with the error included
            # This way the frontend doesn't fail to parse the response
            logger.error(f"Failed to get collection info: {e}")
            return {
                "collection": collection,
                "stats": {"error": str(e)},
                "model_info": {}
            }

    async def list_known_documents(
        self,
        collection_name: Optional[str] = None
    ) -> list[DocumentSummary]:
        """
        Lists all documents indexed in the knowledge base.

        Unlike ask_question(), does NOT go through similarity_search or
        the LLM — delegates directly to vector_db.list_documents(),
        which groups by document_id with no ranking or top_k. It's the
        right way to answer "what do you have indexed?" (see GET
        /documents in main.py and RAGService._build_meta_answer, which
        reuses this same method to answer aggregate questions within the chat).

        Args:
            collection_name: Collection to query (optional)

        Returns:
            list[DocumentSummary]: one per document, alphabetically sorted by title
        """
        collection = collection_name or settings.chromadb_collection_name
        return await self.vector_db.list_documents(collection)
