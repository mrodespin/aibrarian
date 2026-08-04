# /api/app/core/ports/llm_port.py
"""
Puerto (Interfaz) para operaciones del Modelo de Lenguaje - TFM Bibliotecario-IA

Este archivo define el CONTRATO que debe cumplir cualquier LLM (Large Language Model).
Es una interfaz abstracta que permite cambiar de Ollama a OpenAI sin modificar servicios.

¿Qué es un LLM?
- Large Language Model = Modelo de Lenguaje Grande
- Ejemplos: GPT-4, Llama, Mistral, Claude
- Puede entender y generar texto en lenguaje natural

¿Por qué dos tipos de operaciones?
1. generate_response: Usa modelo conversacional (llama3.2) para generar texto
2. generate_embedding: Usa modelo de embeddings (nomic-embed-text) para vectorizar

Son modelos DIFERENTES aunque ambos se accedan por Ollama.

Equivalente en TypeScript:
    interface LLMPort {
        generateResponse(prompt: string, context?: string): Promise<string>;
        generateEmbedding(text: string): Promise<number[]>;
        generateEmbeddingsBatch(texts: string[]): Promise<number[][]>;
        isAvailable(): Promise<boolean>;
        getModelInfo(): Record<string, any>;
    }

La implementación real está en: /adapters/outbound/ollama_adapter.py
"""

# ============================================================================
# IMPORTS
# ============================================================================
# ABC permite crear clases abstractas (interfaces)
from abc import ABC, abstractmethod
from typing import List, Optional, Dict, Any, AsyncIterator


