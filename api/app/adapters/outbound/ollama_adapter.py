# /api/app/adapters/outbound/ollama_adapter.py
"""
Ollama Adapter - Concrete implementation of LLMPort - AIbrarian

This adapter connects the system to Ollama (local LLM server).
It's the REAL implementation of the contract defined by LLMPort.

What is Ollama?
- A local server that runs LLM models without needing the cloud
- Installed on the user's machine
- Reachable over HTTP at localhost:11434
- Models used:
    - llama3.2: conversational model (generates text)
    - nomic-embed-text: embedding model (vectorizes text)

Why use LangChain?
- Provides the OllamaLLM and OllamaEmbeddings classes
- Abstracts away Ollama's API details
- Built-in async methods (ainvoke, aembed_query)
- If we switched to OpenAI, only this adapter would need to change

Patterns implemented:
- Lazy Initialization: clients are only created when needed
- Retry with Exponential Backoff: automatically retries on failure
- Singleton per field: each client is created exactly once

TypeScript equivalent:
    class OllamaAdapter implements LLMPort {
        private llm: OllamaLLM | null = null;
        private embeddings: OllamaEmbeddings | null = null;

        async generateResponse(prompt, context?, ...): Promise<string> { ... }
        async generateEmbedding(text): Promise<number[]> { ... }
        async generateEmbeddingsBatch(texts): Promise<number[][]> { ... }
        async isAvailable(): Promise<boolean> { ... }
        getModelInfo(): Record<string, any> { ... }
    }
"""

# ============================================================================
# IMPORTS
# ============================================================================
from typing import List, Optional, Dict, Any
import time
import httpx  # Async HTTP client (equivalent to axios in JS)

# tenacity: library for automatic retries with configurable wait strategies
from tenacity import retry, stop_after_attempt, wait_exponential

# LangChain: framework that abstracts communication with different LLMs
from langchain_ollama import OllamaLLM, OllamaEmbeddings

# Import the PORT (interface) we're implementing
from app.core.ports.llm_port import LLMPort
from app.config.settings import settings

# Observability: structured logging and metrics
from app.core.observability import get_logger, LLM_REQUESTS, LLM_LATENCY


logger = get_logger(__name__)


