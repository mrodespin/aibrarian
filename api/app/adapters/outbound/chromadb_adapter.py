# /api/app/adapters/outbound/chromadb_adapter.py
"""
Adaptador ChromaDB - Implementación concreta de VectorDBPort - TFM Bibliotecario-IA

Este adaptador conecta el sistema con ChromaDB (base de datos vectorial).
Es la implementación REAL del contrato definido en VectorDBPort.

¿Qué es ChromaDB?
- Base de datos especializada en almacenar y buscar vectores
- Permite búsqueda semántica (por significado, no por palabras exactas)
- Se ejecuta como servidor separado (similar a como PostgreSQL)
- Accesible por HTTP en localhost:8000

¿Qué es una colección?
- Como una tabla en SQL, pero para vectores
- Cada colección almacena chunks de un tipo de documentación
- Ejemplo: "tech_docs", "tutorials", "faq"

Datos almacenados por chunk en ChromaDB:
- id: identificador único del chunk
- embedding: vector numérico [0.1, -0.2, 0.3, ...] (768 dimensiones)
- document: texto original del chunk
- metadata: diccionario con info extra {document_id, source, page, ...}

Patrones implementados:
- Lazy Initialization: el cliente solo se crea cuando se necesita
- Cache de colecciones: cada colección se obtiene una sola vez
- Formato columnar: ChromaDB necesita datos en listas paralelas

Equivalente en TypeScript:
    class ChromaDBAdapter implements VectorDBPort {
        private client: ChromaClient | null = null;
        private collections: Map<string, Collection> = new Map();

        async storeChunks(chunks, collectionName): Promise<boolean> { ... }
        async similaritySearch(queryEmbedding, ...): Promise<SourceDocument[]> { ... }
        async deleteDocument(documentId, ...): Promise<boolean> { ... }
        async collectionExists(collectionName): Promise<boolean> { ... }
        async getCollectionStats(collectionName): Promise<Record<string, any>> { ... }
    }
"""

# ============================================================================
# IMPORTS
# ============================================================================
import chromadb  # Cliente oficial de ChromaDB
from chromadb.config import Settings as ChromaSettings  # Configuración de ChromaDB
from typing import List, Dict, Any, Optional
import logging

# Importamos el PUERTO (interfaz) que implementamos
from app.core.ports.vector_db_port import VectorDBPort
from app.core.domain.models import Chunk, SourceDocument
from app.config.settings import settings


logger = logging.getLogger(__name__)


