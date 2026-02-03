/**
 * Chat/RAG API services
 * Consumes: POST /ask
 */

import { api } from './client';

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
};

export default chatApi;
