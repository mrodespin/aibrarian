# /api/app/adapters/outbound/ollama_adapter.py
"""
Adaptador Ollama - Implementación concreta de LLMPort - TFM Bibliotecario-IA

Este adaptador conecta el sistema con Ollama (servidor LLM local).
Es la implementación REAL del contrato definido en LLMPort.

¿Qué es Ollama?
- Servidor local que ejecuta modelos LLM sin necesidad de cloud
- Instalado en la máquina del usuario
- Accesible por HTTP en localhost:11434
- Modelos usados:
    - llama3.2: modelo conversacional (genera texto)
    - nomic-embed-text: modelo de embeddings (vectoriza texto)

¿Por qué usar LangChain?
- Proporciona clases OllamaLLM y OllamaEmbeddings
- Abstrae los detalles de la API de Ollama
- Métodos async integrados (ainvoke, aembed_query)
- Si cambiamos a OpenAI, solo cambiaríamos este adaptador

Patrones implementados:
- Lazy Initialization: los clientes solo se crean cuando se necesitan
- Retry con Exponential Backoff: reintenta automáticamente en fallos
- Singleton por campo: cada cliente se crea una sola vez

Equivalente en TypeScript:
    class OllamaAdapter implements LLMPort {
        private llm: OllamaLLM | null = null;
        private embeddings: OllamaEmbeddings | null = null;

        async generateResponse(prompt, context?, ...): Promise<string> { ... }
        async generateEmbedding(text): Promise<number[]> { ... }
        async generateEmbeddingsBatch(texts): Promise<number[][]> { ... }
        async isAvailable(): Promise<boolean> { ... }
        getModelInfo(): Record<string, any> { ... }
    }
"""

# ============================================================================
# IMPORTS
# ============================================================================
from typing import List, Optional, Dict, Any
import time
import httpx  # Cliente HTTP async (equivalente a axios en JS)

# tenacity: librería para retries automáticos con estrategias de espera
from tenacity import retry, stop_after_attempt, wait_exponential

# LangChain: framework que abstrae la comunicación con diferentes LLMs
from langchain_ollama import OllamaLLM, OllamaEmbeddings

# Importamos el PUERTO (interfaz) que implementamos
from app.core.ports.llm_port import LLMPort
from app.config.settings import settings

# Observabilidad: logging estructurado y métricas
from app.core.observability import get_logger, LLM_REQUESTS, LLM_LATENCY


logger = get_logger(__name__)


