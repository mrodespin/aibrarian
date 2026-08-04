/**
 * Document management API services
 * Consumes: GET /documents, DELETE /documents/{id}
 */

import { api } from './client';

export const documentsApi = {
  /**
   * List all documents indexed in the knowledge base (no semantic search,
   * just the metadata catalog — see RAGService.list_known_documents)
   * @returns {Promise<{total: number, documents: Array<{document_id, title, source, chunk_count}>}>}
   */
  list: () => api.get('/documents'),

  /**
   * Delete a document and all its chunks
   * @param {string} documentId - The document ID to delete
   * @returns {Promise<{status, message}>}
   */
  delete: (documentId) =>
    api.delete(`/documents/${encodeURIComponent(documentId)}`),
};

export default documentsApi;
