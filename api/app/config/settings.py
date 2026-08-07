# /api/app/config/settings.py
"""
Centralized application configuration - AIbrarian

This file defines ALL of the system's configuration variables.
Every adapter and service reads its values from here.

What is pydantic_settings?
- Like Zod, but for configuration in Python
- Defines variables with types, defaults and validation
- Automatically loads from environment variables or a .env file
- If a variable fails validation, it fails with a clear error

How does configuration loading work?
Priority (highest to lowest):
    1. System environment variables (OLLAMA_MODEL=mistral)
    2. .env file at the project root
    3. Default values defined in this class

Example:
    # If your .env has:
    # OLLAMA_MODEL=mistral
    # CHROMADB_PORT=9000

    from app.config.settings import settings
    print(settings.ollama_model)  # "mistral" (from .env, not the default)
    print(settings.chromadb_port) # 9000 (from .env)

Global instance:
    At the end of the file: settings = Settings()
    Every module imports this same instance:
        from app.config.settings import settings

TypeScript equivalent with dotenv:
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
# BaseSettings: base class that handles loading env vars automatically
# SettingsConfigDict: configures how variables are read (.env file, etc.)
from pydantic_settings import BaseSettings, SettingsConfigDict
# Field: lets you add metadata and validation to each variable
from pydantic import Field
from typing import Optional
from pathlib import Path

# pydantic-settings resolves a relative env_file against the current
# working directory (CWD) when Settings is instantiated, NOT against
# this file's own location. That worked "by accident" in the two places
# where CWD == api/ (uvicorn launched from api/, and the Docker
# container with WORKDIR /app), but silently broke for the scripts/*.py
# CLI scripts (create_user.py, ingest_pdfs.py, ingest_notion.py), which
# are documented to run from the repo root: there CWD was the project
# root, ".env" didn't exist at that path, and Settings silently fell
# back to the defaults (e.g. DATABASE_URL stayed None even though
# api/.env did have it configured).
# Anchoring the path to this file (api/app/config/settings.py -> api/.env)
# makes it independent from whatever CWD Python is invoked from.
_ENV_FILE = Path(__file__).resolve().parent.parent.parent / ".env"


# ============================================================================
# CONFIGURATION CLASS
# ============================================================================
class Settings(BaseSettings):
    """
    Centralized application configuration.

    Each field is a configuration variable that can be:
    - Overridden by an environment variable (e.g. OLLAMA_MODEL=mistral)
    - Set in the .env file
    - Or fall back to its default value

    Field() lets you add:
    - default: the default value
    - ge/le: range validation (ge = >=, le = <=)
    - description: documentation for the variable
    """

    # ===================================
    # API CONFIGURATION
    # ===================================
    app_name: str = Field(default="AIbrarian API", description="Application name")
    app_version: str = Field(default="0.1.0", description="Application version")
    debug: bool = Field(default=False, description="Debug mode")
    # In production: debug=False (doesn't expose internal errors)
    # In development: debug=True (shows full stack traces)

    # ===================================
    # PROVIDER SELECTION (local vs. cloud deployment)
    # ===================================
    # Lets you pick, at startup, which concrete adapter main.py uses,
    # without touching code. The defaults reproduce the usual local
    # setup (native Ollama + ChromaDB in Docker); on Render these get
    # overridden by environment variables to "groq" / "chroma_cloud".
    llm_provider: str = Field(
        default="ollama",
        description="LLM provider: 'ollama' (local, Metal GPU) or 'groq' (cloud, free)"
    )
    vector_db_provider: str = Field(
        default="chromadb_local",
        description="Vector DB provider: 'chromadb_local' (Docker) or 'chroma_cloud' (managed)"
    )

    # ===================================
    # OLLAMA CONFIGURATION
    # ===================================
    ollama_base_url: str = Field(
        default="http://localhost:11434",  # Ollama's default port
        description="Base URL for Ollama API"
    )
    ollama_model: str = Field(
        default="llama3.2",                # Conversational model
        description="Ollama model to use for text generation"
    )
    ollama_embedding_model: str = Field(
        default="nomic-embed-text",        # Embedding model (768 dims)
        description="Ollama model to use for embeddings"
    )
    ollama_timeout: int = Field(
        default=120,                       # 2 minutes max per request
        description="Timeout for Ollama requests in seconds"
    )

    # ===================================
    # CHROMADB CONFIGURATION
    # ===================================
    chromadb_host: str = Field(
        default="localhost",               # ChromaDB running locally
        description="ChromaDB host"
    )
    chromadb_port: int = Field(
        default=8001,                      # ChromaDB's default port
        description="ChromaDB port"
    )
    chromadb_collection_name: str = Field(
        default="aibrarian_docs",      # Default collection
        description="Default ChromaDB collection name"
    )

    # ===================================
    # DOCUMENT PROCESSING CONFIGURATION
    # ===================================
    chunk_size: int = Field(
        default=1000,                      # ~200 words per chunk
        description="Default chunk size for text splitting"
    )
    chunk_overlap: int = Field(
        default=200,                       # 200 chars of overlap (~40 words)
        description="Overlap between chunks"
    )
    data_directory: str = Field(
        default="./data",                  # Folder where the PDFs live
        description="Directory containing PDF documents"
    )

    # ===================================
    # RAG SYSTEM CONFIGURATION
    # ===================================
    max_context_chunks: int = Field(
        default=4,                         # Max 4 chunks as context
        ge=1,                              # ge = >= 1 (minimum 1 chunk)
        le=10,                             # le = <= 10 (maximum 10 chunks)
        description="Maximum number of chunks to use as context"
    )
    # ge and le are Pydantic validations (like min/max in Zod)
    # If someone sets max_context_chunks=0, Pydantic raises an error automatically

    min_relevance_score: float = Field(
        default=0.3,                       # score = 1/(1+L2_distance); see chromadb_adapter.py
        ge=0.0,
        le=1.0,
        description=(
            "Minimum relevance score for a retrieved chunk to be used as context. "
            "Without this filter, ChromaDB always returns the top_k closest chunks even if "
            "none of them are actually relevant, and the LLM ends up fabricating an answer "
            "instead of admitting it has no information."
        )
    )

    llm_temperature: float = Field(
        default=0.7,                       # Balance between precision and variety
        ge=0.0,                            # Minimum 0.0 (deterministic)
        le=1.0,                            # Maximum 1.0 (very creative)
        description="Temperature for LLM generation"
    )
    rag_temperature: float = Field(
        default=0.3,                       # Precision > variety for the RAG's final answer
        ge=0.0,
        le=1.0,
        description=(
            "Temperature specifically for generating RAGService's final answer "
            "(different from llm_temperature, which is used to build the client and other "
            "calls like extract_keywords)."
        )
    )
    conversation_history_turns: int = Field(
        default=3,                         # 3 turns = 6 messages (user+assistant x3)
        ge=0,
        le=10,
        description="Number of previous conversation turns to include as context in the prompt"
    )
    llm_max_tokens: Optional[int] = Field(
        default=None,                      # None = no token limit
        description="Maximum tokens in LLM response"
    )
    # Optional[int] = can be int or None
    # TypeScript equivalent: number | null

    # ===================================
    # GROQ CONFIGURATION (llm_provider="groq")
    # ===================================
    groq_api_key: Optional[str] = Field(
        default=None,                      # Set in .env (sensitive data)
        description="Groq API key (console.groq.com/keys)"
    )
    groq_model: str = Field(
        default="openai/gpt-oss-120b",     # Groq deprecated the llama-3.x models in 2026
        description="Groq model to use for chat completions"
    )

    # ===================================
    # LOCAL EMBEDDINGS CONFIGURATION (used when llm_provider="groq")
    # ===================================
    embedding_model_name: str = Field(
        default="all-MiniLM-L6-v2",        # 384 dims, runs on CPU (both backends use this model)
        description="Local embedding model (same name on both backends)"
    )
    embedding_backend: str = Field(
        default="onnx",
        description=(
            "Backend for generating local embeddings (GroqAdapter, see "
            "adapters/outbound/groq_adapter.py):\n"
            "- 'onnx' (default): chromadb.utils.embedding_functions.ONNXMiniLM_L6_V2, "
            "via onnxruntime (already a chromadb dependency, adds nothing extra). "
            "Recommended for Render's free tier (512MB RAM) — torch alone "
            "adds ~650MB on disk and enough RAM on import to "
            "trigger an OOM before serving a single request.\n"
            "- 'sentence_transformers': more flexible/accurate but requires "
            "`pip install sentence-transformers` separately (not in requirements.txt "
            "for the reason above); meant for local development with more RAM "
            "available, not for the Render deployment."
        )
    )

    # ===================================
    # CHROMA CLOUD CONFIGURATION (vector_db_provider="chroma_cloud")
    # ===================================
    chroma_cloud_api_key: Optional[str] = Field(
        default=None,
        description="Chroma Cloud API key (trychroma.com)"
    )
    chroma_cloud_tenant: Optional[str] = Field(
        default=None,                      # None = resolved automatically from the API key
        description="Chroma Cloud tenant ID (optional if the API key is bound to a single DB)"
    )
    chroma_cloud_database: Optional[str] = Field(
        default=None,                      # None = resolved automatically from the API key
        description="Chroma Cloud database name (optional if the API key is bound to a single DB)"
    )

    # ===================================
    # NOTION CONFIGURATION
    # ===================================
    notion_api_key: Optional[str] = Field(
        default=None,                      # Set in .env (sensitive data)
        description="Notion API key (integration token)"
    )
    notion_database_id: Optional[str] = Field(
        default=None,                      # Only needed if you want to sync a database
        description="Notion database ID (optional, for batch sync)"
    )

    # ===================================
    # AUTHENTICATION CONFIGURATION (Postgres/Neon + JWT)
    # ===================================
    database_url: Optional[str] = Field(
        default=None,                      # Set in .env / Render (sensitive data)
        description="Postgres connection string for users/authentication (Neon in prod, local container in dev)"
    )
    jwt_secret_key: Optional[str] = Field(
        default=None,                      # Set in .env / Render (sensitive data)
        description="Secret used to sign/verify session JWTs"
    )
    jwt_algorithm: str = Field(
        default="HS256",
        description="Signing algorithm for session JWTs"
    )
    jwt_expiration_minutes: int = Field(
        default=1440,                      # 24 hours
        ge=1,
        description="Session (JWT) duration in minutes before it expires"
    )
    frontend_url: str = Field(
        default="http://localhost:5173",
        description="Exact frontend origin: used for CORS (allow_origins). No longer used for cookie SameSite — the session token moved from an httpOnly cookie to an Authorization header, see adapters that read HTTPBearer in main.py."
    )

    # ===================================
    # PYDANTIC SETTINGS CONFIGURATION
    # ===================================
    # model_config controls how variable loading behaves
    model_config = SettingsConfigDict(
        env_file=_ENV_FILE,                # Reads variables from api/.env, regardless of CWD (see the comment next to the Path import above)
        env_file_encoding="utf-8",         # File encoding
        case_sensitive=False,              # OLLAMA_MODEL = ollama_model (interchangeable)
        extra="ignore"                     # Ignore env vars not defined here
    )

    # ===================================
    # ADDITIONAL METHODS
    # ===================================

    @property
    def chromadb_url(self) -> str:
        """
        Builds ChromaDB's full URL from the host and port.

        @property: accessed as an attribute, not as a method.
        JS equivalent: get chromadbUrl() { return `http://${this.host}:${this.port}` }

        Example:
            settings.chromadb_url  # "http://localhost:8000" (no parentheses)
        """
        return f"http://{self.chromadb_host}:{self.chromadb_port}"

    def model_dump_safe(self) -> dict:
        """
        Exports the configuration while hiding sensitive data.

        model_dump(): Pydantic method that converts the model to a dict
        (equivalent to toJSON() in JS).

        Before returning, masks the Notion API key so it doesn't show up
        in logs or API responses.

        Example:
            config = settings.model_dump_safe()
            # config["notion_api_key"] = "***MASKED***"
        """
        data = self.model_dump()
        # Mask sensitive data before exporting
        if data.get("notion_api_key"):
            data["notion_api_key"] = "***MASKED***"
        if data.get("database_url"):
            data["database_url"] = "***MASKED***"
        if data.get("jwt_secret_key"):
            data["jwt_secret_key"] = "***MASKED***"
        return data


# ============================================================================
# GLOBAL INSTANCE (SINGLETON)
# ============================================================================
# A SINGLE instance is created, imported by every module.
# Python only executes this module once, so settings always points to
# the same object. It's an implicit singleton.
#
# Usage in other files:
#     from app.config.settings import settings
#     print(settings.ollama_model)  # "llama3.2"
settings = Settings()
