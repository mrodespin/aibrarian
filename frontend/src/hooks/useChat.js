/**
 * Chat state management hook
 */

import { useState, useCallback } from 'react';
import { chatApi } from '../api';

const SESSION_ID_STORAGE_KEY = 'bibliotecario_session_id';

// Genera o recupera el session_id de la conversación actual. Persistido en
// localStorage para que sobreviva a refrescos de página; se rota cuando el
// usuario pulsa "Limpiar chat" (clearHistory) para no arrastrar contexto de
// una conversación que el usuario ya dio por cerrada.
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

    try {
      const result = await chatApi.ask({ question, sessionId, maxResults: 4 });

      const assistantMessage = {
        id: Date.now() + 1,
        role: 'assistant',
        content: result.answer,
        sources: result.source_documents || [],
        processingTime: result.processing_time,
        timestamp: new Date(),
      };
      setMessages(prev => [...prev, assistantMessage]);
    } catch (err) {
      setError(err.message || 'Error al procesar la pregunta');
      // Add error message to chat
      const errorMessage = {
        id: Date.now() + 1,
        role: 'assistant',
        content: `Error: ${err.message || 'No se pudo obtener respuesta'}`,
        isError: true,
        timestamp: new Date(),
      };
      setMessages(prev => [...prev, errorMessage]);
    } finally {
      setIsLoading(false);
    }
  }, [sessionId]);

  // Rota el session_id además de limpiar los mensajes visibles: si no lo
  // hiciéramos, el backend seguiría teniendo el historial de la
  // conversación "limpiada" y lo resucitaría en la siguiente pregunta.
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
