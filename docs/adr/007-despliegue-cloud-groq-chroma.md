# ADR-007: Despliegue cloud gratuito con Groq y Chroma Cloud

**Estado:** Aceptada
**Fecha:** Agosto 2026
**Contexto adicional:** El TFM ya fue entregado y evaluado (ADR-001 a ADR-006 documentan el diseño original). Esta decisión aplica solo a una instancia pública de demo desplegada en Render, no cambia el modo de desarrollo local.

---

## Contexto

Tras la evaluación del TFM, se quiere alojar una demo pública en un servicio cloud gratuito (Render) que acepte imágenes Docker. El obstáculo principal es que la arquitectura original depende de dos componentes que no encajan en un free tier:

1. **Ollama nativo con GPU Metal** (ADR-002, ADR-006): requiere macOS con Apple Silicon corriendo permanentemente. Render no ofrece GPU ni acceso a hardware nativo — solo contenedores Linux.
2. **ChromaDB self-hosted con volumen Docker** (ADR-003): los servicios gratuitos de Render no tienen disco persistente. Un contenedor de ChromaDB ahí perdería los datos en cada redeploy o cada vez que el servicio "duerme" por inactividad (~15 min sin tráfico en el free tier).

Se necesitan sustitutos gratuitos para ambos, sin romper el setup local existente.

## Alternativas evaluadas

### LLM (sustituto de Ollama)

1. **Ollama en un contenedor de Render** — sin GPU, la inferencia en CPU es demasiado lenta para una demo interactiva; además los modelos (~2-4GB) complican el build/arranque en el free tier.
2. **Groq** — inferencia gratuita sobre modelos open-weight (Llama, gpt-oss, Qwen) en hardware LPU propio, extremadamente rápida, API compatible con OpenAI. **Limitación clave: no ofrece endpoint de embeddings**, solo chat completions.
3. **OpenAI/otros con coste** — descartado por requerir tarjeta y facturación, contrario al requisito de "gratuito".

### Embeddings (Groq no los provee)

1. **Sentence-transformers local (CPU)** — modelo pequeño (`all-MiniLM-L6-v2`, ~80MB, 384 dims) corriendo en el mismo contenedor de la API. Sin API key, sin límite de peticiones, sin dependencia externa adicional.
2. **API de embeddings de terceros** (Cohere, Gemini, HF Inference) — añade otra cuenta, otra clave, y otro punto de fallo externo por ahorrar los ~200-400MB de RAM que ocupa el modelo local. Se descarta por complejidad innecesaria a esta escala.

### Vector DB (sustituto de ChromaDB self-hosted)

1. **ChromaDB self-hosted en Render free** — descartado: sin disco persistente, los datos desaparecen en cada redeploy/sleep.
2. **Chroma Cloud** — mismo motor y cliente Python que ya usa el proyecto (`chromadb`), free tier hasta 1M embeddings sin pedir tarjeta al registrarse (verificado por el autor), persistencia real entre despliegues.
3. **Qdrant Cloud** — tier "free forever" con recursos fijos, pero cliente y API distintos: habría exigido reescribir `chromadb_adapter.py` en vez de solo cambiar la conexión. Descartado por mayor esfuerzo sin beneficio claro para este caso.

## Decisión

**Groq (LLM) + sentence-transformers local (embeddings) + Chroma Cloud (vector DB)**, implementados como adaptadores nuevos que no modifican los existentes:

- `GroqAdapter` (`adapters/outbound/groq_adapter.py`) implementa `LLMPort` completo componiendo dos motores: Groq para `generate_response`/`extract_keywords`, sentence-transformers local para `generate_embedding`/`generate_embeddings_batch`. `LLMPort` no se modifica — mezclar dos proveedores detrás de una interfaz es exactamente lo que la arquitectura hexagonal (ADR-001) permite sin tocar `RAGService` ni `SyncService`.
- `ChromaCloudAdapter` (`adapters/outbound/chromadb_cloud_adapter.py`) hereda de `ChromaDBAdapter` y sobreescribe únicamente `_get_client()` para usar `chromadb.CloudClient` en vez de `chromadb.HttpClient`. Toda la lógica de queries, formato columnar y query expansion se reutiliza sin duplicar.
- La selección de adaptador es configuración, no código: `settings.llm_provider` (`ollama` | `groq`) y `settings.vector_db_provider` (`chromadb_local` | `chroma_cloud`), leídos en `main.py` al hacer la inyección de dependencias. Los defaults reproducen el setup local existente sin cambios.

### Trade-off de privacidad (revisita ADR-003)

ADR-003 rechazó explícitamente Pinecone porque "los datos salen de la máquina". Esta decisión reintroduce ese mismo trade-off deliberadamente, pero **solo para la instancia pública de demo**: el desarrollo local (`docker-compose up`, `LLM_PROVIDER=ollama`, `VECTOR_DB_PROVIDER=chromadb_local`) sigue funcionando exactamente igual que antes, 100% en la máquina del usuario. La app en Render, por su propia naturaleza de demo pública, no tiene la misma necesidad de privacidad total que motivó la elección original.

## Consecuencias

**Positivas:**
- Despliegue 100% gratuito sin tarjeta de crédito en ninguno de los tres servicios (Render, Groq, Chroma Cloud).
- Groq es notablemente más rápido que Ollama en CPU (LPU dedicado).
- Cero cambios en `OllamaAdapter`, `ChromaDBAdapter`, `RAGService`, `SyncService` ni en los puertos — el trabajo local existente queda intacto y sigue siendo el default.
- El mismo Dockerfile de `api/` sirve para ambos entornos; solo cambian variables de entorno.

**Negativas:**
- Los embeddings cambian de dimensión (768 con `nomic-embed-text` → 384 con `all-MiniLM-L6-v2`): no son intercambiables, la colección de Chroma Cloud debe re-ingestarse desde cero, no se puede migrar el volumen local.
- `sentence-transformers` arrastra `torch` como dependencia — aumenta notablemente el tamaño de imagen y el consumo de RAM en arranque; en el free tier de Render (recursos limitados) esto es un riesgo a vigilar, no una garantía.
- Dos LLMs distintos (Ollama local, Groq en producción) pueden dar respuestas de calidad/estilo distintas para la misma pregunta — aceptable para una demo, pero es una divergencia real entre entornos.
- Chroma Cloud es un servicio relativamente nuevo (lanzado Q1 2026); su modelo de precios es *usage-based* más allá del free tier, sin límites publicados tan claros como los de un tier fijo — a vigilar si la demo recibe tráfico inesperado.
- La clave `"ollama"` se mantiene en la respuesta de `GET /health` (`services.ollama`) por compatibilidad con el frontend existente, aunque bajo `llm_provider=groq` representa la disponibilidad de Groq, no de un Ollama real.