# ============================================================================
# ADAPTADOR OLLAMA
# ============================================================================
class OllamaAdapter(LLMPort):
    """
    Implementación concreta de LLMPort usando Ollama via LangChain.

    Esta clase es el ÚNICO lugar del sistema que conoce detalles de Ollama.
    El resto del código solo habla con la interfaz LLMPort.

    Dos clientes internos:
    - _llm: OllamaLLM → modelo llama3.2 para generar texto
    - _embeddings: OllamaEmbeddings → modelo nomic-embed-text para vectorizar

    Ambos se conectan al mismo servidor Ollama (localhost:11434)
    pero son modelos diferentes con funciones distintas.
    """

    def __init__(self):
        """
        Inicializa el adaptador con lazy initialization.

        NO se conecta a Ollama aquí. Los clientes se crean
        la primera vez que se necesitan (_get_llm, _get_embeddings).

        ¿Por qué lazy?
        - Si Ollama no está corriendo al iniciar la app, no falla inmediatamente
        - Solo falla cuando realmente se intenta usar el modelo
        - Equivalente JS: private llm: OllamaLLM | null = null
        """
        self._llm = None
        self._embeddings = None

    def _get_llm(self) -> OllamaLLM:
        """
        Obtiene o crea la instancia del cliente LLM (Singleton por campo).

        PATRÓN: Lazy Singleton
        - Primera llamada: crea el cliente y lo guarda en self._llm
        - Llamadas siguientes: devuelve el mismo cliente
        - Evita crear múltiples conexiones al servidor

        Equivalente JS:
            private getLLM(): OllamaLLM {
                if (!this.llm) this.llm = new OllamaLLM({...});
                return this.llm;
            }

        Returns:
            OllamaLLM: Cliente configurado con modelo llama3.2
        """
        if self._llm is None:
            try:
                self._llm = OllamaLLM(
                    base_url=settings.ollama_base_url,       # http://localhost:11434
                    model=settings.ollama_model,             # llama3.2
                    temperature=settings.llm_temperature,   # 0.3 (precisión)
                    timeout=settings.ollama_timeout          # segundos de espera
                )
                logger.info("Initialized Ollama LLM", model=settings.ollama_model)
            except Exception as e:
                logger.error("Failed to initialize Ollama LLM", error=str(e))
                raise  # Re-lanza la excepción después de loguear
        return self._llm

    def _get_embeddings(self) -> OllamaEmbeddings:
        """
        Obtiene o crea la instancia del cliente de Embeddings (Singleton por campo).

        Mismo patrón lazy que _get_llm, pero para el modelo de embeddings.
        Modelo: nomic-embed-text (especializado en crear vectores)

        Returns:
            OllamaEmbeddings: Cliente configurado con modelo nomic-embed-text
        """
        if self._embeddings is None:
            try:
                self._embeddings = OllamaEmbeddings(
                    base_url=settings.ollama_base_url,            # http://localhost:11434
                    model=settings.ollama_embedding_model         # nomic-embed-text
                )
                logger.info("Initialized Ollama Embeddings", model=settings.ollama_embedding_model)
            except Exception as e:
                logger.error("Failed to initialize Ollama Embeddings", error=str(e))
                raise
        return self._embeddings

    # ========================================================================
    # MÉTODOS PRINCIPALES - Implementación de LLMPort
    # ========================================================================

    # PATRÓN: @retry con Exponential Backoff
    # - stop_after_attempt(3): máximo 3 intentos antes de fallar
    # - wait_exponential: espera entre intentos crece exponencialmente
    #   multiplier=1, min=2, max=10 → esperas: 2s, 4s, 8s (capped en 10s)
    # ¿Por qué? Si Ollama está ocupado procesando otra solicitud,
    # en lugar de fallar inmediatamente, esperamos y reintentamos.
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10)
    )
    async def generate_response(
        self,
        prompt: str,
        context: Optional[str] = None,
        max_tokens: Optional[int] = None,
        temperature: float = 0.7,
        **kwargs
    ) -> str:
        """
        Genera una respuesta de texto usando Ollama/llama3.2.

        ESTE ES EL PUNTO CLAVE DEL RAG: aquí se construye el prompt
        que combina la pregunta con el contexto de los chunks.

        El LLM recibe un prompt estructurado así:
            "Context information: [chunks de ChromaDB]
             Question: [pregunta del usuario]
             Answer based on the context above:"

        Esta estructura le indica al LLM que debe basar su respuesta
        SOLO en el contexto proporcionado, no en su conocimiento general.

        Args:
            prompt: Pregunta del usuario
            context: Contexto (chunks recuperados por ChromaDB)
            max_tokens: Límite de tokens (no usado directamente aquí)
            temperature: Creatividad del modelo
            **kwargs: Parámetros adicionales para el modelo

        Returns:
            str: Respuesta generada por llama3.2
        """
        try:
            # Obtiene el cliente LLM (lazy, solo crea si es la primera vez)
            llm = self._get_llm()

            # ============================================================
            # CONSTRUCCIÓN DEL PROMPT
            # ============================================================
            # Si hay contexto (chunks de ChromaDB), se estructura el prompt
            # para que el LLM use esa información como base
            if context:
                full_prompt = f"""Eres un asistente bibliotecario que SOLO responde usando la información proporcionada en el contexto.

REGLAS ESTRICTAS:
1. SOLO usa la información del contexto para responder
2. NO uses tu conocimiento general o información externa
3. Si la información no está en el contexto, di "No tengo información sobre eso en mi base de conocimientos"
4. Cita las fuentes cuando sea relevante
5. Responde en el mismo idioma que la pregunta

CONTEXTO (información de tu base de conocimientos):
{context}

PREGUNTA DEL USUARIO: {prompt}

RESPUESTA (basada ÚNICAMENTE en el contexto anterior):"""
            else:
                # Sin contexto: la pregunta se envía directa al LLM
                # (el LLM responderá con su conocimiento general)
                full_prompt = prompt

            # ============================================================
            # LLAMADA AL MODELO
            # ============================================================
            # ainvoke() es el método async de LangChain para invocar el LLM
            # "a" de ainvoke = async (vs invoke que es síncrono)
            # Equivalente: await llm.invoke(prompt) en versión async
            start_time = time.perf_counter()
            response = await llm.ainvoke(
                full_prompt,
                temperature=temperature,
                **kwargs  # Parámetros adicionales (top_p, etc.)
            )
            duration = time.perf_counter() - start_time

            # Registrar métricas
            LLM_REQUESTS.labels(operation='generate').inc()
            LLM_LATENCY.labels(operation='generate').observe(duration)

            logger.info(
                "Generated response from Ollama",
                duration_seconds=round(duration, 3),
                response_length=len(response)
            )
            return response

        except Exception as e:
            logger.error("Failed to generate response", error=str(e))
            raise  # Re-lanza para que @retry pueda reintentar

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10)
    )
    async def generate_embedding(self, text: str) -> List[float]:
        """
        Genera un embedding para un solo texto usando nomic-embed-text.

        Usado para vectorizar la PREGUNTA del usuario antes de buscar
        en ChromaDB.

        ¿Diferencia entre aembed_query y aembed_documents?
        - aembed_query: para textos de búsqueda (preguntas)
        - aembed_documents: para textos a almacenar (chunks)
        LangChain puede aplicar optimizaciones diferentes según el tipo.

        Args:
            text: Texto a vectorizar (ej: pregunta del usuario)

        Returns:
            List[float]: Vector de ~768 números flotantes
        """
        try:
            embeddings = self._get_embeddings()

            # aembed_query: embedding async para queries/preguntas
            start_time = time.perf_counter()
            embedding = await embeddings.aembed_query(text)
            duration = time.perf_counter() - start_time

            # Registrar métricas
            LLM_REQUESTS.labels(operation='embed').inc()
            LLM_LATENCY.labels(operation='embed').observe(duration)

            logger.debug("Generated embedding", dimension=len(embedding), duration_seconds=round(duration, 3))
            return embedding

        except Exception as e:
            logger.error("Failed to generate embedding", error=str(e))
            raise

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10)
    )
    async def generate_embeddings_batch(self, texts: List[str]) -> List[List[float]]:
        """
        Genera embeddings para múltiples textos en lote.

        Usado durante la INGESTA de documentos para vectorizar
        todos los chunks de un PDF de una sola vez.

        aembed_documents: embedding async para documentos/chunks
        Es más eficiente que llamar a aembed_query N veces.

        Args:
            texts: Lista de textos a vectorizar (chunks del documento)

        Returns:
            List[List[float]]: Lista de vectores, mismo orden que la entrada
        """
        try:
            embeddings = self._get_embeddings()

            # aembed_documents: embedding async en batch para documentos
            start_time = time.perf_counter()
            embedding_vectors = await embeddings.aembed_documents(texts)
            duration = time.perf_counter() - start_time

            # Registrar métricas
            LLM_REQUESTS.labels(operation='embed_batch').inc()
            LLM_LATENCY.labels(operation='embed_batch').observe(duration)

            logger.info(
                "Generated batch embeddings",
                count=len(embedding_vectors),
                duration_seconds=round(duration, 3)
            )
            return embedding_vectors

        except Exception as e:
            logger.error("Failed to generate batch embeddings", error=str(e), batch_size=len(texts))
            raise

    async def is_available(self) -> bool:
        """
        Verifica si el servidor Ollama está activo y respondiendo.

        Hace una llamada HTTP real al endpoint /api/tags de Ollama.
        Este endpoint lista los modelos disponibles y es ligero.

        ¿Por qué httpx y no LangChain?
        - Es un simple health check, no necesita el framework completo
        - httpx es más directo para verificar si el servidor responde
        - async with: context manager que cierra la conexión automáticamente
          (equivalente JS: con try/finally para limpiar recursos)

        Returns:
            bool: True si Ollama responde con status 200
        """
        try:
            # httpx.AsyncClient: cliente HTTP async (como axios en JS)
            # async with: se abre y cierra automáticamente (context manager)
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{settings.ollama_base_url}/api/tags",  # endpoint de Ollama
                    timeout=5.0  # 5 segundos máximo de espera
                )
                if response.status_code == 200:
                    logger.info("Ollama service is available", base_url=settings.ollama_base_url)
                    return True
                else:
                    logger.warning("Ollama returned unexpected status", status_code=response.status_code)
                    return False

        except Exception as e:
            # Cualquier error (timeout, conexión rechazada, etc.) = no disponible
            logger.error("Ollama service unavailable", error=str(e), base_url=settings.ollama_base_url)
            return False

    def get_model_info(self) -> Dict[str, Any]:
        """
        Devuelve información sobre los modelos Ollama configurados.

        NO es async porque solo lee valores de settings (memoria).
        No hace ninguna llamada externa.

        Returns:
            Dict con la configuración actual de los modelos
        """
        return {
            "llm_model": settings.ollama_model,                # llama3.2
            "embedding_model": settings.ollama_embedding_model, # nomic-embed-text
            "base_url": settings.ollama_base_url,               # http://localhost:11434
            "temperature": settings.llm_temperature,            # 0.3
            "timeout": settings.ollama_timeout                  # segundos
        }

    @retry(
        stop=stop_after_attempt(2),
        wait=wait_exponential(multiplier=1, min=1, max=5)
    )
    async def extract_keywords(self, question: str) -> List[str]:
        """
        Extrae palabras clave y entidades de una pregunta usando el LLM.

        TÉCNICA: Query Expansion
        El LLM identifica nombres propios, títulos, y términos clave
        que pueden usarse para filtrar documentos antes de la búsqueda semántica.

        El prompt está diseñado para:
        - Extraer entidades nombradas (películas, personas, lugares, etc.)
        - Devolver formato parseable (una keyword por línea)
        - Ser rápido (temperatura baja, respuesta corta)

        Args:
            question: Pregunta del usuario

        Returns:
            List[str]: Keywords extraídas, vacía si no hay o hay error
        """
        try:
            llm = self._get_llm()

            # Prompt optimizado para extracción de keywords
            extraction_prompt = f"""Extrae las palabras clave y nombres propios de esta pregunta.
Devuelve SOLO las keywords, una por línea, sin explicaciones ni numeración.
Si hay un título de película, libro, o nombre propio, inclúyelo exactamente como aparece.

Pregunta: {question}

Keywords:"""

            start_time = time.perf_counter()
            response = await llm.ainvoke(
                extraction_prompt,
                temperature=0.1  # Muy bajo para respuestas consistentes
            )
            duration = time.perf_counter() - start_time

            # Parsear respuesta: dividir por líneas y limpiar
            keywords = []
            for line in response.strip().split('\n'):
                keyword = line.strip().strip('-').strip('•').strip()
                # Filtrar líneas vacías y keywords muy cortas
                if keyword and len(keyword) > 2:
                    keywords.append(keyword)

            # Registrar métricas
            LLM_REQUESTS.labels(operation='extract_keywords').inc()
            LLM_LATENCY.labels(operation='extract_keywords').observe(duration)

            logger.info(
                "Extracted keywords from question",
                keywords=keywords,
                count=len(keywords),
                duration_seconds=round(duration, 3)
            )
            return keywords

        except Exception as e:
            logger.warning("Failed to extract keywords", error=str(e))
            # En caso de error, devolvemos lista vacía (fallback a búsqueda semántica pura)
            return []
