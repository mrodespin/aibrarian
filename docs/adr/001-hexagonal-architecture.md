# ADR-001: Hexagonal Architecture (Ports and Adapters)

**Status:** Accepted
**Date:** November 2025

---

## Context

The project needs a RAG system that integrates multiple external services (LLM, vector database, document processors) and multiple data sources (PDFs, Notion). It needs an architecture that:

- Allows swapping implementations without modifying business logic
- Makes testing easy with mocks and test doubles
- Stays maintainable and extensible to future data sources by a single developer

## Alternatives evaluated

### 1. MVC (Model-View-Controller)
- Widely known pattern
- Tends to produce fat controllers with logic coupled to frameworks
- Hard to isolate business logic from external services

### 2. Layered Architecture
- Simple and direct: Controller → Service → Repository
- Dependencies flow in one direction
- But layers tend to leak abstractions and create vertical coupling

### 3. Hexagonal Architecture (Ports and Adapters)
- Business logic isolated at the center (the domain)
- Dependencies point inward (Dependency Inversion)
- External services are interchangeable adapters

## Decision

**Hexagonal Architecture**, for these reasons:

1. **Testability**: The services (`RAGService`, `SyncService`) depend on abstract ports (`LLMPort`, `VectorDBPort`, `DocumentProcessorPort`), letting tests inject mocks without touching real services
2. **Extensibility**: Adding Notion as a data source only required a new adapter (`NotionProcessorAdapter`) implementing the same `DocumentProcessorPort`
3. **Decoupling**: If Ollama gets swapped for OpenAI someday, only `OllamaAdapter` needs replacing, `RAGService` stays untouched
4. **Industry-standard pattern**: A well-recognized approach (DDD, SOLID, Clean Architecture) that's easy for future contributors to onboard onto

## Resulting structure

```
api/app/
├── core/                    # The hexagon (pure logic)
│   ├── domain/models.py     # Entities: Document, Chunk, Query
│   ├── ports/               # Abstract interfaces (ABC)
│   └── services/            # RAGService, SyncService
└── adapters/outbound/       # Concrete implementations
    ├── ollama_adapter.py
    ├── chromadb_adapter.py
    ├── pdf_processor_adapter.py
    └── notion_processor_adapter.py
```

## Consequences

**Positive:**
- 66 unit tests made possible thanks to port mocks
- Notion was integrated in ~1 day by reusing the existing pipeline
- The domain code imports no external library at all

**Negative:**
- More upfront complexity than a simple monolithic script
- More files and abstractions for a single-person project
- A learning curve for anyone unfamiliar with the pattern
