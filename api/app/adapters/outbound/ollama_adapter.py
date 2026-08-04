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

    def _build_full_prompt(
        self,
        prompt: str,
        context: Optional[str],
        history: Optional[str]
    ) -> str:
        """
        Construye el prompt completo que se envía al modelo, combinando
        (si existen) el historial de la conversación y el contexto
        recuperado de ChromaDB con la pregunta del usuario.

        Factorizado como método propio porque tanto generate_response()
        como stream_response() necesitan exactamente el mismo prompt — la
        única diferencia entre ambos es cómo se consume la respuesta del
        modelo (de golpe vs. en streaming), no cómo se construye la pregunta.

        Args:
            prompt: Pregunta del usuario
            context: Contexto (chunks recuperados por ChromaDB), o None
            history: Turnos previos de la conversación ya formateados
                     (ver ConversationService.get_history_prompt_block), o None

        Returns:
            str: prompt completo listo para enviar al modelo
        """
        # Si hay historial (turnos previos de la conversación), se antepone
        # al resto del prompt para que el LLM pueda resolver preguntas de
        # seguimiento ("¿puedes ampliar eso?"). Nota: esto SOLO afecta a la
        # generación — la recuperación de chunks sigue basándose únicamente
        # en la pregunta actual (ver RAGService).
        history_block = f"""CONVERSACIÓN PREVIA (turnos anteriores, para contexto):
{history}

""" if history else ""

        # Si hay contexto (chunks de ChromaDB), se estructura el prompt
        # para que el LLM use esa información como base
        if context:
            return f"""Eres un asistente bibliotecario que SOLO responde usando la información proporcionada en el contexto.

REGLAS ESTRICTAS:
1. SOLO usa la información del contexto para responder
2. NO uses tu conocimiento general o información externa
3. Si la información no está en el contexto, di "No tengo información sobre eso en mi base de conocimientos"
4. Cita las fuentes cuando sea relevante
5. Responde en el mismo idioma que la pregunta

{history_block}CONTEXTO (información de tu base de conocimientos):
{context}

PREGUNTA DEL USUARIO: {prompt}

RESPUESTA (basada ÚNICAMENTE en el contexto anterior):"""
        elif history_block:
            # Sin contexto pero con historial. RAGService no debería llegar
            # aquí en el flujo normal (condense_question() reescribe la
            # pregunta de seguimiento y sigue retrievando como siempre —
            # ver RAGService.ask_question), pero se deja como red de
            # seguridad para cualquier llamada con context=None + history.
            # Antes esta rama no imponía ninguna regla estricta (a
            # diferencia de la rama `if context:` de arriba); el comentario
            # decía "seguimos exigiendo que se ciña a lo ya dicho" pero el
            # texto real no lo hacía cumplir. Ahora sí, con las mismas 4
            # reglas anti-alucinación que la rama de contexto, aplicadas al
            # historial en vez de a chunks de ChromaDB.
            return f"""Eres un asistente bibliotecario. Ya has hablado con el usuario sobre esto en esta misma conversación — la respuesta a su pregunta debería estar en lo que ya se dijo abajo.

REGLAS ESTRICTAS:
1. Responde ÚNICAMENTE con información que ya aparece en la conversación previa
2. NO uses tu conocimiento general ni inventes datos que no estén ahí
3. Si la respuesta no está en la conversación previa, di "No tengo esa información en mi base de conocimientos"
4. Responde en el mismo idioma que la pregunta

{history_block}PREGUNTA DEL USUARIO: {prompt}

RESPUESTA (basada ÚNICAMENTE en la conversación anterior):"""
        else:
            # Sin contexto ni historial: la pregunta se envía directa al LLM
            # (el LLM responderá con su conocimiento general)
            return prompt

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
        history: Optional[str] = None,
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
            history: Turnos previos de la conversación, ya formateados
                     (ver ConversationService.get_history_prompt_block)
            max_tokens: Límite de tokens (None = usa el default de Ollama)
            temperature: Creatividad del modelo
            **kwargs: Parámetros adicionales para el modelo

        Returns:
            str: Respuesta generada por llama3.2
        """
        try:
            # Obtiene el cliente LLM (lazy, solo crea si es la primera vez)
            llm = self._get_llm()
            full_prompt = self._build_full_prompt(prompt, context, history)

            # ============================================================
            # LLAMADA AL MODELO
            # ============================================================
            # ainvoke() es el método async de LangChain para invocar el LLM
            # "a" de ainvoke = async (vs invoke que es síncrono)
            # Equivalente: await llm.invoke(prompt) en versión async
            #
            # OJO: OllamaLLM._default_params solo expone 4 keys de nivel superior
            # (model, format, options, keep_alive); ainvoke() únicamente reenvía a
            # Ollama los kwargs que coincidan con esos nombres. temperature y
            # num_predict (max_tokens) van ANIDADOS dentro de "options" — pasarlos
            # sueltos como kwargs (como se hacía antes) no lanza ningún error,
            # simplemente Ollama los ignora y siempre usa la temperature con la
            # que se construyó el cliente en _get_llm().
            ollama_options: Dict[str, Any] = {"temperature": temperature, **kwargs}
            if max_tokens is not None:
                ollama_options["num_predict"] = max_tokens

            start_time = time.perf_counter()
            response = await llm.ainvoke(
                full_prompt,
                options=ollama_options
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

    async def stream_response(
        self,
        prompt: str,
        context: Optional[str] = None,
        history: Optional[str] = None,
        max_tokens: Optional[int] = None,
        temperature: float = 0.7,
        **kwargs
    ):
        """
        Versión en streaming de generate_response(): produce la respuesta
        trozo a trozo según Ollama la va generando, en vez de esperar a
        tenerla completa.

        Usa el mismo prompt que generate_response() (ver _build_full_prompt)
        y el mismo fix de options={...} para temperature/num_predict — la
        única diferencia real es astream() en vez de ainvoke().

        Sin @retry (a diferencia de generate_response): reintentar a mitad
        de un stream ya empezado produciría trozos duplicados en el
        cliente; si astream() falla, el error se propaga y quien la llama
        (RAGService.ask_question_stream) decide cómo comunicarlo.

        Yields:
            str: fragmentos de texto de la respuesta, en orden
        """
        llm = self._get_llm()
        full_prompt = self._build_full_prompt(prompt, context, history)

        ollama_options: Dict[str, Any] = {"temperature": temperature, **kwargs}
        if max_tokens is not None:
            ollama_options["num_predict"] = max_tokens

        start_time = time.perf_counter()
        chunk_count = 0
        try:
            async for chunk in llm.astream(full_prompt, options=ollama_options):
                chunk_count += 1
                yield chunk
        finally:
            duration = time.perf_counter() - start_time
            LLM_REQUESTS.labels(operation='generate_stream').inc()
            LLM_LATENCY.labels(operation='generate_stream').observe(duration)
            logger.info(
                "Streamed response from Ollama",
                duration_seconds=round(duration, 3),
                chunk_count=chunk_count
            )

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
            # Igual que en generate_response(): temperature va anidada en "options",
            # no como kwarg suelto (ver comentario detallado ahí).
            response = await llm.ainvoke(
                extraction_prompt,
                options={"temperature": 0.1}  # Muy bajo para respuestas consistentes
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

    @retry(
        stop=stop_after_attempt(2),
        wait=wait_exponential(multiplier=1, min=1, max=5)
    )
    async def is_catalog_question(self, question: str) -> bool:
        """
        Clasifica si la pregunta es sobre el catálogo (cuántos/qué
        documentos hay) o sobre contenido, usando el LLM.

        Mismo patrón que extract_keywords(): prompt corto, temperature
        muy baja para una clasificación consistente, respuesta de una
        sola palabra para que el parseo sea trivial. Ver
        LLMPort.is_catalog_question para el porqué (independiente de
        idioma/redacción, a diferencia de un regex de frases).

        Args:
            question: Pregunta del usuario, en cualquier idioma

        Returns:
            bool: True si es una pregunta de catálogo, False en cualquier
                  otro caso (incluido error) — fallback seguro al pipeline normal
        """
        try:
            llm = self._get_llm()

            classification_prompt = f"""Clasifica la siguiente pregunta en una sola categoría.

