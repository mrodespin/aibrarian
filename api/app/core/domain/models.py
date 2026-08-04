# /api/app/core/domain/models.py
"""
Modelos del Dominio - TFM Bibliotecario-IA

Este archivo define las estructuras de datos (entidades) del proyecto.
En arquitectura hexagonal, el dominio es el núcleo que NO depende de nada externo.

Usamos Pydantic para:
- Validación automática de datos
- Serialización JSON
- Documentación automática en Swagger/OpenAPI

Equivalente en TypeScript: interfaces + Zod para validación
"""

# ============================================================================
# IMPORTS
# ============================================================================
from typing import List, Optional, Dict, Any  # Tipos de Python (como TypeScript types)
from datetime import datetime                  # Para manejar fechas y timestamps
from pydantic import BaseModel, Field          # Pydantic: validación de schemas (como Zod en JS)
from enum import Enum                          # Para crear enumeraciones (tipos fijos)


# ============================================================================
# ENUMERACIONES
# ============================================================================
class DocumentSource(str, Enum):
    """
    Tipos de fuentes de documentos soportadas.

    Hereda de (str, Enum) para que los valores sean strings serializables.

    Equivalente TypeScript:
        enum DocumentSource {
            PDF = "pdf",
            NOTION = "notion",
            TEXT = "text"
        }
    """
    PDF = "pdf"        # Documentos PDF locales
    NOTION = "notion"  # Páginas de Notion
    TEXT = "text"      # Texto plano


# ============================================================================
# ENTIDADES PRINCIPALES
# ============================================================================
class Document(BaseModel):
    """
    Representa un documento completo (PDF o página de Notion).

    Esta es la entidad principal que se carga desde las fuentes.
    Un Document se divide en múltiples Chunks para el procesamiento RAG.

    Atributos:
        id: Identificador único (generado con UUID)
        source: Tipo de fuente (pdf, notion, text)
        content: Texto completo extraído del documento
        metadata: Información adicional (nombre archivo, páginas, URL, etc.)
        created_at: Fecha de creación/ingesta

    Equivalente TypeScript:
        interface Document {
            id: string;
            source: DocumentSource;
            content: string;
            metadata?: Record<string, any>;
            created_at?: Date;
        }
    """
    # Field(...) = campo obligatorio (el ... significa "required")
    # Field(default=X) = campo opcional con valor por defecto

    id: str = Field(..., description="Identificador único del documento")
    source: DocumentSource = Field(..., description="Tipo de fuente (pdf, notion, text)")
    content: str = Field(..., description="Contenido textual completo del documento")
    metadata: Dict[str, Any] = Field(
        default_factory=dict,  # default_factory=dict crea un {} nuevo para cada instancia
        description="Metadatos adicionales (filename, page_count, url, etc.)"
    )
    created_at: datetime = Field(
        default_factory=datetime.now,  # Se genera automáticamente al crear
        description="Timestamp de creación"
    )

    class Config:
        """Configuración de Pydantic para este modelo."""
        json_schema_extra = {
            "example": {
                "id": "doc_123",
                "source": "pdf",
                "content": "Este es el contenido del documento...",
                "metadata": {"filename": "manual.pdf", "page_count": 10}
            }
        }


class Chunk(BaseModel):
    """
    Representa un fragmento de texto de un documento.

    ¿Por qué dividir en chunks?
    - Los LLMs tienen límite de contexto (tokens)
    - La búsqueda vectorial funciona mejor con textos cortos
    - Permite encontrar secciones específicas relevantes

    Típicamente un chunk tiene 500-1000 caracteres con overlap de 100-200.

    Atributos:
        id: Identificador único del chunk (ej: "doc_123_chunk_0")
        document_id: Referencia al documento padre
        content: Texto del fragmento
        embedding: Vector numérico que representa el "significado" del texto
                   (lista de ~768 floats generados por el modelo de embeddings)
        metadata: Info adicional (número de página, posición, etc.)
    """
    id: str = Field(..., description="Identificador único del chunk")
    document_id: str = Field(..., description="ID del documento padre (foreign key)")
    content: str = Field(..., description="Texto del fragmento")
    embedding: Optional[List[float]] = Field(
        None,  # None = puede ser null/undefined
        description="Vector embedding (lista de ~768 floats). Se genera con el modelo de embeddings."
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Metadatos del chunk (page, position, source_file, etc.)"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "id": "chunk_456",
                "document_id": "doc_123",
                "content": "Este es un fragmento de texto del documento...",
                "metadata": {"page": 1, "position": 0}
            }
        }


