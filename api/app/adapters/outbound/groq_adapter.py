# /api/app/adapters/outbound/groq_adapter.py
"""
Groq Adapter - Concrete implementation of LLMPort - AIbrarian

This adapter replaces OllamaAdapter for the cloud deployment (Render
free tier), where there's no GPU or Ollama process running.

Why a single adapter for two different backends?
LLMPort requires both text generation (generate_response,
extract_keywords) and embeddings (generate_embedding,
generate_embeddings_batch). Groq does NOT offer an embeddings endpoint
— only chat inference over open-weight models (Llama, gpt-oss, Qwen...)
on its LPU hardware.

Instead of splitting LLMPort into two interfaces (which would force
changes to RAGService, SyncService and main.py), this adapter composes
two engines internally and exposes a single LLMPort, the same way
OllamaAdapter does:
    - Text generation → Groq API (fast, free, cloud)
    - Embeddings      → local sentence-transformers (CPU, no API key,
                         no request limit, runs in the same API container)

This keeps the rest of the hexagon untouched: RAGService and
SyncService don't know whether they're talking to Ollama or to
Groq+sentence-transformers.

Note on dimensions: nomic-embed-text (Ollama) generates 768-dimension
vectors; all-MiniLM-L6-v2 (sentence-transformers) generates 384.
ChromaDB infers a collection's dimension from the first chunk inserted,
so switching adapters means re-ingesting documents into a new
collection (you can't mix embeddings of different dimensions in the
same collection).
"""

from typing import List, Optional, Dict, Any
import asyncio
import time

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential
from groq import AsyncGroq

from app.core.ports.llm_port import LLMPort
from app.config.settings import settings
from app.core.observability import get_logger, LLM_REQUESTS, LLM_LATENCY

logger = get_logger(__name__)

# System prompt with the same anti-hallucination rules OllamaAdapter's
# generate_response uses, so answer quality doesn't depend on which
# adapter is active.
_RAG_SYSTEM_PROMPT = """You are a librarian assistant that ONLY answers using the information provided in the context.

STRICT RULES:
1. Only use the information in the context to answer
2. Do NOT use your general knowledge or outside information
3. If the information isn't in the context, say so clearly, in the same language as the question — do not guess or fill the gap with outside knowledge
4. Cite sources when relevant
5. Always answer in the same language as the question"""

# Used when context=None but history is present. RAGService shouldn't
# normally reach this branch (condense_question() rewrites the
# follow-up question and retrieval proceeds as usual — see
# RAGService.ask_question), but it's kept as a safety net for any call
# made with context=None + history. _RAG_SYSTEM_PROMPT doesn't fit here
# because it talks about "the context" (ChromaDB chunks), which doesn't
# exist in this case — the same anti-hallucination rules, applied to
# the previous conversation instead of retrieved chunks.
_HISTORY_ONLY_SYSTEM_PROMPT = """You are a librarian assistant. You've already talked with the user about this earlier in this same conversation — the answer to their question should be in what was already said before.

STRICT RULES:
1. Answer ONLY with information that already appears in the previous conversation
2. Do NOT use your general knowledge or make up data that isn't there
3. If the answer isn't in the previous conversation, say so clearly, in the same language as the question
4. Always answer in the same language as the question"""


