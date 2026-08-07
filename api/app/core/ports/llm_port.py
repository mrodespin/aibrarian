# /api/app/core/ports/llm_port.py
"""
Port (Interface) for Language Model operations - AIbrarian

This file defines the CONTRACT that any LLM (Large Language Model) must
fulfill. It's an abstract interface that lets you swap Ollama for
OpenAI without modifying any services.

What is an LLM?
- Large Language Model
- Examples: GPT-4, Llama, Mistral, Claude
- Can understand and generate natural-language text

Why two types of operations?
1. generate_response: Uses a conversational model (llama3.2) to generate text
2. generate_embedding: Uses an embedding model (nomic-embed-text) to vectorize text

They're DIFFERENT models even though both are accessed through Ollama.

TypeScript equivalent:
    interface LLMPort {
        generateResponse(prompt: string, context?: string): Promise<string>;
        generateEmbedding(text: string): Promise<number[]>;
        generateEmbeddingsBatch(texts: string[]): Promise<number[][]>;
        isAvailable(): Promise<boolean>;
        getModelInfo(): Record<string, any>;
    }

The real implementation lives at: /adapters/outbound/ollama_adapter.py
"""

# ============================================================================
# IMPORTS
# ============================================================================
# ABC lets you create abstract classes (interfaces)
from abc import ABC, abstractmethod
from typing import List, Optional, Dict, Any, AsyncIterator