# ============================================================================
# ADAPTADOR CHROMADB
# ============================================================================
class ChromaDBAdapter(VectorDBPort):
    """
    Implementación concreta de VectorDBPort usando ChromaDB.

    Esta clase es el ÚNICO lugar del sistema que conoce detalles de ChromaDB.
    El resto del código solo habla con la interfaz VectorDBPort.

    Si mañana cambias a Pinecone o Weaviate, solo cambias este archivo.

    Estado interno:
    - _client: conexión al servidor ChromaDB (lazy, se crea la primera vez)
    - _collections: cache de colecciones (evita pedir la misma colección repetido)
    """

    def __init__(self):
        """
        Inicializa el adaptador con lazy initialization.

        NO se conecta a ChromaDB aquí. La conexión se crea
        la primera vez que se necesita (_get_client).

        _collections es un dict que actúa como cache:
        { "tech_docs": <Collection>, "tutorials": <Collection> }
        Equivalente JS: private collections = new Map<string, Collection>()
        """
        self._client = None
        self._collections = {}

    def _get_client(self) -> chromadb.HttpClient:
        """
        Obtiene o crea la conexión al servidor ChromaDB (Lazy Singleton).

        Mismo patrón que en OllamaAdapter: la conexión se crea
        una sola vez y se reutiliza en todas las operaciones.

        HttpClient conecta al servidor ChromaDB por HTTP.
        anonymized_telemetry=False: deshabilita telemetría (privacidad).

        Returns:
            chromadb.HttpClient: Cliente conectado al servidor ChromaDB
        """
        if self._client is None:
            try:
                self._client = chromadb.HttpClient(
                    host=settings.chromadb_host,  # localhost
                    port=settings.chromadb_port,  # 8000
                    settings=ChromaSettings(
                        anonymized_telemetry=False  # No envía datos a Chroma
                    )
                )
                logger.info(f"Connected to ChromaDB at {settings.chromadb_url}")
            except Exception as e:
                logger.error(f"Failed to connect to ChromaDB: {e}")
                raise
        return self._client

    def _get_or_create_collection(self, collection_name: str):
        """
        Obtiene una colección existente o la crea si no existe.

        Doble patrón:
        1. Cache local: si ya la tenemos en _collections, la devolvemos
        2. ChromaDB get_or_create: si no existe en el servidor, la crea

        get_or_create_collection es un método de ChromaDB que hace:
        - Si la colección existe → la retorna
        - Si no existe → la crea y la retorna
        Es como un "upsert" pero para colecciones.

        Args:
            collection_name: Nombre de la colección (ej: "tech_docs")

        Returns:
            Collection: Objeto de colección de ChromaDB
        """
        # Primero verificamos en el cache local
        if collection_name not in self._collections:
            client = self._get_client()
            try:
                # get_or_create_collection: crea si no existe, retorna si existe
                self._collections[collection_name] = client.get_or_create_collection(
                    name=collection_name,
                    metadata={"description": "Bibliotecario-IA document embeddings"}
                )
                logger.info(f"Using collection: {collection_name}")
            except Exception as e:
                logger.error(f"Failed to get/create collection {collection_name}: {e}")
                raise
        return self._collections[collection_name]

    # ========================================================================
    # MÉTODOS PRINCIPALES - Implementación de VectorDBPort
    # ========================================================================

    async def store_chunks(
        self,
        chunks: List[Chunk],
        collection_name: str = "documents"
    ) -> bool:
        """
        Almacena chunks con sus embeddings en ChromaDB.

        Este método convierte los objetos Chunk en el FORMATO COLUMNAR
        que necesita ChromaDB: 4 listas paralelas donde la posición i
        de cada lista corresponde al mismo chunk.

        Formato columnar:
            ids        = ["chunk_0", "chunk_1", "chunk_2"]
            embeddings = [[0.1,...], [0.2,...], [0.3,...]]
            documents  = ["texto 0", "texto 1", "texto 2"]
            metadatas  = [{...},     {...},     {...}    ]

            ids[0] ↔ embeddings[0] ↔ documents[0] ↔ metadatas[0] = mismo chunk

        ¿Por qué columnar y no por filas?
        ChromaDB está optimizado internamente para almacenar vectores
        en arrays contiguos de memoria. El formato columnar permite esto.

        Args:
            chunks: Lista de chunks CON embeddings ya generados
            collection_name: Colección destino en ChromaDB

        Returns:
            bool: True si se almacenó correctamente
        """
        try:
            if not chunks:
                logger.warning("No chunks to store")
                return False

            collection = self._get_or_create_collection(collection_name)

            # ============================================================
            # PREPARAR DATOS EN FORMATO COLUMNAR
            # ============================================================
            # List comprehension para extraer cada campo de los chunks
            # Equivalente JS: chunks.map(chunk => chunk.id)
            ids = [chunk.id for chunk in chunks]
            embeddings = [chunk.embedding for chunk in chunks if chunk.embedding]
            documents = [chunk.content for chunk in chunks]

            # Metadatas: spread operator {**chunk.metadata} copia los metadatos
            # y añade document_id para poder eliminar por documento después
            # Equivalente JS: chunks.map(c => ({...c.metadata, documentId: c.documentId}))
            metadatas = [
                {**chunk.metadata, "document_id": chunk.document_id}
                for chunk in chunks
            ]

            # Validación: todos los chunks deben tener embedding
            # Si alguno falta, ChromaDB fallaría con un error confuso
            if not embeddings or len(embeddings) != len(chunks):
                logger.error("All chunks must have embeddings")
                return False

            # ============================================================
            # ALMACENAR EN CHROMADB
            # ============================================================
            # collection.add() es el método principal de ChromaDB
            # Recibe las 4 listas en paralelo
            collection.add(
                ids=ids,
                embeddings=embeddings,
                documents=documents,
                metadatas=metadatas
            )

            logger.info(f"Stored {len(chunks)} chunks in collection '{collection_name}'")
            return True

        except Exception as e:
            logger.error(f"Failed to store chunks: {e}")
            return False

    async def similarity_search(
        self,
        query_embedding: List[float],
        collection_name: str = "documents",
        top_k: int = 4,
        filter_metadata: Optional[Dict[str, Any]] = None,
        keyword_filter: Optional[str] = None
    ) -> List[SourceDocument]:
        """
        Realiza búsqueda por similitud en ChromaDB con soporte para Query Expansion.

        ESTE ES EL MÉTODO MÁS IMPORTANTE DEL SISTEMA.
        Es donde ocurre la búsqueda semántica: dado el vector de una pregunta,
        encuentra los chunks más semánticamente similares.

        QUERY EXPANSION (búsqueda híbrida):
        Si se proporciona keyword_filter, primero filtra documentos que contienen
        esa palabra clave (case-insensitive), luego rankea por similitud semántica.
        Esto mejora resultados para nombres propios y títulos específicos.

        ¿Cómo funciona internamente?
        1. ChromaDB calcula la distancia L2 entre el vector de la pregunta
           y TODOS los vectores almacenados en la colección
        2. Ordena por distancia (menor distancia = más similar)
        3. Devuelve los top_k más cercanos

        Formato de respuesta de ChromaDB (anidado):
            results["ids"]       = [["id_0", "id_1", "id_2"]]      # [0] = primera query
            results["documents"] = [["texto_0", "texto_1", ...]]
            results["distances"] = [[0.1, 0.3, 0.7]]               # menor = más similar
            results["metadatas"] = [[{...}, {...}, {...}]]

        ¿Por qué resultados anidados con [0]?
        ChromaDB soporta múltiples queries simultáneas.
        Como enviamos una sola query, los resultados están en el índice [0].

        Args:
            query_embedding: Vector de la pregunta del usuario
            collection_name: Colección donde buscar
            top_k: Número máximo de resultados (ej: 3 chunks más relevantes)
            filter_metadata: Filtro opcional por metadatos
                           Ejemplo: {"source": "pdf"} → solo chunks de PDFs
            keyword_filter: Palabra clave para filtrar documentos (Query Expansion)
                           Ejemplo: "Blade Runner" → solo chunks que contengan ese texto

        Returns:
            List[SourceDocument]: Chunks relevantes ordenados por similitud
        """
        try:
            collection = self._get_or_create_collection(collection_name)

            # ============================================================
            # QUERY A CHROMADB (con soporte para Query Expansion)
            # ============================================================
            # query_embeddings en lista porque ChromaDB acepta batch queries
            # include: qué campos devolver (por defecto solo ids)
            # where: filtro por metadatos (como WHERE en SQL)
            # where_document: filtro por contenido del documento (keyword search)

            # Construir filtro de documento si se proporciona keyword
            where_document = None
            if keyword_filter:
                # $contains busca substring en el contenido del documento
                where_document = {"$contains": keyword_filter}
                logger.info(f"Applying keyword filter: '{keyword_filter}'")

            results = collection.query(
                query_embeddings=[query_embedding],  # Lista con una sola query
                n_results=top_k,                     # Máximo de resultados
                where=filter_metadata,               # Filtro opcional (None = sin filtro)
                where_document=where_document,       # Filtro por contenido (Query Expansion)
                include=["documents", "metadatas", "distances"]  # Campos a incluir
            )

            # ============================================================
            # CONVERTIR RESULTADOS A SourceDocument
            # ============================================================
            source_docs = []
            # Verificamos que hay resultados antes de iterar
            if results and results["ids"] and results["ids"][0]:
                # enumerate para tener el índice i junto con cada doc_id
                for i, doc_id in enumerate(results["ids"][0]):
                    # Accedemos con [0][i] porque: [0] = primera query, [i] = i-ésimo resultado
                    metadata = results["metadatas"][0][i] if results["metadatas"] else {}
                    document = results["documents"][0][i] if results["documents"] else ""
                    distance = results["distances"][0][i] if results["distances"] else 0.0

                    # ============================================================
                    # CONVERSIÓN: Distancia L2 → Score de similitud (0 a 1)
                    # ============================================================
                    # ChromaDB usa distancia L2 (menor = más cercano = más similar)
                    # Pero queremos un score donde MAYOR = más similar
                    # Fórmula: similitud = 1 / (1 + distancia)
                    #   distancia = 0   → similitud = 1.0 (match perfecto)
                    #   distancia = 1   → similitud = 0.5
                    #   distancia = 9   → similitud = 0.1 (muy diferente)
                    similarity_score = 1.0 / (1.0 + distance)

                    source_docs.append(
                        SourceDocument(
                            document_id=metadata.get("document_id", doc_id),
                            chunk_content=document,
                            metadata=metadata,
                            relevance_score=similarity_score
                        )
                    )

            logger.info(f"Found {len(source_docs)} similar documents")
            return source_docs

        except Exception as e:
            logger.error(f"Similarity search failed: {e}")
            return []  # En caso de error, retorna lista vacía (no lanza excepción)

    async def delete_document(
        self,
        document_id: str,
        collection_name: str = "documents"
    ) -> bool:
        """
        Elimina todos los chunks asociados a un documento.

        Usa filtro por metadatos para encontrar y eliminar todos los chunks
        que pertenecen a ese document_id.

        ¿Por qué por metadatos y no por ID?
        - Un documento genera MÚLTIPLES chunks (ej: un PDF de 50 páginas)
        - Cada chunk tiene su propio ID único
        - Pero todos comparten el mismo document_id en sus metadatos
        - Con where={"document_id": X} eliminamos todos de una vez

        Args:
            document_id: ID del documento (todos sus chunks se eliminan)
            collection_name: Colección donde está el documento

        Returns:
            bool: True si la operación fue exitosa
        """
        try:
            collection = self._get_or_create_collection(collection_name)

            # where funciona como un filtro WHERE en SQL
            # Elimina todos los chunks con ese document_id en metadatos
            collection.delete(
                where={"document_id": document_id}
            )

            logger.info(f"Deleted chunks for document: {document_id}")
            return True

        except Exception as e:
            logger.error(f"Failed to delete document {document_id}: {e}")
            return False

    async def collection_exists(self, collection_name: str) -> bool:
        """
        Verifica si una colección existe en ChromaDB.

        Obtiene la lista de todas las colecciones del servidor
        y comprueba si alguna tiene el nombre buscado.

        any(): retorna True si al menos un elemento cumple la condición
        Equivalente JS: collections.some(col => col.name === collectionName)

        Args:
            collection_name: Nombre de la colección a buscar

        Returns:
            bool: True si la colección existe
        """
        try:
            client = self._get_client()
            collections = client.list_collections()
            # any() con generator expression: eficiente porque se detiene
            # en el primer match (no recorre toda la lista si ya encontró)
            return any(col.name == collection_name for col in collections)
        except Exception as e:
            logger.error(f"Failed to check collection existence: {e}")
            return False

    async def get_collection_stats(
        self,
        collection_name: str = "documents"
    ) -> Dict[str, Any]:
        """
        Obtiene estadísticas de una colección de ChromaDB.

        collection.count() retorna el número total de chunks almacenados.
        Útil para:
        - Mostrar al usuario cuántos documentos están indexados
        - El endpoint GET /info de la API
        - Verificar que la ingesta funcionó correctamente

        Args:
            collection_name: Colección a consultar

        Returns:
            Dict con estadísticas de la colección
        """
        try:
            collection = self._get_or_create_collection(collection_name)
            # count() retorna el total de embeddings en la colección
            count = collection.count()

            return {
                "collection_name": collection_name,
                "document_count": count,  # Total de chunks almacenados
                "status": "active"
            }

        except Exception as e:
            logger.error(f"Failed to get collection stats: {e}")
            # En error, retornamos estructura válida con el error
            # El frontend no falla al parsear
            return {
                "collection_name": collection_name,
                "document_count": 0,
                "status": "error",
                "error": str(e)
            }
