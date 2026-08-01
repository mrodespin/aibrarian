# /api/app/config/settings.py
"""
Configuración centralizada de la aplicación - TFM Bibliotecario-IA

Este archivo define TODAS las variables de configuración del sistema.
Todos los adaptadores y servicios leen sus valores desde aquí.

¿Qué es pydantic_settings?
- Como Zod pero para configuración en Python
- Define variables con tipos, valores por defecto y validación
- Carga automáticamente desde variables de entorno o archivo .env
- Si una variable no cumple la validación, falla con error claro

¿Cómo funciona la carga de configuración?
Prioridad (de mayor a menor):
    1. Variables de entorno del sistema (OLLAMA_MODEL=mistral)
    2. Archivo .env en la raíz del proyecto
    3. Valores por defecto definidos en esta clase

Ejemplo:
    # Si tienes en .env:
    # OLLAMA_MODEL=mistral
    # CHROMADB_PORT=9000

    from app.config.settings import settings
    print(settings.ollama_model)  # "mistral" (de .env, no el default)
    print(settings.chromadb_port) # 9000 (de .env)

Instancia global:
    Al final del archivo se crea: settings = Settings()
    Todos los módulos importan esta misma instancia:
        from app.config.settings import settings

Equivalente en TypeScript con dotenv:
    // config.ts
    export const settings = {
        ollama_model: process.env.OLLAMA_MODEL || "llama3.2",
        chromadb_port: parseInt(process.env.CHROMADB_PORT || "8000"),
        // ...
    }
"""

# ============================================================================
# IMPORTS
# ============================================================================
# BaseSettings: clase base que integra carga de env vars automáticamente
# SettingsConfigDict: configura cómo se leen las variables (archivo .env, etc.)
from pydantic_settings import BaseSettings, SettingsConfigDict
# Field: permite añadir metadatos y validación a cada variable
from pydantic import Field
from typing import Optional


