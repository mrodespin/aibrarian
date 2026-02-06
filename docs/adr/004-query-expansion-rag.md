# ADR-004: Query Expansion en el pipeline RAG

**Estado:** Aceptada
**Fecha:** Diciembre 2025

---

## Contexto

El pipeline RAG básico tiene una limitación conocida: la búsqueda semántica por embeddings funciona bien para preguntas conceptuales, pero pierde precisión cuando el usuario busca entidades concretas (nombres propios, siglas, términos técnicos específicos).

**Ejemplo del problema:**
- Pregunta: "¿Qué dice el documento sobre SOLID?"
- Embedding de la pregunta captura el concepto general
- Pero "SOLID" como término exacto puede no coincidir semánticamente con chunks que hablen de "Single Responsibility Principle"

## Alternativas evaluadas

### 1. Solo búsqueda semántica (baseline)
- Simple: embedding de la pregunta → búsqueda por coseno
- Funciona bien para preguntas generales
- Pierde precisión con nombres y términos específicos

### 2. Solo búsqueda por keywords (BM25/TF-IDF)
- Excelente para términos exactos
- No entiende sinónimos ni contexto semántico
- Retroceso a búsqueda pre-LLM

### 3. Búsqueda híbrida con Query Expansion
- El LLM extrae keywords/entidades de la pregunta
- Se combina búsqueda semántica con filtrado por keywords
- Lo mejor de ambos mundos

## Decisión

**Búsqueda híbrida con Query Expansion** implementada en `RAGService`:

1. El usuario hace una pregunta
2. El LLM (`extract_keywords`) analiza la pregunta y extrae entidades relevantes
3. Se genera el embedding de la pregunta original
4. ChromaDB recibe tanto el vector como los keywords para filtrado

```python
# RAGService.ask_question() - flujo simplificado
keywords = await self.llm.extract_keywords(question)     # Query Expansion
embedding = await self.llm.generate_embedding(question)   # Vectorización
results = await self.vector_db.similarity_search(
    query_embedding=embedding,
    keyword_filter=keywords    # Filtrado híbrido
)
```

## Consecuencias

**Positivas:**
- Mejora la precisión en preguntas con entidades concretas
- Compatible con el pipeline existente (añade un paso, no reemplaza)
- El LLM ya está disponible, no requiere infraestructura adicional
- Demostrable en la presentación como mejora técnica sobre RAG básico

**Negativas:**
- Añade una llamada extra al LLM (~0.5-1s de latencia adicional)
- La calidad de los keywords depende de la capacidad del modelo (llama3.2 3B)
- Más complejidad en el pipeline vs búsqueda simple
