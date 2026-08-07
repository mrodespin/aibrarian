/**
 * Human-readable labels for the providers configured on the backend
 * (settings.llm_provider / settings.vector_db_provider, see
 * api/app/config/settings.py). The /health endpoint exposes those
 * values in `config.llm_provider` / `config.vector_db_provider` — used
 * here so the UI doesn't hardcode "Ollama"/"ChromaDB" when Groq/Chroma
 * Cloud (Render) is actually running.
 */

export function llmProviderLabel(provider) {
  switch (provider) {
    case 'groq':
      return 'Groq';
    case 'ollama':
      return 'Ollama';
    default:
      return 'LLM';
  }
}

export function vectorDbProviderLabel(provider) {
  switch (provider) {
    case 'chroma_cloud':
      return 'Chroma Cloud';
    case 'chromadb_local':
      return 'ChromaDB';
    default:
      return 'Vector DB';
  }
}
