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
   * Doesn't use the shared `api.post()` helper (which always awaits and
   * returns `response.json()`) or native `EventSource` (which doesn't
   * allow sending the Authorization header) — it does its own fetch()
   * and parses the stream by hand, reading the body as text chunk by chunk.
   *
   * @param {Object} params
   * @param {string} params.question - The user's question
   * @param {string} [params.sessionId] - Optional session ID
   * @param {number} [params.maxResults=4] - Max context chunks (1-10)
   * @param {(sources: object[]) => void} [params.onSources] - Called once, with the retrieved sources
   * @param {(text: string) => void} [params.onToken] - Called for each generated text fragment
   * @param {(info: {processing_time: number, session_id: string|null}) => void} [params.onDone] - Called once, when finished
   * @param {(detail: string) => void} [params.onError] - Called if the server sends an error event mid-stream
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

      // Each SSE event ends with a blank line ("\n\n"). More than one
      // can arrive per network chunk, or one can arrive split in half —
      // hence the accumulated buffer and inner loop.
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
