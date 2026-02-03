/**
 * Single chat message (user or assistant)
 */

import { useState } from 'react';
import { Badge } from '../common';
import { SourceCard } from './SourceCard';
import { MarkdownContent } from '../../utils/markdown.jsx';

export function MessageItem({ message }) {
  const [showSources, setShowSources] = useState(false);
  const isUser = message.role === 'user';
  const hasSources = message.sources?.length > 0;

  return (
    <div className={`flex ${isUser ? 'justify-end' : 'justify-start'} mb-6 animate-fade-in`}>
      <div
        className={`
          max-w-[85%] md:max-w-[70%] rounded-2xl px-5 py-4
          ${isUser
            ? 'bg-gradient-to-br from-accent-500 to-violet-600 text-white shadow-lg shadow-accent-500/30'
            : message.isError
              ? 'bg-error-500/10 text-error-400 border border-error-500/30 rounded-2xl'
              : 'bg-bg-850 border border-bg-700 shadow-sm text-text-50'
          }
        `}
      >
        {isUser ? (
          <p className="whitespace-pre-wrap">{message.content}</p>
        ) : (
          <>
            <MarkdownContent content={message.content} />

            {/* Processing time */}
            {message.processingTime && (
              <div className="mt-3 pt-2 border-t border-bg-700">
                <Badge variant="default">
                  {message.processingTime.toFixed(2)}s
                </Badge>
              </div>
            )}

            {/* Sources */}
            {hasSources && (
              <div className="mt-3 pt-3 border-t border-bg-700">
                <button
                  onClick={() => setShowSources(!showSources)}
                  className="text-sm text-accent-400 hover:text-accent-300 flex items-center gap-1 transition-colors"
                >
                  <svg className={`w-4 h-4 transition-transform ${showSources ? 'rotate-90' : ''}`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
                  </svg>
                  {showSources ? 'Ocultar' : 'Ver'} {message.sources.length} fuente{message.sources.length > 1 ? 's' : ''}
                </button>

                {showSources && (
                  <div className="mt-3 space-y-2">
                    {message.sources.map((source, idx) => (
                      <SourceCard key={idx} source={source} index={idx + 1} />
                    ))}
                  </div>
                )}
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}

export default MessageItem;
