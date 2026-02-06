# ADR-003: ChromaDB como base de datos vectorial

**Estado:** Aceptada
**Fecha:** Noviembre 2025

---

## Contexto

El sistema RAG necesita almacenar embeddings (vectores) y hacer búsquedas por similaridad semántica. La base de datos vectorial es un componente crítico del pipeline: recibe los vectores generados por Ollama y retorna los chunks más relevantes para cada consulta.

## Alternativas evaluadas

### 1. FAISS (Facebook AI Similarity Search)
- Librería de Meta, muy rápida para búsquedas
- Solo en memoria o ficheros locales, no tiene servidor
- Sin API REST, difícil de compartir entre servicios
- Sin persistencia robusta ni gestión de metadatos

### 2. Pinecone
- Servicio cloud gestionado, alta disponibilidad
- Requiere conexión a internet y API key
- **Los datos salen de la máquina** (viola privacidad)
- Costes recurrentes

### 3. Weaviate
- Open-source con servidor propio
- Más complejo de configurar que ChromaDB
- Mayor consumo de recursos
- Funcionalidades avanzadas innecesarias para el alcance del TFM

### 4. ChromaDB
- Open-source, diseñado específicamente para RAG
- API REST sencilla con imagen Docker oficial
- Persistencia con volúmenes Docker
- Búsqueda por similaridad + filtrado por metadatos

## Decisión

**ChromaDB** por:

1. **Simplicidad**: Una imagen Docker, un puerto, funciona
2. **Diseñado para RAG**: API orientada a documentos con chunks, embeddings y metadatos
3. **Persistencia local**: Los datos se quedan en la máquina via volúmenes Docker
4. **Filtrado por metadatos**: Permite combinar búsqueda semántica con filtros (source, page, type) - esencial para Query Expansion
5. **Ecosistema LangChain**: Integración nativa con LangChain, que es el framework RAG del proyecto

### Configuración

```yaml
# docker-compose.yml
chromadb:
  image: chromadb/chroma:0.5.20
  ports:
    - "8001:8000"    # 8001 en host para no conflictar con la API
  volumes:
    - chroma_data:/chroma/chroma  # Persistencia
```

## Consecuencias

**Positivas:**
- Setup en 1 comando (`docker-compose up -d chromadb`)
- Datos persisten entre reinicios gracias al volumen Docker
- API REST permite acceso desde la API en Docker y scripts CLI
- Búsqueda híbrida (semántica + keywords) funciona out-of-the-box

**Negativas:**
- No escala horizontalmente (suficiente para el TFM)
- Sin replicación ni alta disponibilidad
- Depende de Docker (requisito del proyecto de todas formas)
