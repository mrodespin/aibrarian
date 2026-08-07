/**
 * Chat state management hook
 */

import { useState, useCallback } from 'react';
import { chatApi } from '../api';

const SESSION_ID_STORAGE_KEY = 'bibliotecario_session_id';

// Generates or retrieves the current conversation's session_id.
// Persisted in localStorage so it survives page refreshes; rotated
// when the user hits "Clear chat" (clearHistory) so we don't drag
// along context from a conversation the user already considered closed.
function getOrCreateSessionId() {
  let sessionId = localStorage.getItem(SESSION_ID_STORAGE_KEY);
  if (!sessionId) {
    sessionId = crypto.randomUUID();
    localStorage.setItem(SESSION_ID_STORAGE_KEY, sessionId);
  }
  return sessionId;
}

export function useChat() {
  const [messages, setMessages] = useState([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState(null);
  const [sessionId, setSessionId] = useState(getOrCreateSessionId);

  const sendMessage = useCallback(async (question) => {
    if (!question.trim()) return;

    setIsLoading(true);
    setError(null);

    // Add user message immediately
    const userMessage = {
      id: Date.now(),
      role: 'user',
      content: question,
      timestamp: new Date(),
    };
    setMessages(prev => [...prev, userMessage]);

    // The assistant's bubble is created lazily, on the first event that
    // arrives (onSources), not here: this avoids it coexisting with
    // MessageList's SkeletonMessage (shown while isLoading=true) — as
    // soon as the sources arrive, we turn off isLoading and the real
    // bubble (growing token by token) takes over.
    const assistantMessageId = Date.now() + 1;
    let placeholderCreated = false;

    const ensurePlaceholder = (extra = {}) => {
      if (placeholderCreated) return;
      placeholderCreated = true;
      setMessages(prev => [...prev, {
        id: assistantMessageId,
        role: 'assistant',
        content: '',
        sources: [],
        timestamp: new Date(),
        ...extra,
      }]);
    };

    const updateAssistantMessage = (updater) => {
      setMessages(prev => prev.map(m => (m.id === assistantMessageId ? updater(m) : m)));
    };

    try {
      await chatApi.askStream({
        question,
        sessionId,
        maxResults: 4,
        onSources: (sources) => {
          ensurePlaceholder({ sources: sources || [] });
          setIsLoading(false);
        },
        onToken: (text) => {
          ensurePlaceholder();
          updateAssistantMessage((m) => ({ ...m, content: m.content + text }));
        },
        onDone: (info) => {
          updateAssistantMessage((m) => ({ ...m, processingTime: info.processing_time }));
        },
        onError: (detail) => {
          ensurePlaceholder();
          setError(detail || 'Failed to process the question');
          updateAssistantMessage((m) => ({
            ...m,
            content: `Error: ${detail || 'Could not get a response'}`,
            isError: true,
          }));
        },
      });
    } catch (err) {
      setError(err.message || 'Failed to process the question');
      if (placeholderCreated) {
        updateAssistantMessage((m) => ({
          ...m,
          content: `Error: ${err.message || 'Could not get a response'}`,
          isError: true,
        }));
      } else {
        setMessages(prev => [...prev, {
          id: assistantMessageId,
          role: 'assistant',
          content: `Error: ${err.message || 'Could not get a response'}`,
          isError: true,
          timestamp: new Date(),
        }]);
      }
    } finally {
      setIsLoading(false);
    }
  }, [sessionId]);

  // Rotates the session_id in addition to clearing the visible
  // messages: if we didn't, the backend would still have the "cleared"
  // conversation's history and would resurrect it on the next question.
  const clearHistory = useCallback(() => {
    setMessages([]);
    setError(null);
    const newSessionId = crypto.randomUUID();
    localStorage.setItem(SESSION_ID_STORAGE_KEY, newSessionId);
    setSessionId(newSessionId);
  }, []);

  return {
    messages,
    isLoading,
    error,
    sendMessage,
    clearHistory,
  };
}

export default useChat;
