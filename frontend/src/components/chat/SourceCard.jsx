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

  // Determine file type icon
  const isPdf = fileName.toLowerCase().includes('.pdf') || source.metadata?.source === 'pdf';
  const isNotion = source.metadata?.source === 'notion';

  return (
    <Card className="bg-bg-800/50 border-bg-700 hover:border-accent-500/50 hover:shadow-lg hover:shadow-accent-500/10 transition-all" padding={false}>
      <div className="p-3">
        {/* Header */}
        <div className="flex items-center justify-between gap-3">
          <div className="flex items-center gap-3 min-w-0 flex-1">
            {/* File icon */}
            <div className={`flex-shrink-0 w-8 h-8 rounded-lg flex items-center justify-center ${
              isPdf ? 'bg-error-500/20 text-error-400' : isNotion ? 'bg-accent-500/20 text-accent-400' : 'bg-violet-500/20 text-violet-400'
            }`}>
              {isPdf ? (
                <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 20 20">
                  <path d="M4 18h12V6h-4V2H4v16zm-2 1V0h10l4 4v16H2v-1z"/>
                  <path d="M7 13h2v-2H7v2zm0-3h2V8H7v2zm3 3h2v-2h-2v2zm0-3h2V8h-2v2z"/>
                </svg>
              ) : isNotion ? (
                <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 20 20">
                  <path d="M9 2a1 1 0 000 2h2a1 1 0 100-2H9z"/>
                  <path fillRule="evenodd" d="M4 5a2 2 0 012-2 3 3 0 003 3h2a3 3 0 003-3 2 2 0 012 2v11a2 2 0 01-2 2H6a2 2 0 01-2-2V5zm3 4a1 1 0 000 2h.01a1 1 0 100-2H7zm3 0a1 1 0 000 2h3a1 1 0 100-2h-3zm-3 4a1 1 0 100 2h.01a1 1 0 100-2H7zm3 0a1 1 0 100 2h3a1 1 0 100-2h-3z" clipRule="evenodd"/>
                </svg>
              ) : (
                <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 20 20">
                  <path fillRule="evenodd" d="M4 4a2 2 0 012-2h4.586A2 2 0 0112 2.586L15.414 6A2 2 0 0116 7.414V16a2 2 0 01-2 2H6a2 2 0 01-2-2V4z" clipRule="evenodd"/>
                </svg>
              )}
            </div>

            <div className="min-w-0 flex-1">
              <div className="flex items-center gap-2">
                <Badge variant="info" className="flex-shrink-0">[{index}]</Badge>
                <span className="font-medium text-sm truncate text-text-100" title={fileName}>
                  {fileName}
                </span>
              </div>
              {source.metadata?.page && (
                <p className="text-xs text-text-300 mt-0.5">
                  Página {source.metadata.page}
                </p>
              )}
            </div>
          </div>

          {/* Relevance score */}
          {relevancePercent !== null && (
            <div className="flex items-center gap-2 flex-shrink-0">
              <div className="w-16 h-1.5 bg-bg-700 rounded-full overflow-hidden">
                <div
                  className="h-full bg-gradient-to-r from-accent-500 to-violet-500 transition-all"
                  style={{ width: `${relevancePercent}%` }}
                />
              </div>
              <span className="text-xs font-medium text-text-200 w-8">{relevancePercent}%</span>
            </div>
          )}
        </div>

        {/* Expand button */}
        <button
          onClick={() => setExpanded(!expanded)}
          className="text-xs text-accent-400 hover:text-accent-300 font-medium mt-2 flex items-center gap-1 transition-colors group"
        >
          <svg className={`w-3 h-3 transition-transform ${expanded ? 'rotate-180' : ''}`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
          </svg>
          {expanded ? 'Ocultar contenido' : 'Ver contenido'}
        </button>

        {/* Expanded content */}
        {expanded && (
          <div className="mt-3 pt-3 border-t border-bg-700 animate-fade-in">
            <p className="text-sm text-text-200 whitespace-pre-wrap leading-relaxed">
              {source.chunk_content || source.content || 'Sin contenido disponible'}
            </p>
          </div>
        )}
      </div>
    </Card>
  );
}

export default SourceCard;
