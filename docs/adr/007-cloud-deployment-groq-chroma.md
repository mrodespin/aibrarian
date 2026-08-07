# ADR-007: Free cloud deployment with Groq and Chroma Cloud

**Status:** Accepted
**Date:** August 2026
**Additional context:** this decision was made after the project's original local-first design was already complete (ADR-001 through ADR-006 document that original design). It applies only to an instance deployed on Render (reachable outside `localhost`, for the author's own testing) — it doesn't change the local development mode.

---

## Context

After the initial local-first version was done, the goal was to have an instance reachable on a free cloud service (Render) that accepts Docker images, without depending on a laptop being on with Ollama running. The main obstacle is that the original architecture depends on two components that don't fit a free tier:

1. **Native Ollama with the Metal GPU** (ADR-002, ADR-006): requires macOS with Apple Silicon running permanently. Render offers no GPU or native hardware access — only Linux containers.
2. **Self-hosted ChromaDB with a Docker volume** (ADR-003): Render's free services have no persistent disk. A ChromaDB container there would lose its data on every redeploy or whenever the service "sleeps" from inactivity (~15 min with no traffic on the free tier).

Free substitutes were needed for both, without breaking the existing local setup.

## Alternatives evaluated

### LLM (replacing Ollama)

1. **Ollama in a Render container** — with no GPU, CPU inference is too slow for an interactive demo; the models (~2-4GB) also complicate the build/startup on the free tier.
2. **Groq** — free inference over open-weight models (Llama, gpt-oss, Qwen) on its own LPU hardware, extremely fast, OpenAI-compatible API. **Key limitation: no embeddings endpoint**, chat completions only.
3. **OpenAI/other paid options** — ruled out for requiring a card and billing, contrary to the "free" requirement.

### Embeddings (Groq doesn't provide them)

1. **Local sentence-transformers (CPU)** — a small model (`all-MiniLM-L6-v2`, ~80MB, 384 dims) running in the same API container. No API key, no request limits, no extra external dependency.
2. **Third-party embeddings API** (Cohere, Gemini, HF Inference) — adds another account, another key, and another external point of failure just to save the ~200-400MB of RAM the local model uses. Ruled out as unnecessary complexity at this scale.

### Vector DB (replacing self-hosted ChromaDB)

1. **Self-hosted ChromaDB on Render's free tier** — ruled out: with no persistent disk, data disappears on every redeploy/sleep.
2. **Chroma Cloud** — the same engine and Python client the project already uses (`chromadb`), a free tier up to 1M embeddings with no card required to sign up (verified by the author), real persistence across deployments.
3. **Qdrant Cloud** — a "free forever" tier with fixed resources, but a different client and API: would have required rewriting `chromadb_adapter.py` instead of just changing the connection. Ruled out for the extra effort with no clear benefit here.

## Decision

**Groq (LLM) + local sentence-transformers (embeddings) + Chroma Cloud (vector DB)**, implemented as new adapters that don't modify the existing ones:

- `GroqAdapter` (`adapters/outbound/groq_adapter.py`) implements the full `LLMPort` by composing two engines: Groq for `generate_response`/`extract_keywords`, local sentence-transformers for `generate_embedding`/`generate_embeddings_batch`. `LLMPort` itself isn't modified — mixing two providers behind one interface is exactly what hexagonal architecture (ADR-001) allows without touching `RAGService` or `SyncService`.
- `ChromaCloudAdapter` (`adapters/outbound/chromadb_cloud_adapter.py`) inherits from `ChromaDBAdapter` and only overrides `_get_client()` to use `chromadb.CloudClient` instead of `chromadb.HttpClient`. All the query logic, columnar format and query expansion are reused without duplication.
- Adapter selection is configuration, not code: `settings.llm_provider` (`ollama` | `groq`) and `settings.vector_db_provider` (`chromadb_local` | `chroma_cloud`), read in `main.py` during dependency injection. The defaults reproduce the existing local setup unchanged.

### Privacy trade-off (revisiting ADR-003)

ADR-003 explicitly rejected Pinecone because "data leaves the machine". This decision deliberately reintroduces that same trade-off, but **only for the instance deployed on Render**: local development (`docker-compose up`, `LLM_PROVIDER=ollama`, `VECTOR_DB_PROVIDER=chromadb_local`) keeps working exactly as before, 100% on the user's machine. The Render instance, being for the author's own testing rather than a service with real users, doesn't have the same need for total privacy that motivated the original choice.

## Consequences

**Positive:**
- 100% free deployment, no credit card on any of the three services (Render, Groq, Chroma Cloud).
- Groq is noticeably faster than Ollama on CPU (dedicated LPU).
- Zero changes to `OllamaAdapter`, `ChromaDBAdapter`, `RAGService`, `SyncService` or the ports — the existing local setup stays intact and remains the default.
- The same `api/` Dockerfile serves both environments; only environment variables change.

**Negative:**
- Embeddings change dimension (768 with `nomic-embed-text` → 384 with `all-MiniLM-L6-v2`): they aren't interchangeable, the Chroma Cloud collection must be re-ingested from scratch, the local volume can't be migrated over.
- `sentence-transformers` drags in `torch` as a dependency — noticeably increases image size and RAM usage at startup; on Render's free tier (limited resources) this is a risk to watch, not a guarantee.
- Two different LLMs (local Ollama, Groq in production) can give answers of different quality/style for the same question — acceptable for a demo, but a real divergence between environments.
- Chroma Cloud is a relatively new service (launched Q1 2026); its pricing beyond the free tier is usage-based, without limits as clearly published as a fixed tier's — worth watching if the demo gets unexpected traffic.
- The `"ollama"` key is kept in `GET /health`'s response (`services.ollama`) for compatibility with the existing frontend, even though under `llm_provider=groq` it represents Groq's availability, not a real Ollama's.