CATALOG: la pregunta pide el número total, un listado o un resumen de TODOS los documentos que hay en la base de conocimiento, como colección. Ejemplos: "¿cuántos libros conoces?", "how many books do you have?", "qué documentos tienes", "lista los libros", "qué hay en tu base de conocimiento".
CONTENT: la pregunta pide información sobre UN documento concreto (aunque no lo nombre explícitamente y se sobreentienda por el contexto de la conversación) — incluye preguntas que piden una CANTIDAD sobre ESE documento en particular: páginas, capítulos, año de publicación, precio, etc. Ejemplos: "¿quién escribió 1984?", "what is Docker?", "resume el capítulo 3", "¿cuántas páginas tiene?", "¿cuántos capítulos tiene este libro?", "¿en qué año se publicó?".

Regla clave para desambiguar: si la pregunta pide una cantidad SOBRE UN documento (páginas, capítulos, año...) es CONTENT, no CATALOG. Solo es CATALOG si pregunta por el número o listado de TODOS los documentos de la base de conocimiento en su conjunto.

Responde con una única palabra: CATALOG o CONTENT. Nada más.

Pregunta: {question}

Categoría:"""

            start_time = time.perf_counter()
            response = await llm.ainvoke(
                classification_prompt,
                options={"temperature": 0.0}  # Determinista: es una clasificación, no generación
            )
            duration = time.perf_counter() - start_time

            is_catalog = "CATALOG" in response.strip().upper()

            LLM_REQUESTS.labels(operation='classify_intent').inc()
            LLM_LATENCY.labels(operation='classify_intent').observe(duration)

            logger.info(
                "Classified question intent",
                is_catalog_question=is_catalog,
                duration_seconds=round(duration, 3)
            )
            return is_catalog

        except Exception as e:
            logger.warning("Failed to classify question intent, falling back to content pipeline", error=str(e))
            # Fallback seguro: si la clasificación falla, tratamos la pregunta
            # como de contenido (el pipeline normal ya sabe admitir "no tengo
            # información" si no encuentra nada relevante)
            return False

    @retry(
        stop=stop_after_attempt(2),
        wait=wait_exponential(multiplier=1, min=1, max=5)
    )
    async def condense_question(self, question: str, history: str) -> str:
        """
        Reescribe una pregunta de seguimiento como pregunta autocontenida,
        usando el historial de conversación. Ver LLMPort.condense_question
        para el porqué (patrón estándar de RAG conversacional).

        Args:
            question: Pregunta de seguimiento del usuario
            history: Turnos previos de la conversación ya formateados

        Returns:
            str: pregunta reescrita, o la original si ya era autocontenida
                 o si hubo un error
        """
        try:
            llm = self._get_llm()

            condense_prompt = f"""Dada la conversación previa y la pregunta de seguimiento del usuario, reescribe la pregunta de seguimiento como una pregunta autocontenida (standalone) que incluya todo el contexto necesario para entenderla sin necesitar la conversación previa.

