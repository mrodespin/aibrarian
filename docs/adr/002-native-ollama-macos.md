# ADR-002: Native Ollama on macOS for the local LLM

**Status:** Accepted
**Date:** November 2025

---

## Context

The RAG system needs a language model (LLM) for two tasks:
- **Embedding generation**: converting text into vectors for semantic search
- **Response generation**: answering questions grounded in retrieved context

The project has an implicit **privacy** requirement: user data must never leave the local machine. The development environment is also macOS with Apple Silicon.

## Alternatives evaluated

### 1. OpenAI API (GPT-4, text-embedding-ada-002)
- Better answer quality
- Requires an internet connection and a paid API key
- **Data leaves the machine** (violates the privacy requirement)
- Dependency on an external service

### 2. Ollama in Docker
- Isolation and reproducibility
- **No GPU access on macOS** (Docker doesn't expose Metal)
- Inference ~10x slower than native (CPU only)
- Higher memory usage

### 3. Native Ollama on macOS
- Direct access to **Apple Silicon GPU (Metal)**
- Fast inference (~10x vs. Docker/CPU)
- Simple installation via Homebrew
- 100% local data

## Decision

**Native Ollama on macOS**, because:

1. **Privacy**: data never leaves the machine. No third-party API keys, no calls to external APIs
2. **Performance**: Apple Silicon with Metal delivers fast inference for a 3B-parameter LLM (llama3.2)
3. **Simplicity**: `brew install ollama && ollama pull llama3.2` vs. configuring API keys and managing costs
4. **Independence**: no dependency on cloud services or recurring costs

### Models chosen

| Model | Task | Size | Rationale |
|-------|------|------|-----------|
| `llama3.2` | Response generation | ~2GB | Good quality/speed balance for 3B params |
| `nomic-embed-text` | Embeddings | ~275MB | 768 dimensions, optimized for semantic search |

## Consequences

**Positive:**
- Full data privacy
- No API costs
- Responses in ~2-5 seconds on Apple Silicon
- Works offline

**Negative:**
- Lower answer quality than GPT-4 (but sufficient for this use case)
- Requires macOS with Apple Silicon for optimal performance
- The user must download ~2.3GB of models on first install
