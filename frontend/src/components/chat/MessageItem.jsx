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
    <div className={`flex ${isUser ? 'justify-end' : 'justify-start'} mb-4`}>
      <div
        className={`
          max-w-[85%] md:max-w-[75%] rounded-2xl px-4 py-3
          ${isUser
            ? 'bg-blue-600 text-white'
            : message.isError
              ? 'bg-red-50 text-red-900 border border-red-200'
              : 'bg-white text-gray-900 border border-gray-200 shadow-sm'
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
              <div className="mt-3 pt-2 border-t border-gray-100">
                <Badge variant="default">
                  {message.processingTime.toFixed(2)}s
                </Badge>
              </div>
            )}

            {/* Sources */}
            {hasSources && (
              <div className="mt-3 pt-3 border-t border-gray-100">
                <button
                  onClick={() => setShowSources(!showSources)}
                  className="text-sm text-blue-600 hover:underline flex items-center gap-1"
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