Si la pregunta de seguimiento YA es autocontenida (por ejemplo, ya menciona explícitamente el documento o tema del que habla), devuélvela EXACTAMENTE IGUAL, sin cambiarla.

Responde SOLO con la pregunta (reescrita o igual), sin explicaciones, sin comillas, sin prefijos.

CONVERSACIÓN PREVIA:
{history}

PREGUNTA DE SEGUIMIENTO: {question}

PREGUNTA AUTOCONTENIDA:"""

            start_time = time.perf_counter()
            response = await llm.ainvoke(
                condense_prompt,
                options={"temperature": 0.0}  # Determinista: es una reescritura mecánica, no generación creativa
            )
            duration = time.perf_counter() - start_time

            condensed = response.strip().strip('"')
            # Si el LLM devuelve una respuesta vacía o degenerada, mejor
            # quedarse con la pregunta original que perderla
            if not condensed:
                condensed = question

            LLM_REQUESTS.labels(operation='condense_question').inc()
            LLM_LATENCY.labels(operation='condense_question').observe(duration)

            logger.info(
                "Condensed follow-up question",
                original=question,
                condensed=condensed,
                duration_seconds=round(duration, 3)
            )
            return condensed

        except Exception as e:
            logger.warning("Failed to condense question, using original", error=str(e))
            # Fallback seguro: si la reescritura falla, seguimos con la
            # pregunta original — el retrieval se comporta como si esta
            # función no existiera, no rompe la petición
            return question
