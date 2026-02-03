/**
 * Source document card with relevance score
 */

import { useState } from 'react';
import { Card, Badge } from '../common';

export function SourceCard({ source, index }) {
  const [expanded, setExpanded] = useState(false);

  const relevancePercent = source.relevance_score
    ? Math.round(source.relevance_score * 100)
    : null;

  // Extract filename from metadata
  const fileName =
    source.metadata?.filename ||
    source.metadata?.title ||
    source.metadata?.source_file ||
    source.document_id ||
    'Documento';

  return (
    <Card className="bg-gray-50 border-gray-200" padding={false}>
      <div className="p-3">
        {/* Header */}
        <div className="flex items-center justify-between gap-2">
          <div className="flex items-center gap-2 min-w-0">
            <Badge variant="info">[{index}]</Badge>
            <span className="font-medium text-sm truncate" title={fileName}>
              {fileName}
            </span>
          </div>

          {/* Relevance score */}
          {relevancePercent !== null && (
            <div className="flex items-center gap-2 flex-shrink-0">
              <div className="w-16 h-1.5 bg-gray-200 rounded-full overflow-hidden">
                <div
                  className="h-full bg-green-500 transition-all"
                  style={{ width: `${relevancePercent}%` }}
                />
              </div>
              <span className="text-xs text-gray-500 w-8">{relevancePercent}%</span>
            </div>
          )}
        </div>

        {/* Expand button */}
        <button
          onClick={() => setExpanded(!expanded)}
          className="text-xs text-blue-600 hover:underline mt-2"
        >
          {expanded ? 'Ocultar contenido' : 'Ver contenido'}
        </button>

        {/* Expanded content */}
        {expanded && (
          <div className="mt-3 pt-3 border-t border-gray-200">
            <p className="text-sm text-gray-700 whitespace-pre-wrap leading-relaxed">
              {source.chunk_content || source.content || 'Sin contenido disponible'}
            </p>
            {source.metadata?.page && (
              <p className="text-xs text-gray-500 mt-2">
                Página: {source.metadata.page}
              </p>
            )}
          </div>
        )}
      </div>
    </Card>
  );
}

export default SourceCard;