# ============================================================================
# INTERFAZ DEL MODELO DE LENGUAJE
# ============================================================================
class LLMPort(ABC):
    """
    Interfaz abstracta para operaciones del Modelo de Lenguaje.

    El sistema RAG necesita DOS capacidades del LLM:

    1. GENERACIÓN DE TEXTO (generate_response):
       - Recibe: pregunta + contexto (chunks relevantes)
       - Devuelve: respuesta en lenguaje natural
       - Modelo usado: llama3.2 (conversacional)

    2. GENERACIÓN DE EMBEDDINGS (generate_embedding):
       - Recibe: texto a vectorizar
       - Devuelve: vector numérico [0.1, -0.2, 0.3, ...]
       - Modelo usado: nomic-embed-text (especializado en embeddings)

    Flujo en el sistema RAG:
        Usuario: "¿Qué es machine learning?"
            ↓
        generate_embedding("¿Qué es machine learning?")
            ↓
        Vector → ChromaDB → chunks relevantes
            ↓
        generate_response(prompt=pregunta, context=chunks)
            ↓
        "Machine learning es una rama de la IA..."

    Nota: ABC = Abstract Base Class (no se puede instanciar directamente)
    """

    @abstractmethod
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
        Genera una respuesta de texto usando el modelo de lenguaje.

        ESTE MÉTODO ES EL "CEREBRO" DEL CHATBOT.

        ¿Cómo funciona internamente?
        1. Se construye un prompt con la pregunta + contexto
        2. Se envía al modelo (Ollama/llama3.2)
        3. El modelo genera tokens uno a uno hasta completar
        4. Se devuelve la respuesta completa

        Args:
            prompt: Pregunta del usuario en lenguaje natural
                   Ejemplo: "¿Qué es machine learning?"

            context: Contexto opcional (chunks recuperados de ChromaDB)
                    Ejemplo: "Según el documento X, machine learning es..."
                    El contexto se inyecta en el prompt para dar información

            history: Turnos previos de la conversación, ya formateados como
                    texto (ver ConversationService.get_history_prompt_block),
                    o None si no hay historial. Se antepone al contexto en el
                    prompt para que el modelo pueda resolver preguntas de
                    seguimiento ("¿puedes ampliar eso?").

            max_tokens: Límite de tokens en la respuesta (None = sin límite)
                       Un token ≈ 0.75 palabras en español
                       Ejemplo: max_tokens=500 ≈ 375 palabras

            temperature: Controla la "creatividad" del modelo (0.0 a 1.0)
                        - 0.0 = determinista (siempre la misma respuesta)
                        - 0.7 = balance entre coherencia y variedad (default)
                        - 1.0 = muy creativo/aleatorio
                        Para Q&A técnico, mejor usar 0.3-0.5

            **kwargs: Parámetros adicionales específicos del modelo
                     Es como ...rest en JavaScript
                     Ejemplo: top_p=0.9, repetition_penalty=1.1

        Returns:
            str: Respuesta generada por el modelo

        Ejemplo de uso:
            response = await llm.generate_response(
                prompt="¿Qué es RAG?",
                context="RAG significa Retrieval-Augmented Generation...",
                temperature=0.3  # Bajo para respuestas más precisas
            )
            # response = "RAG (Retrieval-Augmented Generation) es una técnica..."
        """
        pass  # La implementación real está en ollama_adapter.py

    @abstractmethod
    async def generate_embedding(self, text: str) -> List[float]:
        """
        Genera un vector embedding para un texto.

        ¿Qué es un embedding?
        - Representación numérica del "significado" de un texto
        - Vector de ~768 números flotantes
        - Textos similares → vectores cercanos en el espacio

        ¿Para qué sirve?
        - Convertir la pregunta del usuario en vector
        - Ese vector se compara con los chunks en ChromaDB
        - Se encuentran los chunks más "semánticamente similares"

        Args:
            text: Texto a convertir en vector
                 Ejemplo: "¿Cómo funciona la autenticación?"

        Returns:
            List[float]: Vector de ~768 números
                        Ejemplo: [0.123, -0.456, 0.789, ...]

        Ejemplo:
            # Vectorizar una pregunta
            embedding = await llm.generate_embedding("¿Qué es Docker?")
            # embedding = [0.1, -0.2, 0.3, ...] (768 números)

            # Este vector se envía a ChromaDB para buscar chunks similares

        Modelo usado: nomic-embed-text (especializado en embeddings)
        Dimensiones: 768 (fijo para este modelo)
        """
        pass

    @abstractmethod
    async def generate_embeddings_batch(self, texts: List[str]) -> List[List[float]]:
        """
        Genera embeddings para múltiples textos en lote.

        ¿Por qué batch en lugar de uno por uno?
        - Eficiencia: una llamada en lugar de N llamadas
        - Menor latencia total
        - Cuando ingestas un PDF de 100 chunks, es MUY ineficiente
          hacer 100 llamadas individuales

        Args:
            texts: Lista de textos a vectorizar
                  Ejemplo: ["Chunk 1 del PDF...", "Chunk 2 del PDF...", ...]

        Returns:
            List[List[float]]: Lista de vectores, uno por cada texto
                              Mantiene el mismo orden que la entrada

        Ejemplo:
            chunks = ["Texto chunk 1", "Texto chunk 2", "Texto chunk 3"]
            embeddings = await llm.generate_embeddings_batch(chunks)
            # embeddings[0] corresponde a chunks[0]
            # embeddings[1] corresponde a chunks[1]
            # etc.

        Nota: Internamente puede procesar en paralelo o en mini-batches
              según las capacidades del modelo/hardware
        """
        pass

    @abstractmethod
    async def is_available(self) -> bool:
        """
        Verifica si el servicio LLM está disponible y respondiendo.

        Útil para:
        - Health checks de la API (endpoint /health)
        - Verificar que Ollama está corriendo antes de procesar
        - Mostrar estado al usuario en el frontend

        Returns:
            bool: True si el servicio está disponible

        Ejemplo:
            if not await llm.is_available():
                raise ServiceUnavailableError("Ollama no está corriendo")

        Implementación típica:
        - Intenta hacer una llamada simple al modelo
        - Si responde en < 5 segundos → True
        - Si hay timeout o error → False
        """
        pass

    async def warm_up(self) -> None:
        """
        Precarga en memoria lo que el adaptador necesite antes de la primera
        petición real (p.ej. descargar/cargar un modelo local).

        No es @abstractmethod: por defecto no hace nada (implementación
        vacía), así que los adaptadores que no lo necesiten (OllamaAdapter,
        cuyos embeddings los sirve el propio servidor Ollama) no tienen que
        implementarlo. GroqAdapter lo sobreescribe para precargar el modelo
        de sentence-transformers local.

        Se llama como tarea en segundo plano DESPUÉS de que el startup de
        FastAPI termine (ver lifespan en main.py) — nunca debe bloquear el
        arranque, porque uvicorn no abre el puerto hasta que el startup
        completa (ver is_available en groq_adapter.py para el porqué).
        """
        pass

    async def stream_response(
        self,
        prompt: str,
        context: Optional[str] = None,
        history: Optional[str] = None,
        max_tokens: Optional[int] = None,
        temperature: float = 0.7,
        **kwargs
    ) -> AsyncIterator[str]:
        """
        Versión en streaming de generate_response(): produce la respuesta
        trozo a trozo en vez de esperar a tenerla completa.

        No es @abstractmethod (mismo patrón que warm_up): por defecto cae
        a generate_response() y produce un único trozo con la respuesta
        completa, así que un adaptador que no implemente streaming real
        (p.ej. GroqAdapter en esta primera versión) sigue siendo un
        LLMPort válido sin tener que sobreescribir nada. OllamaAdapter sí
        lo sobreescribe con streaming real (llm.astream()).

        Args:
            Mismos que generate_response() — ver ahí para el detalle.

        Yields:
            str: fragmentos de la respuesta, en el orden en que se generan.
                 Concatenados en orden, forman la misma respuesta completa
                 que devolvería generate_response() con los mismos argumentos.
        """
        yield await self.generate_response(
            prompt=prompt,
            context=context,
            history=history,
            max_tokens=max_tokens,
            temperature=temperature,
            **kwargs
        )

    @abstractmethod
    def get_model_info(self) -> Dict[str, Any]:
        """
        Obtiene información sobre el modelo actual.

        Nota: Este método NO es async (sin await) porque la info
              típicamente está cacheada en memoria.

        Returns:
            Dict con información del modelo:
            {
                "model_name": "llama3.2",
                "embedding_model": "nomic-embed-text",
                "embedding_dimensions": 768,
                "provider": "ollama",
                "base_url": "http://localhost:11434"
            }

        Útil para:
        - Endpoint /info de la API
        - Debugging ("¿qué modelo estoy usando?")
        - Logging y monitoreo
        """
        pass

    @abstractmethod
    async def extract_keywords(self, question: str) -> List[str]:
        """
        Extrae palabras clave y entidades de una pregunta (Query Expansion).

        ¿Por qué Query Expansion?
        - La búsqueda semántica pura puede fallar con nombres propios
        - Ejemplo: "Blade Runner" vs "Blade Runner 2049"
        - Extraer keywords permite filtrar documentos antes de buscar

        Flujo:
            Pregunta: "¿Quién dirigió Blade Runner 2049?"
                ↓
            Keywords: ["Blade Runner 2049", "dirigió", "director"]
                ↓
            Filtro por keywords + búsqueda semántica

        Args:
            question: Pregunta del usuario en lenguaje natural

        Returns:
            List[str]: Lista de keywords/entidades extraídas
                      Lista vacía si no se pueden extraer

        Ejemplo:
            keywords = await llm.extract_keywords("¿Qué es Docker?")
            # keywords = ["Docker"]
        """
        pass

    @abstractmethod
    async def is_catalog_question(self, question: str) -> bool:
        """
        Clasifica si una pregunta es sobre el CATÁLOGO (cuántos/qué
        documentos hay en total) en vez de sobre el CONTENIDO de un
        documento concreto.

        ¿Por qué hace falta esto?
        similarity_search siempre devuelve como mucho top_k chunks — es la
        herramienta correcta para "¿qué dice el libro X sobre Y?", pero
        estructuralmente NO puede responder bien "¿cuántos libros
        conoces?": no hay forma de garantizar que el top_k cubra el
        catálogo completo. RAGService usa este método para desviar esa
        clase de pregunta a VectorDBPort.list_documents() en vez de a
        similarity_search (ver RAGService._build_meta_answer).

        Nota: esto es independiente de condense_question() — una pregunta
        de catálogo no necesita reescribirse con el historial, así que
        esta comprobación va ANTES, y solo si es False se pasa por
        condense_question() antes de retrievar.

        ¿Por qué un LLM y no un regex de palabras clave?
        Un regex de frases típicas solo cubre un idioma y una redacción
        concreta. El LLM entiende la intención independientemente del
        idioma o de cómo esté formulada la pregunta — mismo principio que
        extract_keywords(), que también delega en el LLM en vez de en una
        lista de patrones.

        Debe ser una llamada barata y rápida: prompt corto, respuesta de
        una palabra, temperature baja/0 para que la clasificación sea
        consistente. En caso de error de red/parseo, debe devolver False
        (fallback seguro: cae al pipeline RAG normal en vez de romper la
        pregunta por completo).

        Args:
            question: Pregunta del usuario en lenguaje natural, en cualquier idioma

        Returns:
            bool: True si la pregunta es sobre el catálogo/inventario de
                  documentos, False si es sobre contenido (o si hubo error)

        Ejemplo:
            await llm.is_catalog_question("¿Cuántos libros conoces?")       # True
            await llm.is_catalog_question("How many books do you have?")   # True
            await llm.is_catalog_question("¿Quién escribió 1984?")         # False
        """
        pass

    @abstractmethod
    async def condense_question(self, question: str, history: str) -> str:
        """
        Reescribe una pregunta de seguimiento como una pregunta
        autocontenida (standalone), incorporando el contexto necesario de
        la conversación previa — patrón estándar en RAG conversacional
        ("query rewriting" / "condense question", ver
        `create_history_aware_retriever` de LangChain para la misma idea).

        ¿Por qué hace falta esto?
        similarity_search/extract_keywords se basan SOLO en el texto de la
        pregunta actual. Una pregunta de seguimiento corta y sin nombres
        propios ("¿en qué año fue publicada?", "¿cuántas páginas tiene?")
        no tiene ancla para encontrar el documento correcto — puede no
        encontrar nada, o (peor, confirmado en producción) encontrar un
        chunk de OTRO documento con score suficiente para colarse como
        "relevante" y generar una respuesta segura pero incorrecta.

        Al reescribir ANTES de retrievar ("¿en qué año fue publicada?" +
        historial sobre "Cien años de soledad" → "¿En qué año fue
        publicada Cien años de soledad?"), la búsqueda vectorial recibe
        una pregunta autocontenida y vuelve a funcionar con el pipeline
        normal de siempre (extract_keywords + similarity_search) — no hace
        falta ninguna vía especial ni saltarse ChromaDB.

        Si la pregunta ya es autocontenida (nombra el documento/tema
        explícitamente, o no depende de turnos anteriores), debe
        devolverse tal cual, sin reescribir — este método NO decide si
        hace falta reescribir, siempre se le pide que lo intente; es su
        propio prompt el que debe dejar la pregunta intacta si ya vale
        por sí sola.

        En caso de error, debe devolver la pregunta original sin tocar
        (fallback seguro: en el peor caso el retrieval se comporta como
        antes de tener esta función, no rompe la petición).

        Args:
            question: Pregunta de seguimiento del usuario
            history: Turnos previos de la conversación ya formateados (ver
                     ConversationService.get_history_prompt_block) — quien
                     llama a este método solo debe invocarlo cuando history
                     no es None/vacío (sin historial no hay nada que condensar)

        Returns:
            str: la pregunta reescrita como standalone, o la original si
                 ya lo era o si hubo un error

        Ejemplo:
            await llm.condense_question(
                "¿En qué año fue publicada?",
                history="Usuario: háblame de Cien años de soledad\\nAsistente: ...publicada en 1967..."
            )
            # "¿En qué año fue publicada Cien años de soledad?"
        """
        pass
