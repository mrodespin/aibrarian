/**
 * Collection statistics panel
 */

import { useApp } from '../../hooks/useApp';
import { Card, Badge, Spinner, Button } from '../common';
import { llmProviderLabel, vectorDbProviderLabel } from '../../utils/providerLabels';

export function StatsPanel() {
  const { stats, health, isLoading, isRefreshing, refreshAll } = useApp();

  return (
    <Card title="System Status">
      {isLoading ? (
        <div className="flex justify-center py-4">
          <Spinner />
        </div>
      ) : (
        <div className="space-y-4">
          {/* Services status */}
          <div>
            <h4 className="text-sm font-medium text-text-300 mb-2">Services</h4>
            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <span className="text-sm text-text-200">FastAPI API</span>
                <Badge variant={health.api ? 'success' : 'error'}>
                  {health.api ? 'Connected' : 'Disconnected'}
                </Badge>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-sm text-text-200">{llmProviderLabel(health.llmProvider)} (LLM)</span>
                <Badge variant={health.llm ? 'success' : 'error'}>
                  {health.llm ? 'Connected' : 'Disconnected'}
                </Badge>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-sm text-text-200">{vectorDbProviderLabel(health.vectorDbProvider)}</span>
                <Badge variant={health.vectorDb ? 'success' : 'error'}>
                  {health.vectorDb ? 'Connected' : 'Disconnected'}
                </Badge>
              </div>
            </div>
          </div>

          {/* Collection stats */}
          <div>
            <h4 className="text-sm font-medium text-text-300 mb-2">Collection</h4>
            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <span className="text-sm text-text-200">Documents</span>
                <span className="font-mono text-sm font-semibold text-text-50">
                  {stats.documentCount}
                </span>
              </div>
              {stats.collectionName && (
                <div className="flex items-center justify-between">
                  <span className="text-sm text-text-200">Name</span>
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
              <h4 className="text-sm font-medium text-text-300 mb-2">Model</h4>
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
          <Button
            onClick={refreshAll}
            disabled={isRefreshing}
            className="w-full"
          >
            Refresh status
          </Button>
        </div>
      )}
    </Card>
  );
}

export default StatsPanel;