class GroqAdapter(LLMPort):
    """
    LLMPort implementation combining Groq (generation) with ChromaDB's
    local ONNX embedder (embeddings).

    Same Lazy Singleton pattern as OllamaAdapter: the clients
    (AsyncGroq, ONNXMiniLM_L6_V2) are created on first use, not in
    __init__, so the app starts even if the API key is missing or the
    embedding model hasn't been downloaded yet.
    """

    def __init__(self):
        self._client: Optional[AsyncGroq] = None
        self._embedder = None  # ONNXMiniLM_L6_V2, lazily typed to avoid importing onnxruntime at startup

    def _get_client(self) -> AsyncGroq:
        if self._client is None:
            if not settings.groq_api_key:
                raise RuntimeError(
                    "GROQ_API_KEY not configured. Add it to api/.env "
                    "(get one at https://console.groq.com/keys)."
                )
            self._client = AsyncGroq(api_key=settings.groq_api_key)
            logger.info("Initialized Groq client", model=settings.groq_model)
        return self._client

    def _get_embedder(self):
        """
        Loads the local embedding model (lazily), based on
        settings.embedding_backend:

        - 'onnx' (default): chromadb.utils.embedding_functions.ONNXMiniLM_L6_V2,
          the same model (all-MiniLM-L6-v2, 384 dims, mean pooling + L2
          normalization) but via onnxruntime, which is already a
          transitive dependency of chromadb. Adds nothing to
          requirements.txt. Recommended for the Render free tier:
          torch+transformers (the 'sentence_transformers' backend) alone
          add ~650MB on disk and enough RAM on import to trigger an OOM
          (512MB) before serving a single real request.
        - 'sentence_transformers': requires `pip install sentence-transformers`
          separately (deliberately kept out of requirements.txt, see the
          comment there for why). Meant for local development with more
          RAM available.

        The first call downloads the model if it's not cached (see the
        Dockerfile, which pre-downloads it at build time); subsequent
        calls reuse the instance.
        """
        if self._embedder is None:
            if settings.embedding_backend == "sentence_transformers":
                try:
                    from sentence_transformers import SentenceTransformer
                except ImportError as e:
                    raise RuntimeError(
                        "EMBEDDING_BACKEND=sentence_transformers but the package "
                        "isn't installed (deliberately not in requirements.txt, "
                        "see the comment there). Install it with `pip install sentence-transformers` "
                        "or switch to EMBEDDING_BACKEND=onnx."
                    ) from e
                self._embedder = SentenceTransformer(settings.embedding_model_name)
                logger.info(
                    "Initialized local embedding model (sentence-transformers)",
                    model=settings.embedding_model_name,
                    dimensions=self._embedder.get_sentence_embedding_dimension(),
                )
            else:
                from chromadb.utils.embedding_functions import ONNXMiniLM_L6_V2
                self._embedder = ONNXMiniLM_L6_V2()
                logger.info("Initialized local embedding model (ONNX)", model=settings.embedding_model_name)
        return self._embedder

    # ========================================================================
    # Text generation (Groq)
    # ========================================================================

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def generate_response(
        self,
        prompt: str,
        context: Optional[str] = None,
        history: Optional[str] = None,
        max_tokens: Optional[int] = None,
        temperature: float = 0.7,
        **kwargs,
    ) -> str:
        client = self._get_client()

        # "history"-only path (context=None, history present): a different
        # system prompt, focused on the previous conversation instead of
        # "the context" (which doesn't exist in this case). See _HISTORY_ONLY_SYSTEM_PROMPT.
        system_prompt = _HISTORY_ONLY_SYSTEM_PROMPT if (not context and history) else _RAG_SYSTEM_PROMPT
        messages = [{"role": "system", "content": system_prompt}]
        if history:
            # Block already formatted by ConversationService.get_history_prompt_block
            # (same text format OllamaAdapter uses, instead of native
            # user/assistant turns in the array — kept simple for v1, both
            # adapters consume the same string).
            messages.append({
                "role": "user",
                "content": f"PREVIOUS CONVERSATION (earlier turns, for context):\n{history}",
            })
        if context:
            messages.append({
                "role": "user",
                "content": f"CONTEXT (information from your knowledge base):\n{context}\n\nUSER QUESTION: {prompt}",
            })
        else:
            messages.append({"role": "user", "content": prompt})

        start_time = time.perf_counter()
        completion = await client.chat.completions.create(
            model=settings.groq_model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        duration = time.perf_counter() - start_time

        response = completion.choices[0].message.content

        LLM_REQUESTS.labels(operation="generate").inc()
        LLM_LATENCY.labels(operation="generate").observe(duration)
        logger.info("Generated response from Groq", duration_seconds=round(duration, 3), response_length=len(response))

        return response

    @retry(stop=stop_after_attempt(2), wait=wait_exponential(multiplier=1, min=1, max=5))
    async def extract_keywords(self, question: str) -> List[str]:
        try:
            client = self._get_client()

            extraction_prompt = (
                "Extract the keywords and proper nouns from this question.\n"
                "Return ONLY the keywords, one per line, with no explanations or numbering.\n"
                "If there's a movie title, book title, or proper noun, include it exactly as it appears.\n\n"
                f"Question: {question}\n\nKeywords:"
            )

            start_time = time.perf_counter()
            completion = await client.chat.completions.create(
                model=settings.groq_model,
                messages=[{"role": "user", "content": extraction_prompt}],
                temperature=0.1,
            )
            duration = time.perf_counter() - start_time

            raw = completion.choices[0].message.content or ""
            keywords = [
                line.strip().strip("-").strip("•").strip()
                for line in raw.strip().split("\n")
            ]
            keywords = [k for k in keywords if len(k) > 2]

            LLM_REQUESTS.labels(operation="extract_keywords").inc()
            LLM_LATENCY.labels(operation="extract_keywords").observe(duration)
            logger.info("Extracted keywords via Groq", keywords=keywords, count=len(keywords))

            return keywords

        except Exception as e:
            logger.warning("Failed to extract keywords via Groq", error=str(e))
            return []

    @retry(stop=stop_after_attempt(2), wait=wait_exponential(multiplier=1, min=1, max=5))
    async def is_catalog_question(self, question: str) -> bool:
        """See LLMPort.is_catalog_question — same prompt/criteria as OllamaAdapter."""
        try:
            client = self._get_client()

            classification_prompt = (
                "Classify the following question into a single category.\n\n"
                "CATALOG: the question asks for the total number, a listing, or a summary of "
                "ALL the documents in the knowledge base, as a collection. "
                "Examples: \"how many books do you know?\", \"how many books do you have?\", "
                "\"what documents do you have\", \"list the books\", \"what's in your knowledge base\".\n"
                "CONTENT: the question asks for information about ONE specific document (even if not "
                "explicitly named and implied by the conversation's context) — "
                "this includes questions asking for a QUANTITY about that particular document: "
                "pages, chapters, publication year, price, etc. Examples: "
                "\"who wrote 1984?\", \"what is Docker?\", \"summarize chapter 3\", "
                "\"how many pages does it have?\", \"how many chapters does this book have?\", "
                "\"what year was it published?\".\n\n"
                "Key rule to disambiguate: if the question asks for a quantity ABOUT ONE "
                "document (pages, chapters, year...) it's CONTENT, not CATALOG. It's only CATALOG "
                "if it asks for the number or listing of ALL the documents in the "
                "knowledge base as a whole.\n\n"
                "Answer with a single word: CATALOG or CONTENT. Nothing else.\n\n"
                f"Question: {question}\n\nCategory:"
            )

            start_time = time.perf_counter()
            completion = await client.chat.completions.create(
                model=settings.groq_model,
                messages=[{"role": "user", "content": classification_prompt}],
                temperature=0.0,
            )
            duration = time.perf_counter() - start_time

            raw = completion.choices[0].message.content or ""
            is_catalog = "CATALOG" in raw.strip().upper()

            LLM_REQUESTS.labels(operation="classify_intent").inc()
            LLM_LATENCY.labels(operation="classify_intent").observe(duration)
            logger.info("Classified question intent via Groq", is_catalog_question=is_catalog)

            return is_catalog

        except Exception as e:
            logger.warning("Failed to classify question intent via Groq, falling back to content pipeline", error=str(e))
            return False

    @retry(stop=stop_after_attempt(2), wait=wait_exponential(multiplier=1, min=1, max=5))
    async def condense_question(self, question: str, history: str) -> str:
        """See LLMPort.condense_question — same prompt/criteria as OllamaAdapter."""
        try:
            client = self._get_client()

            condense_prompt = (
                "Given the previous conversation and the user's follow-up question, "
                "rewrite the follow-up question as a standalone question that includes "
                "all the context needed to understand it without needing the previous "
                "conversation.\n\n"
                "If the follow-up question is ALREADY standalone (for example, it already "
                "explicitly mentions the document or topic it's about), return it "
                "EXACTLY AS IS, unchanged.\n\n"
                "Answer ONLY with the question (rewritten or unchanged), with no "
                "explanations, no quotes, no prefixes.\n\n"
                f"PREVIOUS CONVERSATION:\n{history}\n\n"
                f"FOLLOW-UP QUESTION: {question}\n\n"
                "STANDALONE QUESTION:"
            )

            start_time = time.perf_counter()
            completion = await client.chat.completions.create(
                model=settings.groq_model,
                messages=[{"role": "user", "content": condense_prompt}],
                temperature=0.0,
            )
            duration = time.perf_counter() - start_time

            condensed = (completion.choices[0].message.content or "").strip().strip('"')
            if not condensed:
                condensed = question

            LLM_REQUESTS.labels(operation="condense_question").inc()
            LLM_LATENCY.labels(operation="condense_question").observe(duration)
            logger.info("Condensed follow-up question via Groq", original=question, condensed=condensed)

            return condensed

        except Exception as e:
            logger.warning("Failed to condense question via Groq, using original", error=str(e))
            return question

    # ========================================================================
    # Embeddings (local, configurable backend — see _get_embedder)
    # ========================================================================

    async def generate_embedding(self, text: str) -> List[float]:
        vectors = await self.generate_embeddings_batch([text])
        return vectors[0]

    @staticmethod
    def _encode_sync(embedder, texts: List[str]) -> List[List[float]]:
        """
        Wraps the CPU-bound call to the embedder (runs in an executor,
        see generate_embeddings_batch). The two libraries expose a
        different API despite producing the same kind of vector (384
        normalized floats): sentence-transformers uses .encode(...) and
        returns a single 2D array; ONNXMiniLM_L6_V2 is called directly
        (__call__) and returns a list of 1D arrays, one per text.
        """
        if settings.embedding_backend == "sentence_transformers":
            vectors = embedder.encode(texts, batch_size=32, convert_to_numpy=True)
            return vectors.tolist()
        return [vector.tolist() for vector in embedder(texts)]

    async def generate_embeddings_batch(self, texts: List[str]) -> List[List[float]]:
        embedder = self._get_embedder()

        start_time = time.perf_counter()
        loop = asyncio.get_running_loop()
        vectors = await loop.run_in_executor(None, self._encode_sync, embedder, texts)
        duration = time.perf_counter() - start_time

        LLM_REQUESTS.labels(operation="embed_batch").inc()
        LLM_LATENCY.labels(operation="embed_batch").observe(duration)
        logger.info("Generated batch embeddings locally", count=len(texts), duration_seconds=round(duration, 3))

        return vectors

    # ========================================================================
    # Utilities
    # ========================================================================

    async def is_available(self) -> bool:
        """
        Only checks Groq (a lightweight call to /models).

        Deliberately does NOT load the local embedding model here: this
        function is called during FastAPI's startup (see lifespan in
        main.py), and uvicorn doesn't start listening on the port until
        startup finishes. Loading sentence-transformers here
        (synchronous, no timeout, can involve downloading the model from
        Hugging Face) used to block startup long enough for Render to
        time out the deploy ("no open ports detected") before the port
        ever opened. The embedding model still loads lazily on first
        real use (_get_embedder), as its docstring says.
        """
        if not settings.groq_api_key:
            logger.warning("Groq service unavailable: GROQ_API_KEY not set")
            return False

        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    "https://api.groq.com/openai/v1/models",
                    headers={"Authorization": f"Bearer {settings.groq_api_key}"},
                    timeout=5.0,
                )
            if response.status_code != 200:
                logger.warning("Groq returned unexpected status", status_code=response.status_code)
                return False
        except Exception as e:
            logger.error("Groq service unavailable", error=str(e))
            return False

        return True

    async def warm_up(self) -> None:
        """
        Preloads the local embedding model in a separate thread so the
        first real request (sync or chat) doesn't pay the cost of
        loading it. Runs as a background task after startup (see
        main.py), so a failure here must not crash the app: if something
        goes wrong, _get_embedder() will retry lazily on first real use
        and that error will propagate to the corresponding endpoint then.
        """
        try:
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(None, self._get_embedder)
        except Exception as e:
            logger.warning("Embedding model warm-up failed, will retry lazily on first use", error=str(e))

    def get_model_info(self) -> Dict[str, Any]:
        embedding_provider = (
            "sentence-transformers (local)"
            if settings.embedding_backend == "sentence_transformers"
            else "onnxruntime (local, via chromadb)"
        )
        return {
            "llm_model": settings.groq_model,
            "llm_provider": "groq",
            "embedding_model": settings.embedding_model_name,
            "embedding_provider": embedding_provider,
            "base_url": "https://api.groq.com/openai/v1",
        }
