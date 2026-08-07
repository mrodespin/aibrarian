# ADR-003: ChromaDB as the vector database

**Status:** Accepted
**Date:** November 2025

---

## Context

The RAG system needs to store embeddings (vectors) and run semantic similarity searches. The vector database is a critical pipeline component: it receives the vectors Ollama generates and returns the most relevant chunks for each query.

## Alternatives evaluated

### 1. FAISS (Facebook AI Similarity Search)
- Meta's library, very fast for searches
- In-memory or local files only, no server
- No REST API, hard to share between services
- No robust persistence or metadata management

### 2. Pinecone
- Managed cloud service, high availability
- Requires an internet connection and an API key
- **Data leaves the machine** (violates privacy)
- Recurring costs

### 3. Weaviate
- Open-source with its own server
- More complex to configure than ChromaDB
- Higher resource usage
- Advanced features unnecessary for this project's scope

### 4. ChromaDB
- Open-source, purpose-built for RAG
- Simple REST API with an official Docker image
- Persistence via Docker volumes
- Similarity search + metadata filtering

## Decision

**ChromaDB**, because:

1. **Simplicity**: one Docker image, one port, it just works
2. **Built for RAG**: document-oriented API with chunks, embeddings and metadata
3. **Local persistence**: data stays on the machine via Docker volumes
4. **Metadata filtering**: lets you combine semantic search with filters (source, page, type) — essential for Query Expansion
5. **LangChain ecosystem**: native integration with LangChain, the project's RAG framework

### Configuration

```yaml
# docker-compose.yml
chromadb:
  image: chromadb/chroma:0.5.20
  ports:
    - "8001:8000"    # 8001 on the host to avoid clashing with the API
  volumes:
    - chroma_data:/chroma/chroma  # Persistence
```

## Consequences

**Positive:**
- Setup in 1 command (`docker-compose up -d chromadb`)
- Data survives restarts thanks to the Docker volume
- The REST API allows access from the Dockerized API and CLI scripts alike
- Hybrid search (semantic + keywords) works out of the box

**Negative:**
- Doesn't scale horizontally (fine for this project)
- No replication or high availability
- Depends on Docker (already a project requirement anyway)
