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

    // La burbuja del asistente se crea de forma perezosa, en el primer
    // evento que llega (onSources), no aquí: así evitamos que conviva con
    // el SkeletonMessage de MessageList (que se muestra mientras
    // isLoading=true) — en cuanto llegan las fuentes, apagamos isLoading
    // y la burbuja real (creciendo token a token) toma el relevo.
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
          setError(detail || 'Error al procesar la pregunta');
          updateAssistantMessage((m) => ({
            ...m,
            content: `Error: ${detail || 'No se pudo obtener respuesta'}`,
            isError: true,
          }));
        },
      });
    } catch (err) {
      setError(err.message || 'Error al procesar la pregunta');
      if (placeholderCreated) {
        updateAssistantMessage((m) => ({
          ...m,
          content: `Error: ${err.message || 'No se pudo obtener respuesta'}`,
          isError: true,
        }));
      } else {
        setMessages(prev => [...prev, {
          id: assistantMessageId,
          role: 'assistant',
          content: `Error: ${err.message || 'No se pudo obtener respuesta'}`,
          isError: true,
          timestamp: new Date(),
        }]);
      }
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