# ============================================================================
# LANGUAGE MODEL INTERFACE
# ============================================================================
class LLMPort(ABC):
    """
    Abstract interface for Language Model operations.

    The RAG system needs TWO capabilities from the LLM:

    1. TEXT GENERATION (generate_response):
       - Receives: question + context (relevant chunks)
       - Returns: a natural-language answer
       - Model used: llama3.2 (conversational)

    2. EMBEDDING GENERATION (generate_embedding):
       - Receives: text to vectorize
       - Returns: a numeric vector [0.1, -0.2, 0.3, ...]
       - Model used: nomic-embed-text (specialized in embeddings)

    Flow in the RAG system:
        User: "What is machine learning?"
            ↓
        generate_embedding("What is machine learning?")
            ↓
        Vector → ChromaDB → relevant chunks
            ↓
        generate_response(prompt=question, context=chunks)
            ↓
        "Machine learning is a branch of AI..."

    Note: ABC = Abstract Base Class (can't be instantiated directly)
    """

    @abstractmethod
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
        Generates a text response using the language model.

        THIS METHOD IS THE CHATBOT'S "BRAIN".

        How does it work internally?
        1. A prompt is built from the question + context
        2. It's sent to the model (Ollama/llama3.2)
        3. The model generates tokens one at a time until it's done
        4. The full response is returned

        Args:
            prompt: The user's question in natural language
                   Example: "What is machine learning?"

            context: Optional context (chunks retrieved from ChromaDB)
                    Example: "According to document X, machine learning is..."
                    The context is injected into the prompt to provide grounding

            history: Previous conversation turns, already formatted as
                    text (see ConversationService.get_history_prompt_block),
                    or None if there's no history. It's prepended to the
                    context in the prompt so the model can resolve
                    follow-up questions ("can you expand on that?").

            max_tokens: Token limit for the response (None = no limit)
                       A token ≈ 0.75 words in English
                       Example: max_tokens=500 ≈ 375 words

            temperature: Controls the model's "creativity" (0.0 to 1.0)
                        - 0.0 = deterministic (always the same answer)
                        - 0.7 = balance between coherence and variety (default)
                        - 1.0 = very creative/random
                        For technical Q&A, better to use 0.3-0.5

            **kwargs: Additional model-specific parameters
                     Like ...rest in JavaScript
                     Example: top_p=0.9, repetition_penalty=1.1

        Returns:
            str: The model's generated response

        Usage example:
            response = await llm.generate_response(
                prompt="What is RAG?",
                context="RAG stands for Retrieval-Augmented Generation...",
                temperature=0.3  # Low for more precise answers
            )
            # response = "RAG (Retrieval-Augmented Generation) is a technique..."
        """
        pass  # The real implementation lives in ollama_adapter.py

    @abstractmethod
    async def generate_embedding(self, text: str) -> List[float]:
        """
        Generates an embedding vector for a text.

        What is an embedding?
        - A numeric representation of a text's "meaning"
        - A vector of ~768 floating point numbers
        - Similar texts → vectors close together in that space

        What's it for?
        - Converting the user's question into a vector
        - That vector is compared against the chunks in ChromaDB
        - The most "semantically similar" chunks are found

        Args:
            text: Text to convert into a vector
                 Example: "How does authentication work?"

        Returns:
            List[float]: A vector of ~768 numbers
                        Example: [0.123, -0.456, 0.789, ...]

        Example:
            # Vectorize a question
            embedding = await llm.generate_embedding("What is Docker?")
            # embedding = [0.1, -0.2, 0.3, ...] (768 numbers)

            # This vector is sent to ChromaDB to search for similar chunks

        Model used: nomic-embed-text (specialized in embeddings)
        Dimensions: 768 (fixed for this model)
        """
        pass

    @abstractmethod
    async def generate_embeddings_batch(self, texts: List[str]) -> List[List[float]]:
        """
        Generates embeddings for multiple texts in a batch.

        Why batch instead of one at a time?
        - Efficiency: one call instead of N calls
        - Lower total latency
        - When ingesting a 100-chunk PDF, making 100 individual calls
          would be VERY inefficient

        Args:
            texts: List of texts to vectorize
                  Example: ["PDF chunk 1...", "PDF chunk 2...", ...]

        Returns:
            List[List[float]]: List of vectors, one per text
                              Keeps the same order as the input

        Example:
            chunks = ["Chunk 1 text", "Chunk 2 text", "Chunk 3 text"]
            embeddings = await llm.generate_embeddings_batch(chunks)
            # embeddings[0] corresponds to chunks[0]
            # embeddings[1] corresponds to chunks[1]
            # etc.

        Note: internally it may process in parallel or in mini-batches
              depending on the model/hardware's capabilities
        """
        pass

    @abstractmethod
    async def is_available(self) -> bool:
        """
        Checks whether the LLM service is available and responding.

        Useful for:
        - The API's health checks (/health endpoint)
        - Verifying Ollama is running before processing
        - Showing status to the user in the frontend

        Returns:
            bool: True if the service is available

        Example:
            if not await llm.is_available():
                raise ServiceUnavailableError("Ollama is not running")

        Typical implementation:
        - Tries a simple call to the model
        - Responds in < 5 seconds → True
        - Timeout or error → False
        """
        pass

    async def warm_up(self) -> None:
        """
        Preloads into memory whatever the adapter needs before the first
        real request (e.g. downloading/loading a local model).

        Not an @abstractmethod: it does nothing by default (empty
        implementation), so adapters that don't need it (OllamaAdapter,
        whose embeddings are served by the Ollama server itself) don't
        have to implement it. GroqAdapter overrides it to preload the
        local sentence-transformers model.

        Called as a background task AFTER FastAPI's startup finishes
        (see lifespan in main.py) — it must never block startup, since
        uvicorn doesn't open the port until startup completes (see
        is_available in groq_adapter.py for why).
        """
        pass

    async def stream_response(
        self,
        prompt: str,
        context: Optional[str] = None,
        history: Optional[str] = None,
        max_tokens: Optional[int] = None,
        temperature: float = 0.7,
        **kwargs
    ) -> AsyncIterator[str]:
        """
        Streaming version of generate_response(): yields the response
        chunk by chunk instead of waiting for the full answer.

        Not an @abstractmethod (same pattern as warm_up): it falls back
        by default to generate_response() and yields a single chunk with
        the full answer, so an adapter that doesn't implement real
        streaming (e.g. GroqAdapter in this first version) is still a
        valid LLMPort without having to override anything. OllamaAdapter
        does override it with real streaming (llm.astream()).

        Args:
            Same as generate_response() — see there for details.

        Yields:
            str: fragments of the response, in generation order.
                 Concatenated in order, they form the same full response
                 that generate_response() would return with the same arguments.
        """
        yield await self.generate_response(
            prompt=prompt,
            context=context,
            history=history,
            max_tokens=max_tokens,
            temperature=temperature,
            **kwargs
        )

    @abstractmethod
    def get_model_info(self) -> Dict[str, Any]:
        """
        Gets information about the current model.

        Note: This method is NOT async (no await) because the info is
              typically cached in memory.

        Returns:
            Dict with model information:
            {
                "model_name": "llama3.2",
                "embedding_model": "nomic-embed-text",
                "embedding_dimensions": 768,
                "provider": "ollama",
                "base_url": "http://localhost:11434"
            }

        Useful for:
        - The API's /info endpoint
        - Debugging ("what model am I using?")
        - Logging and monitoring
        """
        pass

    @abstractmethod
    async def extract_keywords(self, question: str) -> List[str]:
        """
        Extracts keywords and entities from a question (Query Expansion).

        Why Query Expansion?
        - Pure semantic search can fail with proper nouns
        - Example: "Blade Runner" vs "Blade Runner 2049"
        - Extracting keywords lets you filter documents before searching

        Flow:
            Question: "Who directed Blade Runner 2049?"
                ↓
            Keywords: ["Blade Runner 2049", "directed", "director"]
                ↓
            Filter by keywords + semantic search

        Args:
            question: The user's question in natural language

        Returns:
            List[str]: List of extracted keywords/entities
                      Empty list if none could be extracted

        Example:
            keywords = await llm.extract_keywords("What is Docker?")
            # keywords = ["Docker"]
        """
        pass

    @abstractmethod
    async def is_catalog_question(self, question: str) -> bool:
        """
        Classifies whether a question is about the CATALOG (how
        many/what documents there are in total) rather than about the
        CONTENT of one specific document.

        Why is this needed?
        similarity_search always returns at most top_k chunks — it's the
        right tool for "what does book X say about Y?", but it
        structurally CANNOT answer "how many books do you know?" well:
        there's no way to guarantee top_k covers the whole catalog.
        RAGService uses this method to route that class of question to
        VectorDBPort.list_documents() instead of similarity_search (see
        RAGService._build_meta_answer).

        Note: this is independent from condense_question() — a catalog
        question doesn't need rewriting with history, so this check runs
        BEFORE that, and only if it's False does the question go through
        condense_question() before retrieval.

        Why an LLM and not a keyword regex?
        A regex of typical phrases only covers one language and one
        specific wording. The LLM understands the intent regardless of
        language or how the question is phrased — same principle as
        extract_keywords(), which also delegates to the LLM instead of a
        list of patterns.

        Must be a cheap, fast call: short prompt, single-word response,
        low/zero temperature so the classification is consistent. On a
        network/parsing error, it must return False (safe fallback:
        falls back to the normal RAG pipeline instead of breaking the
        question entirely).

        Args:
            question: The user's question in natural language, in any language

        Returns:
            bool: True if the question is about the document
                  catalog/inventory, False if it's about content (or if
                  there was an error)

        Example:
            await llm.is_catalog_question("How many books do you know?")   # True
            await llm.is_catalog_question("How many books do you have?")   # True
            await llm.is_catalog_question("Who wrote 1984?")               # False
        """
        pass

    @abstractmethod
    async def condense_question(self, question: str, history: str) -> str:
        """
        Rewrites a follow-up question as a standalone question,
        incorporating the necessary context from the previous
        conversation — a standard pattern in conversational RAG ("query
        rewriting" / "condense question", see LangChain's
        `create_history_aware_retriever` for the same idea).

        Why is this needed?
        similarity_search/extract_keywords rely ONLY on the current
        question's text. A short follow-up question with no proper nouns
        ("what year was it published?", "how many pages does it have?")
        has no anchor to find the right document — it might find
        nothing, or (worse, confirmed in production) find a chunk from a
        DIFFERENT document with a high enough score to sneak in as
        "relevant" and produce a confident but wrong answer.

        By rewriting BEFORE retrieval ("what year was it published?" +
        history about "One Hundred Years of Solitude" → "What year was
        One Hundred Years of Solitude published?"), the vector search
        receives a standalone question and goes back to working with the
        normal pipeline as always (extract_keywords + similarity_search)
        — no special path or bypassing ChromaDB needed.

        If the question is already standalone (explicitly names the
        document/topic, or doesn't depend on earlier turns), it must be
        returned unchanged, without rewriting — this method does NOT
        decide whether rewriting is needed, it's always asked to try;
        it's the method's own prompt that must leave the question intact
        if it already stands on its own.

        On error, it must return the original question untouched (safe
        fallback: worst case, retrieval behaves as it did before this
        function existed, it doesn't break the request).

        Args:
            question: The user's follow-up question
            history: Previous conversation turns, already formatted (see
                     ConversationService.get_history_prompt_block) —
                     callers should only invoke this method when history
                     is not None/empty (with no history there's nothing to condense)

        Returns:
            str: the question rewritten as standalone, or the original
                 if it already was or if there was an error

        Example:
            await llm.condense_question(
                "What year was it published?",
                history="User: tell me about One Hundred Years of Solitude\\nAssistant: ...published in 1967..."
            )
            # "What year was One Hundred Years of Solitude published?"
        """
        pass
