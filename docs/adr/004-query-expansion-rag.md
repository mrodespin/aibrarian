# ADR-004: Query Expansion in the RAG pipeline

**Status:** Accepted
**Date:** December 2025

---

## Context

The basic RAG pipeline has a known limitation: semantic search via embeddings works well for conceptual questions, but loses precision when the user is looking for specific entities (proper nouns, acronyms, specific technical terms).

**Example of the problem:**
- Question: "What does the document say about SOLID?"
- The question's embedding captures the general concept
- But "SOLID" as an exact term may not semantically match chunks that talk about "Single Responsibility Principle"

## Alternatives evaluated

### 1. Semantic search only (baseline)
- Simple: embed the question → cosine search
- Works well for general questions
- Loses precision with specific names and terms

### 2. Keyword search only (BM25/TF-IDF)
- Excellent for exact terms
- Doesn't understand synonyms or semantic context
- A step back to pre-LLM search

### 3. Hybrid search with Query Expansion
- The LLM extracts keywords/entities from the question
- Combines semantic search with keyword filtering
- Best of both worlds

## Decision

**Hybrid search with Query Expansion**, implemented in `RAGService`:

1. The user asks a question
2. The LLM (`extract_keywords`) analyzes the question and extracts relevant entities
3. The original question's embedding is generated
4. ChromaDB receives both the vector and the keywords for filtering

```python
# RAGService.ask_question() - simplified flow
keywords = await self.llm.extract_keywords(question)     # Query Expansion
embedding = await self.llm.generate_embedding(question)   # Vectorization
results = await self.vector_db.similarity_search(
    query_embedding=embedding,
    keyword_filter=keywords    # Hybrid filtering
)
```

## Consequences

**Positive:**
- Improves precision on questions with specific entities
- Compatible with the existing pipeline (adds a step, doesn't replace one)
- The LLM is already available, no extra infrastructure needed
- A clear, demonstrable technical improvement over basic RAG

**Negative:**
- Adds an extra LLM call (~0.5-1s of additional latency)
- Keyword quality depends on the model's capability (llama3.2 3B)
- More pipeline complexity than plain search
