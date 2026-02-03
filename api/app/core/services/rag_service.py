# /api/app/core/services/rag_service.py
"""
Servicio RAG (Retrieval-Augmented Generation) - TFM Bibliotecario-IA

Este servicio es el CORAZÓN del sistema. Implementa el patrón RAG completo:
recibe una pregunta del usuario y devuelve una respuesta basada en documentos.

¿Qué es RAG?
- Retrieval-Augmented Generation = Generación Aumentada por Recuperación
- Combina búsqueda vectorial (ChromaDB) con generación de texto (LLM)
- El LLM NO inventa respuestas: las basa en chunks reales de los documentos

¿Diferencia con SyncService?
- SyncService: Datos → ChromaDB (pipeline de INGESTA)
- RAGService:  ChromaDB → Respuesta (pipeline de CONSULTA)

Pipeline RAG completo:
    Pregunta → Embedding → Búsqueda → Contexto → LLM → Respuesta

Solo necesita 2 puertos (no el DocumentProcessor, pues no procesa docs):
- LLMPort: Para generar embeddings y respuestas
- VectorDBPort: Para buscar chunks relevantes

Equivalente en TypeScript:
    class RAGService {
        constructor(
            private llm: LLMPort,
            private vectorDb: VectorDBPort
        ) {}

        async askQuestion(query: Query): Promise<QueryResult> { ... }
        private buildContext(docs: SourceDocument[]): string { ... }
        async getCollectionInfo(): Promise<Record<string, any>> { ... }
    }

Endpoints que usan este servicio:
- POST /query → ask_question()
- GET /info  → get_collection_info()
"""

# ============================================================================
# IMPORTS
# ============================================================================
import logging
import time
from typing import Optional

# Solo importamos LLM y VectorDB (no necesitamos DocumentProcessor)
from app.core.ports.llm_port import LLMPort
from app.core.ports.vector_db_port import VectorDBPort
from app.core.domain.models import Query, QueryResult, SourceDocument
from app.config.settings import settings


logger = logging.getLogger(__name__)


