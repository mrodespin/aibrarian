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
            <h4 className="text-sm font-medium text-gray-500 mb-2">Servicios</h4>
            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <span className="text-sm">API FastAPI</span>
                <Badge variant={health.api ? 'success' : 'error'}>
                  {health.api ? 'Conectado' : 'Desconectado'}
                </Badge>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-sm">Ollama (LLM)</span>
                <Badge variant={health.ollama ? 'success' : 'error'}>
                  {health.ollama ? 'Conectado' : 'Desconectado'}
                </Badge>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-sm">ChromaDB</span>
                <Badge variant={health.chromadb ? 'success' : 'error'}>
                  {health.chromadb ? 'Conectado' : 'Desconectado'}
                </Badge>
              </div>
            </div>
          </div>

          {/* Collection stats */}
          <div>
            <h4 className="text-sm font-medium text-gray-500 mb-2">Colección</h4>
            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <span className="text-sm">Documentos</span>
                <span className="font-mono text-sm font-semibold">
                  {stats.documentCount}
                </span>
              </div>
              {stats.collectionName && (
                <div className="flex items-center justify-between">
                  <span className="text-sm">Nombre</span>
                  <span className="font-mono text-xs text-gray-600 truncate max-w-32" title={stats.collectionName}>
                    {stats.collectionName}
                  </span>
                </div>
              )}
            </div>
          </div>

          {/* Model info */}
          {stats.modelInfo && (
            <div>
              <h4 className="text-sm font-medium text-gray-500 mb-2">Modelo</h4>
              <div className="space-y-2">
                <div className="flex items-center justify-between">
                  <span className="text-sm">LLM</span>
                  <span className="font-mono text-xs text-gray-600">
                    {stats.modelInfo.model_name || 'N/A'}
                  </span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-sm">Embeddings</span>
                  <span className="font-mono text-xs text-gray-600">
                    {stats.modelInfo.embedding_model || 'N/A'}
                  </span>
                </div>
              </div>
            </div>
          )}

          {/* Refresh button */}
          <button
            onClick={refreshAll}
            className="w-full text-sm text-blue-600 hover:underline mt-2"
          >
            Actualizar estado
          </button>
        </div>
      )}
    </Card>
  );
}

export default StatsPanel;