# ============================================================================
# AUTENTICACIÓN
# ============================================================================
class User(BaseModel):
    """
    Representa un usuario con acceso al sistema.

    No hay UI de registro: los usuarios se dan de alta con
    scripts/create_user.py y se guardan en Postgres (Neon).

    IMPORTANTE: password_hash es un dato sensible. Este modelo se usa
    entre el adapter y los servicios (capa interna) — nunca se devuelve
    directamente desde un endpoint de la API. main.py define su propio
    UserResponse (sin password_hash) para eso, igual que ya separa
    HealthResponse de los modelos de dominio.

    Atributos:
        id: Identificador único (autoincremental en Postgres)
        email: Email del usuario, usado como login
        password_hash: Hash bcrypt de la contraseña
        is_active: Si el usuario puede iniciar sesión
        created_at: Fecha de creación de la cuenta

    Equivalente TypeScript:
        interface User {
            id: number;
            email: string;
            passwordHash: string;
            isActive: boolean;
            createdAt: Date;
        }
    """
    id: int = Field(..., description="Identificador único del usuario (autoincremental)")
    email: str = Field(..., description="Email del usuario, usado como login")
    password_hash: str = Field(..., description="Hash bcrypt de la contraseña (dato sensible, nunca se expone en respuestas de la API)")
    is_active: bool = Field(default=True, description="Si el usuario puede iniciar sesión")
    created_at: datetime = Field(
        default_factory=datetime.now,
        description="Fecha de creación de la cuenta"
    )


# ============================================================================
# MODELOS DE CONSULTA (INPUT/OUTPUT DEL SISTEMA RAG)
# ============================================================================
class Query(BaseModel):
    """
    Representa una consulta/pregunta del usuario al sistema RAG.

    Este es el INPUT del endpoint POST /ask.

    Atributos:
        question: La pregunta en lenguaje natural
        session_id: (Opcional) Para mantener contexto entre preguntas
        max_results: Cuántos chunks de contexto recuperar (default: 4)

    Validaciones:
        - question: mínimo 1 carácter (no puede estar vacía)
        - max_results: entre 1 y 10 (ge=greater or equal, le=less or equal)
    """
    question: str = Field(
        ...,
        min_length=1,  # Validación: no puede estar vacía
        description="Pregunta del usuario en lenguaje natural"
    )
    session_id: Optional[str] = Field(
        None,
        description="ID de sesión para conversaciones con contexto (futuro)"
    )
    max_results: int = Field(
        default=4,
        ge=1,   # ge = greater or equal (>=)
        le=10,  # le = less or equal (<=)
        description="Número máximo de chunks de contexto a recuperar"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "question": "¿Cuál es el tema principal del documento?",
                "session_id": "session_789",
                "max_results": 4
            }
        }


class ConversationMessage(BaseModel):
    """
    Representa un turno (mensaje) del historial de una conversación.

    Persistido en Postgres (conversation_messages) por ConversationService,
    y usado para dar contexto de turnos previos al generar una respuesta
    (ver RAGService.ask_question y OllamaAdapter.generate_response).

    Atributos:
        role: "user" o "assistant"
        content: Texto del mensaje (pregunta o respuesta)
        created_at: Momento en que se guardó el mensaje
    """
    role: str = Field(..., description="'user' o 'assistant'")
    content: str = Field(..., description="Texto del mensaje")
    created_at: datetime = Field(..., description="Momento en que se guardó el mensaje")