# ============================================================================
# SERVICIO RAG
# ============================================================================
class RAGService:
    """
    Servicio para responder preguntas usando el pipeline RAG.

    Este es el servicio principal que los usuarios interactúan indirectamente.
    Cuando alguien hace una pregunta por la API, este servicio:
    1. Busca información relevante en ChromaDB
    2. Construye un contexto con esa información
    3. Le pide al LLM que responda basándose en ese contexto

    Ventaja del patrón RAG vs un LLM solo:
    - Sin RAG: El LLM responde con su conocimiento general (puede inventar)
    - Con RAG: El LLM responde basándose en TUS documentos (más preciso)
    """

    def __init__(
        self,
        llm: LLMPort,
        vector_db: VectorDBPort
    ):
        """
        Inicializa el servicio RAG con las dependencias requeridas.

        Solo necesita 2 puertos (a diferencia de SyncService que necesita 3):
        - LLM: Para vectorizar la pregunta y generar la respuesta
        - VectorDB: Para buscar chunks relevantes

        Args:
            llm: Adaptador del modelo de lenguaje (Ollama)
            vector_db: Adaptador de base de datos vectorial (ChromaDB)
        """
        self.llm = llm
        self.vector_db = vector_db

    async def ask_question(
        self,
        query: Query,
        collection_name: Optional[str] = None
    ) -> QueryResult:
        """
        Responde una pregunta usando el pipeline RAG completo con Query Expansion.

        ESTE ES EL MÉTODO PRINCIPAL DEL SISTEMA.
        Es el que se invoca cuando un usuario hace una pregunta.

        Pipeline con Query Expansion:
            ① Extraer keywords         → extract_keywords() [NUEVO]
            ② Vectorizar pregunta      → generate_embedding()
            ③ Buscar con keywords      → similarity_search(keyword_filter) [NUEVO]
            ④ Fallback semántico       → similarity_search() sin filtro
            ⑤ Construir contexto       → _build_context()
            ⑥ Generar respuesta        → generate_response()
            ⑦ Devolver resultado       → QueryResult

        ¿Qué es Query Expansion?
        Técnica que mejora la búsqueda para nombres propios y títulos:
        - Extraemos keywords de la pregunta (ej: "Blade Runner 2049")
        - Buscamos documentos que contengan esas keywords
        - Si no hay resultados, hacemos búsqueda semántica pura

        Args:
            query: Objeto Query con:
                   - question: la pregunta del usuario
                   - max_results: máximo de chunks a recuperar
                   - session_id: ID de sesión (para futuro historial)
            collection_name: Colección de ChromaDB (opcional)

        Returns:
            QueryResult con:
                - answer: respuesta generada por el LLM
                - source_documents: chunks que se usaron como contexto
                - processing_time: tiempo total de la operación

        Ejemplo:
            query = Query(question="¿Qué es Docker?", max_results=3)
            result = await rag_service.ask_question(query)
            print(result.answer)  # "Docker es una plataforma..."
            print(len(result.source_documents))  # 3 fuentes usadas
        """
        start_time = time.time()
        collection = collection_name or settings.chromadb_collection_name

        try:
            # Truncamos la pregunta a 50 chars solo para el log
            # [:50] es slicing en Python (como substring en JS)
            logger.info(f"Processing question: {query.question[:50]}...")

            # ================================================================
            # PASO 1: Extraer keywords para Query Expansion
            # ================================================================
            # El LLM identifica nombres propios, títulos, etc.
            # Ejemplo: "¿Quién dirigió Blade Runner?" → ["Blade Runner"]
            keywords = await self.llm.extract_keywords(query.question)
            logger.info(f"Extracted keywords: {keywords}")

            # ================================================================
            # PASO 2: Vectorizar la pregunta del usuario
            # ================================================================
            # La pregunta se convierte en un vector numérico
            # Este vector se usará para buscar chunks similares
            query_embedding = await self.llm.generate_embedding(query.question)
            logger.debug(f"Generated query embedding of dimension: {len(query_embedding)}")

            # ================================================================
            # PASO 3: Buscar con Query Expansion (keyword + semantic)
            # ================================================================
            # Intentamos buscar con cada keyword extraída
            # Si encontramos resultados, usamos esos; si no, fallback semántico
            source_documents = []

            if keywords:
                # Intentar búsqueda con la primera keyword más relevante
                # (normalmente es el nombre propio o título)
                for keyword in keywords:
                    source_documents = await self.vector_db.similarity_search(
                        query_embedding=query_embedding,
                        collection_name=collection,
                        top_k=query.max_results,
                        keyword_filter=keyword
                    )
                    if source_documents:
                        logger.info(f"Found {len(source_documents)} docs with keyword '{keyword}'")
                        break  # Encontramos resultados, no seguir buscando

            # ================================================================
            # PASO 4: Fallback a búsqueda semántica pura
            # ================================================================
            # Si no hay keywords o no encontramos resultados con keywords,
            # hacemos búsqueda semántica sin filtros
            if not source_documents:
                logger.info("No results with keywords, falling back to semantic search")
                source_documents = await self.vector_db.similarity_search(
                    query_embedding=query_embedding,
                    collection_name=collection,
                    top_k=query.max_results
                )

            # Si no hay resultados relevantes, no llamamos al LLM
            # Ahorra recursos y evita que invente una respuesta
            if not source_documents:
                logger.warning("No relevant context found in database")
                return QueryResult(
                    question=query.question,
                    answer="Lo siento, no encontré información relevante en la base de conocimientos para responder a tu pregunta.",
                    source_documents=[],
                    session_id=query.session_id,
                    processing_time=time.time() - start_time
                )

            logger.info(f"Retrieved {len(source_documents)} relevant documents")

            # ================================================================
            # PASO 3: Construir el contexto a partir de los chunks
            # ================================================================
            # Convierte la lista de SourceDocuments en un texto formateado
            # que se inyectará al LLM como contexto
            context = self._build_context(source_documents)

            # ================================================================
            # PASO 4: Generar respuesta usando el LLM con contexto
            # ================================================================
            # El LLM recibe:
            # - prompt: la pregunta original del usuario
            # - context: los chunks relevantes formateados
            # El LLM debe basar su respuesta SOLO en ese contexto
            answer = await self.llm.generate_response(
                prompt=query.question,
                context=context,
                temperature=settings.llm_temperature,   # Ej: 0.3 para precisión
                max_tokens=settings.llm_max_tokens       # Límite de respuesta
            )

            processing_time = time.time() - start_time
            logger.info(f"Generated answer in {processing_time:.2f}s")

            # ================================================================
            # PASO 5: Devolver resultado con respuesta y fuentes
            # ================================================================
            # El QueryResult incluye source_documents para que el frontend
            # pueda mostrar "esta respuesta se basó en estas fuentes"
            return QueryResult(
                question=query.question,
                answer=answer,
                source_documents=source_documents,
                session_id=query.session_id,
                processing_time=processing_time
            )

        except Exception as e:
            # En caso de error, devolvemos un QueryResult con mensaje
            # en español al usuario (no lanzamos la excepción)
            error_msg = f"Failed to process question: {str(e)}"
            logger.error(error_msg, exc_info=True)

            return QueryResult(
                question=query.question,
                answer=f"Lo siento, ocurrió un error al procesar tu pregunta: {str(e)}",
                source_documents=[],
                session_id=query.session_id,
                processing_time=time.time() - start_time
            )

    def _build_context(self, source_documents: list[SourceDocument]) -> str:
        """
        Construye el texto de contexto a partir de los chunks recuperados.

        MÉTODO PRIVADO (el guión bajo _ indica que es solo para uso interno).
        No se llama desde fuera de la clase.

        ¿Qué hace?
        Toma los chunks relevantes de ChromaDB y los formatea en un texto
        que el LLM puede entender como contexto para basar su respuesta.

        Ejemplo de salida:
            [Fuente 1]
            Docker es una plataforma de contenedores que permite...

            ---

            [Fuente 2]
            Los contenedores se diferecian de las VMs porque...

        ¿Por qué numerar las fuentes?
        - Permite al LLM referenciar fuentes específicas
        - El frontend puede mostrar "según la fuente 1..."
        - Facilita la trazabilidad de la respuesta

        Args:
            source_documents: Lista de chunks relevantes recuperados

        Returns:
            str: Texto formateado con todas las fuentes
        """
        context_parts = []

        # enumerate(lista, 1) itera con índice empezando desde 1
        # Equivalente JS: source_documents.forEach((doc, i) => ...)
        # pero i empieza en 1 en lugar de 0
        for i, doc in enumerate(source_documents, 1):
            # Formato: [Fuente N] + contenido del chunk
            context_part = f"[Fuente {i}]\n{doc.chunk_content}"
            context_parts.append(context_part)

        # join() une todos los parts con un separador visual
        # "\n\n---\n\n" = línea en blanco + guiones + línea en blanco
        # Equivalente JS: context_parts.join("\n\n---\n\n")
        context = "\n\n---\n\n".join(context_parts)

        logger.debug(f"Built context with {len(source_documents)} sources")
        return context

    async def get_collection_info(
        self,
        collection_name: Optional[str] = None
    ) -> dict:
        """
        Obtiene información sobre la colección de la base de datos vectorial.

        Método auxiliar para endpoints de info/estado de la API.
        Devuelve estadísticas de ChromaDB + info del modelo LLM.

        Args:
            collection_name: Colección a consultar (opcional)

        Returns:
            dict con:
                - collection: nombre de la colección
                - stats: estadísticas (total chunks, documentos, etc.)
                - model_info: info del modelo LLM activo

        Ejemplo de retorno:
            {
                "collection": "tech_docs",
                "stats": {"total_chunks": 1500, "unique_documents": 12},
                "model_info": {"model_name": "llama3.2", "provider": "ollama"}
            }
        """
        collection = collection_name or settings.chromadb_collection_name

        try:
            # Obtiene estadísticas de ChromaDB
            stats = await self.vector_db.get_collection_stats(collection)
            return {
                "collection": collection,
                "stats": stats,
                # get_model_info() no es async, retorna info cacheada
                "model_info": self.llm.get_model_info()
            }

        except Exception as e:
            # En caso de error, devolvemos estructura válida con el error
            # Así el frontend no falla al parsear la respuesta
            logger.error(f"Failed to get collection info: {e}")
            return {
                "collection": collection,
                "stats": {"error": str(e)},
                "model_info": {}
            }
