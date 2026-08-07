# ADR-006: Docker for services, native Ollama

**Status:** Accepted
**Date:** February 2026
**Supersedes:** The earlier decision to run everything in Docker (Mode A/B)

---

## Context

The project originally supported two installation modes:
- **Mode A**: everything in Docker (Ollama + ChromaDB + API)
- **Mode B**: native Ollama + ChromaDB in Docker + local API

That duality caused problems:
- Different `.env` configuration depending on the mode (OLLAMA_BASE_URL)
- Complex setup scripts with mode selection
- Duplicated documentation for each mode
- Recurring errors from misconfiguration

The decision was made to simplify down to a single configuration.

## Alternatives evaluated

### 1. Everything in Docker (former Mode A)
- Reproducible and isolated
- **Ollama in Docker has no GPU access on macOS** (Metal isn't available)
- Inference ~10x slower (CPU only)
- Simpler to document (a single `docker-compose up`)

### 2. Everything native (no Docker)
- Maximum performance
- ChromaDB requires manual installation or pip
- No automated persistence
- Harder to reproduce

### 3. Hybrid: ChromaDB + API in Docker, native Ollama
- Ollama takes advantage of the Metal GPU (~10x faster)
- ChromaDB and API in Docker via `docker-compose up -d`
- One mode = one configuration
- The API in Docker uses `host.docker.internal` to reach Ollama on the host

## Decision

**ChromaDB + API in Docker, native Ollama**, because:

1. **Performance**: native Ollama with the Metal GPU is ~10x faster than in Docker (CPU)
2. **Simplicity**: a single installation mode, a single set of docs
3. **Reproducibility**: `docker-compose up -d` consistently brings up ChromaDB + API
4. **Ease of setup**: getting started only requires:
   - Installing Ollama (`brew install ollama`)
   - Running `docker-compose up -d`
   - Running `cd frontend && npm run dev`

### Network architecture

```
┌─────────────────────────────────────────────┐
│              macOS Host                      │
│                                             │
│  ┌─────────┐                                │
│  │ Ollama  │ :11434 (GPU Metal)             │
│  └────▲────┘                                │
│       │ host.docker.internal                │
│  ┌────┼────────────────────────────┐        │
│  │ Docker                          │        │
│  │  ┌──────┐    ┌──────────┐      │        │
│  │  │ API  │───▶│ ChromaDB │      │        │
│  │  │:8000 │    │  :8000   │      │        │
│  │  └──────┘    └──────────┘      │        │
│  └─────────────────────────────────┘        │
│       │                                     │
│  ┌────▼────┐                                │
│  │Frontend │ :5173 (npm run dev)            │
│  └─────────┘                                │
└─────────────────────────────────────────────┘
```

## Consequences

**Positive:**
- Eliminated the mode system (A/B) and all its complexity
- Setup scripts cut from 857 to 446 lines
- A single `.env.example` with no conditionals
- Can be installed in under 10 minutes

**Negative:**
- Requires macOS with Apple Silicon for Ollama's optimal performance
- The API in Docker has minimal network latency connecting to Ollama via `host.docker.internal`
- If Ollama isn't running, `docker-compose up` still starts but the API reports Ollama as unavailable
