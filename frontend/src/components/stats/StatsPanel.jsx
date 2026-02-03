/**
 * Collection statistics panel
 */

import { useApp } from '../../context/AppContext';
import { Card, Badge, Spinner } from '../common';

export function StatsPanel() {
  const { stats, health, isLoading, refreshAll } = useApp();

  return (
    <Card title="Estado del Sistema">
      {isLoading ? (
        <div className="flex justify-center py-4">
          <Spinner />
        </div>
      ) : (
        <div className="space-y-4">
          {/* Services status */}
          <div>
            <h4 className="text-sm font-medium text-text-300 mb-2">Servicios</h4>
            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <span className="text-sm text-text-200">API FastAPI</span>
                <Badge variant={health.api ? 'success' : 'error'}>
                  {health.api ? 'Conectado' : 'Desconectado'}
                </Badge>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-sm text-text-200">Ollama (LLM)</span>
                <Badge variant={health.ollama ? 'success' : 'error'}>
                  {health.ollama ? 'Conectado' : 'Desconectado'}
                </Badge>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-sm text-text-200">ChromaDB</span>
                <Badge variant={health.chromadb ? 'success' : 'error'}>
                  {health.chromadb ? 'Conectado' : 'Desconectado'}
                </Badge>
              </div>
            </div>
          </div>

          {/* Collection stats */}
          <div>
            <h4 className="text-sm font-medium text-text-300 mb-2">Colección</h4>
            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <span className="text-sm text-text-200">Documentos</span>
                <span className="font-mono text-sm font-semibold text-text-50">
                  {stats.documentCount}
                </span>
              </div>
              {stats.collectionName && (
                <div className="flex items-center justify-between">
                  <span className="text-sm text-text-200">Nombre</span>
                  <span className="font-mono text-xs text-text-200 truncate max-w-32" title={stats.collectionName}>
                    {stats.collectionName}
                  </span>
                </div>
              )}
            </div>
          </div>

          {/* Model info */}
          {stats.modelInfo && (
            <div>
              <h4 className="text-sm font-medium text-text-300 mb-2">Modelo</h4>
              <div className="space-y-2">
                <div className="flex items-center justify-between">
                  <span className="text-sm text-text-200">LLM</span>
                  <span className="font-mono text-xs text-text-200">
                    {stats.modelInfo.model_name || 'N/A'}
                  </span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-sm text-text-200">Embeddings</span>
                  <span className="font-mono text-xs text-text-200">
                    {stats.modelInfo.embedding_model || 'N/A'}
                  </span>
                </div>
              </div>
            </div>
          )}

          {/* Refresh button */}
          <button
            onClick={refreshAll}
            className="w-full text-sm text-accent-400 hover:text-accent-300 transition-colors mt-2"
          >
            Actualizar estado
          </button>
        </div>
      )}
    </Card>
  );
}

export default StatsPanel;
