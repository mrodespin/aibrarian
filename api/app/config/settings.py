# /api/app/config/settings.py

"""
Application settings using Pydantic Settings.
Configuration can be loaded from environment variables or .env file.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field
from typing import Optional


class Settings(BaseSettings):
    """Application configuration settings."""

    # ===================================
    # API Configuration
    # ===================================
    app_name: str = Field(default="Bibliotecario-IA API", description="Application name")
    app_version: str = Field(default="0.1.0", description="Application version")
    debug: bool = Field(default=False, description="Debug mode")

    # ===================================
    # Ollama Configuration
    # ===================================
    ollama_base_url: str = Field(
        default="http://localhost:11434",
        description="Base URL for Ollama API"
    )
    ollama_model: str = Field(
        default="llama3.2",
        description="Ollama model to use for text generation"
    )
    ollama_embedding_model: str = Field(
        default="nomic-embed-text",
        description="Ollama model to use for embeddings"
    )
    ollama_timeout: int = Field(
        default=120,
        description="Timeout for Ollama requests in seconds"
    )

    # ===================================
    # ChromaDB Configuration
    # ===================================
    chromadb_host: str = Field(
        default="localhost",
        description="ChromaDB host"
    )
    chromadb_port: int = Field(
        default=8000,
        description="ChromaDB port"
    )
    chromadb_collection_name: str = Field(
        default="bibliotecario_docs",
        description="Default ChromaDB collection name"
    )

    # ===================================
    # Document Processing Configuration
    # ===================================
    chunk_size: int = Field(
        default=1000,
        description="Default chunk size for text splitting"
    )
    chunk_overlap: int = Field(
        default=200,
        description="Overlap between chunks"
    )
    data_directory: str = Field(
        default="./data",
        description="Directory containing PDF documents"
    )

    # ===================================
    # RAG Configuration
    # ===================================
    max_context_chunks: int = Field(
        default=4,
        ge=1,
        le=10,
        description="Maximum number of chunks to use as context"
    )
    llm_temperature: float = Field(
        default=0.7,
        ge=0.0,
        le=1.0,
        description="Temperature for LLM generation"
    )
    llm_max_tokens: Optional[int] = Field(
        default=None,
        description="Maximum tokens in LLM response"
    )

    # ===================================
    # Notion Configuration
    # ===================================
    notion_api_key: Optional[str] = Field(
        default=None,
        description="Notion API key (integration token)"
    )
    notion_database_id: Optional[str] = Field(
        default=None,
        description="Notion database ID (optional, for batch sync)"
    )

    # Model configuration
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore"
    )

    @property
    def chromadb_url(self) -> str:
        """Get full ChromaDB URL."""
        return f"http://{self.chromadb_host}:{self.chromadb_port}"

    def model_dump_safe(self) -> dict:
        """Dump settings without sensitive information."""
        data = self.model_dump()
        # Mask sensitive fields
        if data.get("notion_api_key"):
            data["notion_api_key"] = "***MASKED***"
        return data


# Global settings instance
settings = Settings()