# ============================================================================
# OLLAMA ADAPTER
# ============================================================================
class OllamaAdapter(LLMPort):
    """
    Concrete implementation of LLMPort using Ollama via LangChain.

    This class is the ONLY place in the system that knows Ollama-specific
    details. Everywhere else in the code only talks to the LLMPort
    interface.

    Two internal clients:
    - _llm: OllamaLLM → llama3.2 model for text generation
    - _embeddings: OllamaEmbeddings → nomic-embed-text model for vectorizing

    Both connect to the same Ollama server (localhost:11434) but are
    different models with different jobs.
    """

    def __init__(self):
        """
        Initializes the adapter with lazy initialization.

        Does NOT connect to Ollama here. The clients are created the
        first time they're needed (_get_llm, _get_embeddings).

        Why lazy?
        - If Ollama isn't running when the app starts, it doesn't fail immediately
        - It only fails when the model is actually used
        - JS equivalent: private llm: OllamaLLM | null = null
        """
        self._llm = None
        self._embeddings = None

    def _get_llm(self) -> OllamaLLM:
        """
        Gets or creates the LLM client instance (Singleton per field).

        PATTERN: Lazy Singleton
        - First call: creates the client and stores it in self._llm
        - Subsequent calls: returns the same client
        - Avoids opening multiple connections to the server

        JS equivalent:
            private getLLM(): OllamaLLM {
                if (!this.llm) this.llm = new OllamaLLM({...});
                return this.llm;
            }

        Returns:
            OllamaLLM: Client configured with the llama3.2 model
        """
        if self._llm is None:
            try:
                self._llm = OllamaLLM(
                    base_url=settings.ollama_base_url,       # http://localhost:11434
                    model=settings.ollama_model,             # llama3.2
                    temperature=settings.llm_temperature,   # 0.3 (precision)
                    timeout=settings.ollama_timeout          # seconds to wait
                )
                logger.info("Initialized Ollama LLM", model=settings.ollama_model)
            except Exception as e:
                logger.error("Failed to initialize Ollama LLM", error=str(e))
                raise  # Re-raise after logging
        return self._llm

    def _get_embeddings(self) -> OllamaEmbeddings:
        """
        Gets or creates the Embeddings client instance (Singleton per field).

        Same lazy pattern as _get_llm, but for the embedding model.
        Model: nomic-embed-text (specialized in producing vectors)

        Returns:
            OllamaEmbeddings: Client configured with the nomic-embed-text model
        """
        if self._embeddings is None:
            try:
                self._embeddings = OllamaEmbeddings(
                    base_url=settings.ollama_base_url,            # http://localhost:11434
                    model=settings.ollama_embedding_model         # nomic-embed-text
                )
                logger.info("Initialized Ollama Embeddings", model=settings.ollama_embedding_model)
            except Exception as e:
                logger.error("Failed to initialize Ollama Embeddings", error=str(e))
                raise
        return self._embeddings

    # ========================================================================
    # MAIN METHODS - LLMPort implementation
    # ========================================================================

    def _build_full_prompt(
        self,
        prompt: str,
        context: Optional[str],
        history: Optional[str]
    ) -> str:
        """
        Builds the full prompt sent to the model, combining (if present)
        the conversation history and the context retrieved from ChromaDB
        with the user's question.

        Factored out as its own method because both generate_response()
        and stream_response() need exactly the same prompt — the only
        difference between them is how the model's response is consumed
        (all at once vs. streamed), not how the question is built.

        Args:
            prompt: The user's question
            context: Context (chunks retrieved by ChromaDB), or None
            history: Previous conversation turns, already formatted
                     (see ConversationService.get_history_prompt_block), or None

        Returns:
            str: the full prompt, ready to send to the model
        """
        # If there's history (previous conversation turns), it's prepended
        # to the rest of the prompt so the LLM can resolve follow-up
        # questions ("can you expand on that?"). Note: this ONLY affects
        # generation — chunk retrieval is still based solely on the
        # current question (see RAGService).
        history_block = f"""PREVIOUS CONVERSATION (earlier turns, for context):
{history}

""" if history else ""

        # If there's context (ChromaDB chunks), the prompt is structured
        # so the LLM uses that information as its basis
        if context:
            return f"""You are a librarian assistant that ONLY answers using the information provided in the context.

STRICT RULES:
1. Only use the information in the context to answer
2. Do NOT use your general knowledge or outside information
3. If the information isn't in the context, say so clearly, in the same language as the question — do not guess or fill the gap with outside knowledge
4. Cite sources when relevant
5. Always answer in the same language as the question

{history_block}CONTEXT (information from your knowledge base):
{context}

USER QUESTION: {prompt}

ANSWER (based ONLY on the context above):"""
        elif history_block:
            # No context but there's history. RAGService shouldn't normally
            # reach this branch (condense_question() rewrites the follow-up
            # question and retrieval proceeds as usual — see
            # RAGService.ask_question), but it's kept as a safety net for
            # any call made with context=None + history.
            # This branch used to not enforce any strict rules at all
            # (unlike the `if context:` branch above); the comment said
            # "we still require it to stick to what was already said" but
            # the actual text didn't enforce that. Now it does, with the
            # same 4 anti-hallucination rules as the context branch,
            # applied to the history instead of ChromaDB chunks.
            return f"""You are a librarian assistant. You've already talked with the user about this earlier in this same conversation — the answer to their question should be in what was already said below.

STRICT RULES:
1. Answer ONLY with information that already appears in the previous conversation
2. Do NOT use your general knowledge or make up data that isn't there
3. If the answer isn't in the previous conversation, say so clearly, in the same language as the question
4. Always answer in the same language as the question

{history_block}USER QUESTION: {prompt}

ANSWER (based ONLY on the previous conversation):"""
        else:
            # No context and no history: the question is sent straight to
            # the LLM (it will answer using its general knowledge)
            return prompt

    # PATTERN: @retry with Exponential Backoff
    # - stop_after_attempt(3): at most 3 attempts before failing
    # - wait_exponential: the wait between attempts grows exponentially
    #   multiplier=1, min=2, max=10 → waits: 2s, 4s, 8s (capped at 10s)
    # Why? If Ollama is busy processing another request, instead of
    # failing immediately, we wait and retry.
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10)
    )
    async def generate_response(
        self,
        prompt: str,
        context: Optional[str] = None,
        history: Optional[str] = None,
        max_tokens: Optional[int] = None,
        temperature: float = 0.7,
        **kwargs
    ) -> str:
        """
        Generates a text response using Ollama/llama3.2.

        THIS IS THE KEY POINT OF THE RAG: this is where the prompt that
        combines the question with the chunk context gets built.

        The LLM receives a prompt structured like:
            "Context information: [ChromaDB chunks]
             Question: [user's question]
             Answer based on the context above:"

        This structure tells the LLM it should base its answer ONLY on
        the provided context, not on its general knowledge.

        Args:
            prompt: The user's question
            context: Context (chunks retrieved by ChromaDB)
            history: Previous conversation turns, already formatted
                     (see ConversationService.get_history_prompt_block)
            max_tokens: Token limit (None = use Ollama's default)
            temperature: Model creativity
            **kwargs: Additional parameters for the model

        Returns:
            str: Response generated by llama3.2
        """
        try:
            # Get the LLM client (lazy, only created the first time)
            llm = self._get_llm()
            full_prompt = self._build_full_prompt(prompt, context, history)

            # ============================================================
            # MODEL CALL
            # ============================================================
            # ainvoke() is LangChain's async method for invoking the LLM
            # the "a" in ainvoke = async (vs. invoke, which is sync)
            # Equivalent: await llm.invoke(prompt) in async form
            #
            # NOTE: OllamaLLM._default_params only exposes 4 top-level
            # keys (model, format, options, keep_alive); ainvoke() only
            # forwards to Ollama the kwargs matching those names.
            # temperature and num_predict (max_tokens) go NESTED inside
            # "options" — passing them loose as kwargs (as this code used
            # to do) doesn't raise any error, Ollama just ignores them and
            # always uses the temperature the client was built with in
            # _get_llm().
            ollama_options: Dict[str, Any] = {"temperature": temperature, **kwargs}
            if max_tokens is not None:
                ollama_options["num_predict"] = max_tokens

            start_time = time.perf_counter()
            response = await llm.ainvoke(
                full_prompt,
                options=ollama_options
            )
            duration = time.perf_counter() - start_time

            # Record metrics
            LLM_REQUESTS.labels(operation='generate').inc()
            LLM_LATENCY.labels(operation='generate').observe(duration)

            logger.info(
                "Generated response from Ollama",
                duration_seconds=round(duration, 3),
                response_length=len(response)
            )
            return response

        except Exception as e:
            logger.error("Failed to generate response", error=str(e))
            raise  # Re-raise so @retry can retry

    async def stream_response(
        self,
        prompt: str,
        context: Optional[str] = None,
        history: Optional[str] = None,
        max_tokens: Optional[int] = None,
        temperature: float = 0.7,
        **kwargs
    ):
        """
        Streaming version of generate_response(): yields the response
        chunk by chunk as Ollama generates it, instead of waiting for the
        full response.

        Uses the same prompt as generate_response() (see
        _build_full_prompt) and the same options={...} fix for
        temperature/num_predict — the only real difference is astream()
        instead of ainvoke().

        No @retry (unlike generate_response): retrying midway through an
        already-started stream would produce duplicated chunks on the
        client side; if astream() fails, the error propagates and the
        caller (RAGService.ask_question_stream) decides how to handle it.

        Yields:
            str: text fragments of the response, in order
        """
        llm = self._get_llm()
        full_prompt = self._build_full_prompt(prompt, context, history)

        ollama_options: Dict[str, Any] = {"temperature": temperature, **kwargs}
        if max_tokens is not None:
            ollama_options["num_predict"] = max_tokens

        start_time = time.perf_counter()
        chunk_count = 0
        try:
            async for chunk in llm.astream(full_prompt, options=ollama_options):
                chunk_count += 1
                yield chunk
        finally:
            duration = time.perf_counter() - start_time
            LLM_REQUESTS.labels(operation='generate_stream').inc()
            LLM_LATENCY.labels(operation='generate_stream').observe(duration)
            logger.info(
                "Streamed response from Ollama",
                duration_seconds=round(duration, 3),
                chunk_count=chunk_count
            )

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10)
    )
    async def generate_embedding(self, text: str) -> List[float]:
        """
        Generates an embedding for a single text using nomic-embed-text.

        Used to vectorize the user's QUESTION before searching ChromaDB.

        Difference between aembed_query and aembed_documents?
        - aembed_query: for search texts (questions)
        - aembed_documents: for texts to store (chunks)
        LangChain can apply different optimizations depending on the type.

        Args:
            text: Text to vectorize (e.g. the user's question)

        Returns:
            List[float]: Vector of ~768 floating point numbers
        """
        try:
            embeddings = self._get_embeddings()

            # aembed_query: async embedding for queries/questions
            start_time = time.perf_counter()
            embedding = await embeddings.aembed_query(text)
            duration = time.perf_counter() - start_time

            # Record metrics
            LLM_REQUESTS.labels(operation='embed').inc()
            LLM_LATENCY.labels(operation='embed').observe(duration)

            logger.debug("Generated embedding", dimension=len(embedding), duration_seconds=round(duration, 3))
            return embedding

        except Exception as e:
            logger.error("Failed to generate embedding", error=str(e))
            raise

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10)
    )
    async def generate_embeddings_batch(self, texts: List[str]) -> List[List[float]]:
        """
        Generates embeddings for multiple texts in a batch.

        Used during document INGESTION to vectorize all the chunks of a
        PDF in a single call.

        aembed_documents: async embedding for documents/chunks.
        More efficient than calling aembed_query N times.

        Args:
            texts: List of texts to vectorize (document chunks)

        Returns:
            List[List[float]]: List of vectors, same order as the input
        """
        try:
            embeddings = self._get_embeddings()

            # aembed_documents: batch async embedding for documents
            start_time = time.perf_counter()
            embedding_vectors = await embeddings.aembed_documents(texts)
            duration = time.perf_counter() - start_time

            # Record metrics
            LLM_REQUESTS.labels(operation='embed_batch').inc()
            LLM_LATENCY.labels(operation='embed_batch').observe(duration)

            logger.info(
                "Generated batch embeddings",
                count=len(embedding_vectors),
                duration_seconds=round(duration, 3)
            )
            return embedding_vectors

        except Exception as e:
            logger.error("Failed to generate batch embeddings", error=str(e), batch_size=len(texts))
            raise

    async def is_available(self) -> bool:
        """
        Checks whether the Ollama server is up and responding.

        Makes a real HTTP call to Ollama's /api/tags endpoint. This
        endpoint lists the available models and is lightweight.

        Why httpx and not LangChain?
        - It's a simple health check, doesn't need the full framework
        - httpx is more direct for checking whether the server responds
        - async with: context manager that closes the connection automatically
          (JS equivalent: try/finally to clean up resources)

        Returns:
            bool: True if Ollama responds with status 200
        """
        try:
            # httpx.AsyncClient: async HTTP client (like axios in JS)
            # async with: opened and closed automatically (context manager)
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{settings.ollama_base_url}/api/tags",  # Ollama's endpoint
                    timeout=5.0  # 5 second max wait
                )
                if response.status_code == 200:
                    logger.info("Ollama service is available", base_url=settings.ollama_base_url)
                    return True
                else:
                    logger.warning("Ollama returned unexpected status", status_code=response.status_code)
                    return False

        except Exception as e:
            # Any error (timeout, connection refused, etc.) = unavailable
            logger.error("Ollama service unavailable", error=str(e), base_url=settings.ollama_base_url)
            return False

    def get_model_info(self) -> Dict[str, Any]:
        """
        Returns information about the configured Ollama models.

        NOT async because it only reads values from settings (in memory).
        Makes no external calls.

        Returns:
            Dict with the current model configuration
        """
        return {
            "llm_model": settings.ollama_model,                # llama3.2
            "embedding_model": settings.ollama_embedding_model, # nomic-embed-text
            "base_url": settings.ollama_base_url,               # http://localhost:11434
            "temperature": settings.llm_temperature,            # 0.3
            "timeout": settings.ollama_timeout                  # seconds
        }

    @retry(
        stop=stop_after_attempt(2),
        wait=wait_exponential(multiplier=1, min=1, max=5)
    )
    async def extract_keywords(self, question: str) -> List[str]:
        """
        Extracts keywords and entities from a question using the LLM.

        TECHNIQUE: Query Expansion
        The LLM identifies proper nouns, titles, and key terms that can
        be used to filter documents before semantic search.

        The prompt is designed to:
        - Extract named entities (movies, people, places, etc.)
        - Return a parseable format (one keyword per line)
        - Be fast (low temperature, short response)

        Args:
            question: The user's question

        Returns:
            List[str]: Extracted keywords, empty if none or on error
        """
        try:
            llm = self._get_llm()

            # Prompt optimized for keyword extraction
            extraction_prompt = f"""Extract the keywords and proper nouns from this question.
Return ONLY the keywords, one per line, with no explanations or numbering.
If there's a movie title, book title, or proper noun, include it exactly as it appears.

Question: {question}

Keywords:"""

            start_time = time.perf_counter()
            # Same as in generate_response(): temperature goes nested in
            # "options", not as a loose kwarg (see the detailed comment there).
            response = await llm.ainvoke(
                extraction_prompt,
                options={"temperature": 0.1}  # Very low for consistent responses
            )
            duration = time.perf_counter() - start_time

            # Parse the response: split by line and clean up
            keywords = []
            for line in response.strip().split('\n'):
                keyword = line.strip().strip('-').strip('•').strip()
                # Filter out empty lines and very short keywords
                if keyword and len(keyword) > 2:
                    keywords.append(keyword)

            # Record metrics
            LLM_REQUESTS.labels(operation='extract_keywords').inc()
            LLM_LATENCY.labels(operation='extract_keywords').observe(duration)

            logger.info(
                "Extracted keywords from question",
                keywords=keywords,
                count=len(keywords),
                duration_seconds=round(duration, 3)
            )
            return keywords

        except Exception as e:
            logger.warning("Failed to extract keywords", error=str(e))
            # On error, return an empty list (fallback to pure semantic search)
            return []

    @retry(
        stop=stop_after_attempt(2),
        wait=wait_exponential(multiplier=1, min=1, max=5)
    )
    async def is_catalog_question(self, question: str) -> bool:
        """
        Classifies whether the question is about the catalog (how
        many/what documents exist) or about content, using the LLM.

        Same pattern as extract_keywords(): short prompt, very low
        temperature for a consistent classification, single-word
        response so parsing is trivial. See LLMPort.is_catalog_question
        for the why (language/wording independent, unlike a regex of
        phrases).

        Args:
            question: The user's question, in any language

        Returns:
            bool: True if it's a catalog question, False in any other
                  case (including errors) — a safe fallback to the normal pipeline
        """
        try:
            llm = self._get_llm()

            classification_prompt = f"""Classify the following question into a single category.

CATALOG: the question asks for the total number, a listing, or a summary of ALL the documents in the knowledge base, as a collection. Examples: "how many books do you know?", "how many books do you have?", "what documents do you have", "list the books", "what's in your knowledge base".
CONTENT: the question asks for information about ONE specific document (even if not explicitly named and implied by the conversation's context) — this includes questions asking for a QUANTITY about that particular document: pages, chapters, publication year, price, etc. Examples: "who wrote 1984?", "what is Docker?", "summarize chapter 3", "how many pages does it have?", "how many chapters does this book have?", "what year was it published?".

Key rule to disambiguate: if the question asks for a quantity ABOUT ONE document (pages, chapters, year...) it's CONTENT, not CATALOG. It's only CATALOG if it asks for the number or listing of ALL the documents in the knowledge base as a whole.

Answer with a single word: CATALOG or CONTENT. Nothing else.

Question: {question}

Category:"""

            start_time = time.perf_counter()
            response = await llm.ainvoke(
                classification_prompt,
                options={"temperature": 0.0}  # Deterministic: it's a classification, not generation
            )
            duration = time.perf_counter() - start_time

            is_catalog = "CATALOG" in response.strip().upper()

            LLM_REQUESTS.labels(operation='classify_intent').inc()
            LLM_LATENCY.labels(operation='classify_intent').observe(duration)

            logger.info(
                "Classified question intent",
                is_catalog_question=is_catalog,
                duration_seconds=round(duration, 3)
            )
            return is_catalog

        except Exception as e:
            logger.warning("Failed to classify question intent, falling back to content pipeline", error=str(e))
            # Safe fallback: if classification fails, we treat the
            # question as content (the normal pipeline already knows how
            # to admit "I don't have that information" if nothing relevant is found)
            return False

    @retry(
        stop=stop_after_attempt(2),
        wait=wait_exponential(multiplier=1, min=1, max=5)
    )
    async def condense_question(self, question: str, history: str) -> str:
        """
        Rewrites a follow-up question as a standalone question, using the
        conversation history. See LLMPort.condense_question for the why
        (standard pattern for conversational RAG).

        Args:
            question: The user's follow-up question
            history: Previous conversation turns, already formatted

        Returns:
            str: the rewritten question, or the original if it was
                 already standalone or if there was an error
        """
        try:
            llm = self._get_llm()

            condense_prompt = f"""Given the previous conversation and the user's follow-up question, rewrite the follow-up question as a standalone question that includes all the context needed to understand it without needing the previous conversation.

If the follow-up question is ALREADY standalone (for example, it already explicitly mentions the document or topic it's about), return it EXACTLY AS IS, unchanged.

Answer ONLY with the question (rewritten or unchanged), with no explanations, no quotes, no prefixes.

PREVIOUS CONVERSATION:
{history}

FOLLOW-UP QUESTION: {question}

STANDALONE QUESTION:"""

            start_time = time.perf_counter()
            response = await llm.ainvoke(
                condense_prompt,
                options={"temperature": 0.0}  # Deterministic: it's a mechanical rewrite, not creative generation
            )
            duration = time.perf_counter() - start_time

            condensed = response.strip().strip('"')
            # If the LLM returns an empty or degenerate response, better to
            # keep the original question than lose it
            if not condensed:
                condensed = question

            LLM_REQUESTS.labels(operation='condense_question').inc()
            LLM_LATENCY.labels(operation='condense_question').observe(duration)

            logger.info(
                "Condensed follow-up question",
                original=question,
                condensed=condensed,
                duration_seconds=round(duration, 3)
            )
            return condensed

        except Exception as e:
            logger.warning("Failed to condense question, using original", error=str(e))
            # Safe fallback: if the rewrite fails, we keep going with the
            # original question — retrieval behaves as if this function
            # didn't exist, it doesn't break the request
            return question
