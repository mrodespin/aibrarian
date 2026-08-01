/**
 * Etiquetas legibles para los proveedores configurados en el backend
 * (settings.llm_provider / settings.vector_db_provider, ver api/app/config/settings.py).
 * El endpoint /health expone esos valores en `config.llm_provider` /
 * `config.vector_db_provider` — se usan aquí para no dejar "Ollama"/"ChromaDB"
 * fijos en la UI cuando en realidad está corriendo Groq/Chroma Cloud (Render).
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