# ============================================================================
# CLASE DE CONFIGURACIÓN
# ============================================================================
class Settings(BaseSettings):
    """
    Configuración centralizada de la aplicación.

    Cada campo es una variable de configuración que puede ser:
    - Cambiada por variable de entorno (ej: OLLAMA_MODEL=mistral)
    - Definida en el archivo .env
    - O usar el valor por defecto

    Field() permite añadir:
    - default: valor por defecto
    - ge/le: validación de rango (ge = >=, le = <=)
    - description: documentación de la variable
    """

    # ===================================
    # CONFIGURACIÓN DE LA API
    # ===================================
    app_name: str = Field(default="Bibliotecario-IA API", description="Application name")
    app_version: str = Field(default="0.1.0", description="Application version")
    debug: bool = Field(default=False, description="Debug mode")
    # En producción: debug=False (no muestra errores internos)
    # En desarrollo: debug=True (muestra stack traces completos)

    # ===================================
    # SELECCIÓN DE PROVEEDORES (local vs. cloud deployment)
    # ===================================
    # Permite elegir en tiempo de arranque qué adaptador concreto usa main.py,
    # sin tocar código. Los defaults reproducen el setup local de siempre
    # (Ollama nativo + ChromaDB en Docker); en Render se sobreescriben por
    # variables de entorno a "groq" / "chroma_cloud".
    llm_provider: str = Field(
        default="ollama",
        description="Proveedor de LLM: 'ollama' (local, GPU Metal) o 'groq' (cloud, gratuito)"
    )
    vector_db_provider: str = Field(
        default="chromadb_local",
        description="Proveedor de vector DB: 'chromadb_local' (Docker) o 'chroma_cloud' (gestionado)"
    )

    # ===================================
    # CONFIGURACIÓN DE OLLAMA
    # ===================================
    ollama_base_url: str = Field(
        default="http://localhost:11434",  # Puerto por defecto de Ollama
        description="Base URL for Ollama API"
    )
    ollama_model: str = Field(
        default="llama3.2",                # Modelo conversacional
        description="Ollama model to use for text generation"
    )
    ollama_embedding_model: str = Field(
        default="nomic-embed-text",        # Modelo de embeddings (768 dims)
        description="Ollama model to use for embeddings"
    )
    ollama_timeout: int = Field(
        default=120,                       # 2 minutos máximo por petición
        description="Timeout for Ollama requests in seconds"
    )

    # ===================================
    # CONFIGURACIÓN DE CHROMADB
    # ===================================
    chromadb_host: str = Field(
        default="localhost",               # ChromaDB corriendo local
        description="ChromaDB host"
    )
    chromadb_port: int = Field(
        default=8001,                      # Puerto por defecto de ChromaDB
        description="ChromaDB port"
    )
    chromadb_collection_name: str = Field(
        default="bibliotecario_docs",      # Colección por defecto
        description="Default ChromaDB collection name"
    )

    # ===================================
    # CONFIGURACIÓN DE PROCESAMIENTO DE DOCUMENTOS
    # ===================================
    chunk_size: int = Field(
        default=1000,                      # ~200 palabras por chunk
        description="Default chunk size for text splitting"
    )
    chunk_overlap: int = Field(
        default=200,                       # 200 chars de overlap (~40 palabras)
        description="Overlap between chunks"
    )
    data_directory: str = Field(
        default="./data",                  # Carpeta donde están los PDFs
        description="Directory containing PDF documents"
    )

    # ===================================
    # CONFIGURACIÓN DEL SISTEMA RAG
    # ===================================
    max_context_chunks: int = Field(
        default=4,                         # Máximo 4 chunks como contexto
        ge=1,                              # ge = >= 1 (mínimo 1 chunk)
        le=10,                             # le = <= 10 (máximo 10 chunks)
        description="Maximum number of chunks to use as context"
    )
    # ge y le son validaciones de Pydantic (como min/max en Zod)
    # Si alguien pone max_context_chunks=0, Pydantic lanza error automáticamente

    llm_temperature: float = Field(
        default=0.7,                       # Balance entre precisión y variedad
        ge=0.0,                            # Mínimo 0.0 (determinista)
        le=1.0,                            # Máximo 1.0 (muy creativo)
        description="Temperature for LLM generation"
    )
    llm_max_tokens: Optional[int] = Field(
        default=None,                      # None = sin límite de tokens
        description="Maximum tokens in LLM response"
    )
    # Optional[int] = puede ser int o None
    # Equivalente TypeScript: number | null

    # ===================================
    # CONFIGURACIÓN DE GROQ (llm_provider="groq")
    # ===================================
    groq_api_key: Optional[str] = Field(
        default=None,                      # Se configura en .env (dato sensible)
        description="Groq API key (console.groq.com/keys)"
    )
    groq_model: str = Field(
        default="openai/gpt-oss-120b",     # Groq deprecó los modelos llama-3.x en 2026
        description="Groq model to use for chat completions"
    )

    # ===================================
    # CONFIGURACIÓN DE EMBEDDINGS LOCALES (usado cuando llm_provider="groq")
    # ===================================
    embedding_model_name: str = Field(
        default="all-MiniLM-L6-v2",        # 384 dims, corre en CPU (ambos backends usan este modelo)
        description="Modelo de embeddings locales (mismo nombre en ambos backends)"
    )
    embedding_backend: str = Field(
        default="onnx",
        description=(
            "Backend para generar embeddings locales (GroqAdapter, ver "
            "adapters/outbound/groq_adapter.py):\n"
            "- 'onnx' (default): chromadb.utils.embedding_functions.ONNXMiniLM_L6_V2, "
            "vía onnxruntime (ya es dependencia de chromadb, no añade nada extra). "
            "Recomendado para Render free tier (512MB RAM) — torch por sí solo "
            "añade ~650MB en disco y suficiente RAM en el import como para "
            "provocar un OOM antes de atender ninguna petición.\n"
            "- 'sentence_transformers': más flexible/preciso pero requiere "
            "`pip install sentence-transformers` aparte (no está en requirements.txt "
            "por el motivo de arriba); pensado para desarrollo local con más RAM "
            "disponible, no para el deploy en Render."
        )
    )

    # ===================================
    # CONFIGURACIÓN DE CHROMA CLOUD (vector_db_provider="chroma_cloud")
    # ===================================
    chroma_cloud_api_key: Optional[str] = Field(
        default=None,
        description="Chroma Cloud API key (trychroma.com)"
    )
    chroma_cloud_tenant: Optional[str] = Field(
        default=None,                      # None = se resuelve automáticamente desde la API key
        description="Chroma Cloud tenant ID (opcional si la API key está ligada a una sola BD)"
    )
    chroma_cloud_database: Optional[str] = Field(
        default=None,                      # None = se resuelve automáticamente desde la API key
        description="Chroma Cloud database name (opcional si la API key está ligada a una sola BD)"
    )

    # ===================================
    # CONFIGURACIÓN DE NOTION
    # ===================================
    notion_api_key: Optional[str] = Field(
        default=None,                      # Se configura en .env (dato sensible)
        description="Notion API key (integration token)"
    )
    notion_database_id: Optional[str] = Field(
        default=None,                      # Solo si quieres sync de una base de datos
        description="Notion database ID (optional, for batch sync)"
    )

    # ===================================
    # CONFIGURACIÓN DE PYDANTIC SETTINGS
    # ===================================
    # model_config controla cómo se comporta la carga de variables
    model_config = SettingsConfigDict(
        env_file=".env",                   # Lee variables del archivo .env
        env_file_encoding="utf-8",         # Encoding del archivo
        case_sensitive=False,              # OLLAMA_MODEL = ollama_model (indistinto)
        extra="ignore"                     # Ignora vars de entorno no definidas aquí
    )

    # ===================================
    # MÉTODOS ADICIONALES
    # ===================================

    @property
    def chromadb_url(self) -> str:
        """
        Genera la URL completa de ChromaDB a partir de host y puerto.

        @property: se accede como atributo, no como método.
        Equivalente JS: get chromadbUrl() { return `http://${this.host}:${this.port}` }

        Ejemplo:
            settings.chromadb_url  # "http://localhost:8000" (sin paréntesis)
        """
        return f"http://{self.chromadb_host}:{self.chromadb_port}"

    def model_dump_safe(self) -> dict:
        """
        Exporta la configuración ocultando datos sensibles.

        model_dump(): método de Pydantic que convierte el modelo a dict
        (equivalente a toJSON() en JS).

        Antes de retornar, enmascara la API key de Notion para que
        no aparezca en logs ni en respuestas de la API.

        Ejemplo:
            config = settings.model_dump_safe()
            # config["notion_api_key"] = "***MASKED***"
        """
        data = self.model_dump()
        # Enmascar datos sensibles antes de exportar
        if data.get("notion_api_key"):
            data["notion_api_key"] = "***MASKED***"
        return data


# ============================================================================
# INSTANCIA GLOBAL (SINGLETON)
# ============================================================================
# Se crea UNA sola instancia que todos los módulos importan.
# Python ejecuta este módulo una sola vez, así que settings siempre
# apunta al mismo objeto. Es un singleton implícito.
#
# Uso en otros archivos:
#     from app.config.settings import settings
#     print(settings.ollama_model)  # "llama3.2"
settings = Settings()
