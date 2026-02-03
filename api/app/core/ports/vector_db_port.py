# /api/app/core/ports/vector_db_port.py
"""
Puerto (Interfaz) para Base de Datos Vectorial - TFM Bibliotecario-IA

Este archivo define el CONTRATO que debe cumplir cualquier base de datos vectorial.
Es una interfaz abstracta (no tiene implementación, solo define métodos).

¿Qué es un Puerto en Arquitectura Hexagonal?
- Define QUÉ operaciones existen, pero NO CÓMO se implementan
- Permite desacoplar la lógica de negocio de la tecnología específica
- Facilita cambiar ChromaDB por Pinecone sin tocar los servicios

Equivalente en TypeScript:
    interface VectorDBPort {
        storeChunks(chunks: Chunk[]): Promise<boolean>;
        similaritySearch(queryEmbedding: number[]): Promise<SourceDocument[]>;
        deleteDocument(documentId: string): Promise<boolean>;
        collectionExists(name: string): Promise<boolean>;
        getCollectionStats(name: string): Promise<Record<string, any>>;
    }

La implementación real está en: /adapters/outbound/chromadb_adapter.py
"""

# ============================================================================
# IMPORTS
# ============================================================================
# ABC (Abstract Base Class) permite crear clases abstractas en Python
# abstractmethod marca métodos como "obligatorios de implementar"
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
from app.core.domain.models import Chunk, SourceDocument