class SourceDocument(BaseModel):
    """
    Representa una fuente usada para generar una respuesta.

    Cuando el sistema responde una pregunta, incluye las fuentes
    de donde extrajo la información (para transparencia y verificación).

    Atributos:
        document_id: ID del documento original
        chunk_content: El texto del chunk que se usó como contexto
        metadata: Info del documento (filename, page, etc.)
        relevance_score: Puntuación de similitud (0-1, mayor = más relevante)
    """
    document_id: str = Field(..., description="ID del documento fuente")
    chunk_content: str = Field(..., description="Texto del chunk usado como contexto")
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Metadatos de la fuente (filename, page, url, etc.)"
    )
    relevance_score: Optional[float] = Field(
        None,
        description="Score de relevancia/similitud (0.0 a 1.0)"
    )


class QueryResult(BaseModel):
    """
    Resultado completo de una consulta RAG.

    Este es el OUTPUT del endpoint POST /ask.
    Incluye la respuesta generada Y las fuentes utilizadas.

    Atributos:
        question: La pregunta original (eco)
        answer: Respuesta generada por el LLM
        source_documents: Lista de fuentes usadas para generar la respuesta
        session_id: ID de sesión (si se proporcionó)
        processing_time: Tiempo de procesamiento en segundos
    """
    question: str = Field(..., description="Pregunta original")
    answer: str = Field(..., description="Respuesta generada por el LLM")
    source_documents: List[SourceDocument] = Field(
        default_factory=list,
        description="Fuentes usadas para generar la respuesta"
    )
    session_id: Optional[str] = Field(None, description="ID de sesión")
    processing_time: Optional[float] = Field(
        None,
        description="Tiempo de procesamiento en segundos"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "question": "¿Qué es RAG?",
                "answer": "RAG (Retrieval-Augmented Generation) es una técnica que...",
                "source_documents": [
                    {
                        "document_id": "doc_123",
                        "chunk_content": "RAG es una técnica de IA que...",
                        "metadata": {"page": 1},
                        "relevance_score": 0.95
                    }
                ],
                "processing_time": 1.23
            }
        }


class DocumentSummary(BaseModel):
    """
    Resumen de un documento indexado, para listarlo sin pasar por
    similarity search (a diferencia de SourceDocument, que representa
    un CHUNK usado como contexto de una respuesta concreta).

    Es el resultado de agrupar todos los chunks de un mismo document_id
    en la base de datos vectorial. Se usa tanto en GET /documents (para
    que el usuario pueda explorar la base de conocimiento desde el UI)
    como en RAGService para responder preguntas del tipo "¿cuántos
    documentos conoces?" sin depender del retrieval semántico (ver
    LLMPort.is_catalog_question).

    Atributos:
        document_id: ID del documento (ej: "notion_abc123", "pdf_a3f2b1c9")
        title: Título legible — de metadata.title/filename, o el propio
               document_id como último fallback
        source: "pdf" | "notion" | "unknown", inferido del prefijo del id
        chunk_count: Cuántos chunks tiene este documento en la colección
    """
    document_id: str = Field(..., description="ID del documento")
    title: str = Field(..., description="Título legible del documento")
    source: str = Field(..., description="Fuente del documento: pdf, notion o unknown")
    chunk_count: int = Field(..., description="Número de chunks de este documento en la colección")


# ============================================================================
# MODELOS DE SINCRONIZACIÓN/INGESTA
# ============================================================================
class SyncResult(BaseModel):
    """
    Resultado de una operación de sincronización/ingesta de documentos.

    Este es el OUTPUT de los endpoints POST /sync y POST /sync/notion.

    Atributos:
        document_id: ID del documento procesado
        chunks_created: Número de chunks generados
        success: Si la operación fue exitosa
        message: Mensaje informativo o de error
        processing_time: Tiempo de procesamiento en segundos
    """
    document_id: str = Field(..., description="ID del documento procesado")
    chunks_created: int = Field(..., description="Número de chunks creados")
    success: bool = Field(..., description="Si la operación fue exitosa")
    message: Optional[str] = Field(
        None,
        description="Mensaje informativo o de error"
    )
    processing_time: Optional[float] = Field(
        None,
        description="Tiempo de procesamiento en segundos"
    )
