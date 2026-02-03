/**
 * Chat input with send button
 */

import { useState, useRef, useEffect } from 'react';
import { Button, Spinner } from '../common';

export function ChatInput({ onSend, isLoading, disabled }) {
  const [value, setValue] = useState('');
  const textareaRef = useRef(null);

  // Auto-resize textarea
  useEffect(() => {
    const textarea = textareaRef.current;
    if (textarea) {
      textarea.style.height = 'auto';
      textarea.style.height = `${Math.min(textarea.scrollHeight, 150)}px`;
    }
  }, [value]);

  const handleSubmit = (e) => {
    e.preventDefault();
    if (value.trim() && !isLoading && !disabled) {
      onSend(value.trim());
      setValue('');
    }
  };

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSubmit(e);
    }
  };

  return (
    <form onSubmit={handleSubmit} className="border-t border-bg-700 bg-bg-850/80 backdrop-blur-sm p-4">
      <div className="flex gap-3 items-end">
        <textarea
          ref={textareaRef}
          value={value}
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Escribe tu pregunta..."
          disabled={isLoading || disabled}
          rows={1}
          className="
            flex-1 resize-none rounded-lg border border-bg-700 px-4 py-3
            bg-bg-900 text-text-50 placeholder-text-400
            focus:outline-none focus:ring-2 focus:ring-accent-500 focus:border-accent-500
            disabled:bg-bg-950 disabled:cursor-not-allowed disabled:text-text-400
            hover:border-bg-600 transition-all
            max-h-36
          "
        />
        <Button
          type="submit"
          disabled={!value.trim() || isLoading || disabled}
          className="flex-shrink-0"
        >
          {isLoading ? (
            <Spinner size="sm" />
          ) : (
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8" />
            </svg>
          )}
        </Button>
      </div>
      <p className="text-xs text-text-300 mt-2">
        Presiona Enter para enviar, Shift+Enter para nueva línea
      </p>
    </form>
  );
}

export default ChatInput;
