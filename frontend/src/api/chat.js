/**
 * Chat/RAG API services
 * Consumes: POST /ask, POST /ask/stream
 */

import { api, ApiError, API_BASE_URL } from './client';
import { tokenStorage } from './tokenStorage';

export const chatApi = {
  /**
   * Send a question to the RAG system
   * @param {Object} params
   * @param {string} params.question - The user's question
   * @param {string} [params.sessionId] - Optional session ID
   * @param {number} [params.maxResults=4] - Max context chunks (1-10)
   * @returns {Promise<{question, answer, source_documents, processing_time}>}
   */
  ask: ({ question, sessionId, maxResults = 4 }) =>
    api.post('/ask', {
      question,
      session_id: sessionId,
      max_results: maxResults,
    }),

  /**
   * Send a question to the RAG system with streaming (Server-Sent Events).
   *
   * No usa el helper compartido `api.post()` (que siempre espera y
   * devuelve `response.json()`) ni `EventSource` nativo (que no permite
   * mandar el header Authorization) — hace su propio fetch() y parsea el
   * stream a mano, leyendo el body como texto trozo a trozo.
   *
   * @param {Object} params
   * @param {string} params.question - The user's question
   * @param {string} [params.sessionId] - Optional session ID
   * @param {number} [params.maxResults=4] - Max context chunks (1-10)
   * @param {(sources: object[]) => void} [params.onSources] - Llamado una vez, con las fuentes recuperadas
   * @param {(text: string) => void} [params.onToken] - Llamado por cada fragmento de texto generado
   * @param {(info: {processing_time: number, session_id: string|null}) => void} [params.onDone] - Llamado una vez, al terminar
   * @param {(detail: string) => void} [params.onError] - Llamado si el servidor manda un evento de error a mitad de stream
   * @returns {Promise<void>}
   */
  askStream: async ({ question, sessionId, maxResults = 4, onSources, onToken, onDone, onError }) => {
    const token = tokenStorage.get();

    let response;
    try {
      response = await fetch(`${API_BASE_URL}/ask/stream`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify({
          question,
          session_id: sessionId,
          max_results: maxResults,
        }),
      });
    } catch (err) {
      throw new ApiError(err.message || 'Network error', 0, { originalError: err.message });
    }

    if (!response.ok) {
      const data = await response.json().catch(() => ({}));
      throw new ApiError(data.detail || `HTTP error ${response.status}`, response.status, data);
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });

      // Cada evento SSE termina en línea en blanco ("\n\n"). Puede llegar
      // más de uno por chunk de red, o uno partido a medias — de ahí el
      // buffer acumulado y el bucle interno.
      let separatorIndex;
      while ((separatorIndex = buffer.indexOf('\n\n')) !== -1) {
        const rawEvent = buffer.slice(0, separatorIndex);
        buffer = buffer.slice(separatorIndex + 2);

        const eventTypeMatch = rawEvent.match(/^event: (.+)$/m);
        const dataMatch = rawEvent.match(/^data: (.+)$/m);
        if (!eventTypeMatch || !dataMatch) continue;

        const eventType = eventTypeMatch[1];
        const data = JSON.parse(dataMatch[1]);

        if (eventType === 'sources') onSources?.(data.source_documents);
        else if (eventType === 'token') onToken?.(data.text);
        else if (eventType === 'done') onDone?.(data);
        else if (eventType === 'error') onError?.(data.detail);
      }
    }
  },
};

export default chatApi;
