/**
 * Document management API services
 * Consumes: DELETE /documents/{id}
 */

import { api } from './client';

export const documentsApi = {
  /**
   * Delete a document and all its chunks
   * @param {string} documentId - The document ID to delete
   * @returns {Promise<{status, message}>}
   */
  delete: (documentId) =>
    api.delete(`/documents/${encodeURIComponent(documentId)}`),
};

export default documentsApi;