# ============================================================================
# INTERFAZ DE BASE DE DATOS VECTORIAL
# ============================================================================
class VectorDBPort(ABC):
    """
    Interfaz abstracta para operaciones de base de datos vectorial.

    ¿Qué es una base de datos vectorial?
    - Almacena textos como vectores numéricos (embeddings)
    - Permite buscar textos similares usando distancia coseno
    - Ejemplo: ChromaDB, Pinecone, Weaviate, Milvus

    ¿Cómo funciona?
    1. Texto "El gato negro" → Modelo de embeddings → Vector [0.1, -0.2, 0.3, ...]
    2. Se almacena el vector junto con el texto original
    3. Para buscar: pregunta → vector → buscar vectores similares

    Métodos que debe implementar cualquier adaptador:
    - store_chunks: Guardar fragmentos de texto
    - similarity_search: Buscar textos similares (CORE del RAG)
    - delete_document: Eliminar un documento
    - collection_exists: Verificar si existe una colección
    - get_collection_stats: Obtener estadísticas

    Nota: ABC = Abstract Base Class
    - No se puede instanciar directamente: VectorDBPort() → Error
    - Solo se pueden crear clases que hereden e implementen los métodos
    """

    @abstractmethod
    async def store_chunks(
        self,
        chunks: List[Chunk],
        collection_name: str = "documents"
    ) -> bool:
        """
        Almacena chunks de texto con sus embeddings en la base de datos.

        ¿Qué es un chunk?
        - Fragmento de ~500-1000 caracteres de un documento
        - Incluye: id, contenido, embedding (vector), metadatos

        Args:
            chunks: Lista de objetos Chunk a almacenar
                   Cada chunk debe tener su embedding ya generado
            collection_name: Nombre de la colección (como una "tabla" en SQL)
                           Default: "documents"

        Returns:
            bool: True si se guardó correctamente, False si hubo error

        Ejemplo:
            chunks = [
                Chunk(id="doc1_0", content="Texto...", embedding=[0.1, 0.2, ...]),
                Chunk(id="doc1_1", content="Más texto...", embedding=[0.3, 0.4, ...])
            ]
            success = await vector_db.store_chunks(chunks)

        Nota: async def = función asíncrona (como async function en JavaScript)
        """
        pass  # pass = no hay implementación, la clase hija debe implementar

    @abstractmethod
    async def similarity_search(
        self,
        query_embedding: List[float],
        collection_name: str = "documents",
        top_k: int = 4,
        filter_metadata: Optional[Dict[str, Any]] = None,
        keyword_filter: Optional[str] = None
    ) -> List[SourceDocument]:
        """
        Busca los chunks más similares a un vector de consulta.

        ESTE ES EL MÉTODO MÁS IMPORTANTE DEL SISTEMA RAG.

        ¿Cómo funciona?
        1. Recibe el embedding (vector) de la pregunta del usuario
        2. Compara ese vector con TODOS los vectores almacenados
        3. Usa distancia coseno para medir similitud
        4. Devuelve los top_k chunks más similares

        ¿Qué es distancia coseno?
        - Mide el ángulo entre dos vectores
        - Score 1.0 = vectores idénticos (mismo significado)
        - Score 0.0 = vectores perpendiculares (nada en común)
        - Ejemplo: "perro" y "gato" → ~0.7, "perro" y "avión" → ~0.2

        Query Expansion (búsqueda híbrida):
        Si se proporciona keyword_filter, primero filtra documentos que
        contienen esa palabra clave, luego rankea por similitud semántica.
        Útil para nombres propios y títulos específicos.

        Args:
            query_embedding: Vector de la pregunta (lista de ~768 floats)
                           Generado por el modelo de embeddings (nomic-embed-text)
            collection_name: Colección donde buscar
            top_k: Número de resultados a devolver (default: 4)
            filter_metadata: Filtros opcionales, ej: {"source": "pdf"}
            keyword_filter: Palabra clave para filtrar documentos (Query Expansion)
                          Ejemplo: "Blade Runner" → solo chunks que contengan ese texto

        Returns:
            List[SourceDocument]: Chunks más relevantes con:
                - document_id: ID del documento origen
                - chunk_content: Texto del chunk
                - metadata: Información adicional
                - relevance_score: Puntuación de similitud (0-1)

        Ejemplo:
            # 1. Usuario pregunta: "¿Qué es machine learning?"
            # 2. Se genera embedding de la pregunta
            query_vec = await llm.generate_embedding("¿Qué es machine learning?")
            # query_vec = [0.1, -0.2, 0.3, ...] (768 números)

            # 3. Se buscan chunks similares
            results = await vector_db.similarity_search(query_vec, top_k=5)

            # 4. results[0] = chunk más relevante
            # results[0].relevance_score = 0.92
            # results[0].chunk_content = "Machine learning es una rama de la IA..."
        """
        pass

    @abstractmethod
    async def delete_document(
        self,
        document_id: str,
        collection_name: str = "documents"
    ) -> bool:
        """
        Elimina todos los chunks asociados a un documento.

        ¿Por qué eliminar por document_id y no por chunk_id?
        - Un documento puede tener MUCHOS chunks (PDF 50 páginas = ~100 chunks)
        - Es más práctico eliminar todos a la vez
        - Los chunks tienen document_id como "foreign key"

        Args:
            document_id: ID del documento a eliminar
            collection_name: Colección donde está el documento

        Returns:
            bool: True si se eliminó correctamente

        Ejemplo:
            # Eliminar un PDF que ya no necesitamos
            await vector_db.delete_document("doc_123")
        """
        pass

    @abstractmethod
    async def collection_exists(self, collection_name: str) -> bool:
        """
        Verifica si una colección existe en la base de datos.

        ¿Qué es una colección?
        - Es como una "tabla" en bases de datos relacionales
        - Agrupa chunks relacionados
        - Permite tener múltiples "bases de conocimiento" separadas

        Args:
            collection_name: Nombre de la colección a verificar

        Returns:
            bool: True si existe, False si no

        Útil para:
        - Verificar setup inicial del sistema
        - Crear colección si no existe
        - Validar configuración
        """
        pass

    @abstractmethod
    async def get_collection_stats(
        self,
        collection_name: str = "documents"
    ) -> Dict[str, Any]:
        """
        Obtiene estadísticas de una colección.

        Args:
            collection_name: Nombre de la colección

        Returns:
            Dict con estadísticas, ejemplo:
            {
                "count": 150,              # Número total de chunks
                "dimensions": 768,          # Dimensiones de los embeddings
                "collection_name": "documents"
            }

        Útil para:
        - Endpoint /stats de la API
        - Monitoreo del sistema
        - Verificar que hay documentos cargados
        - Debugging ("¿se indexaron mis PDFs?")
        """
        pass
