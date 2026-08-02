/**
 * Document sync API services
 * Consumes: POST /sync, /sync/upload, /sync/directory, /sync/notion, /sync/notion/database
 */

import { api, ApiError } from './client';
import { tokenStorage } from './tokenStorage';

const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

export const syncApi = {
  /**
   * Sync a single PDF file by server path
   * @param {string} filePath - Path to the PDF file on the server
   * @param {string} [collectionName] - Optional collection name
   * @returns {Promise<{document_id, chunks_created, success, message}>}
   */
  syncFile: (filePath, collectionName = null) =>
    api.post('/sync', {
      file_path: filePath,
      collection_name: collectionName,
    }),

  /**
   * Upload and sync a PDF file from the browser
   * @param {File} file - File object from input[type=file]
   * @param {string} [collectionName] - Optional collection name
   * @returns {Promise<{document_id, chunks_created, success, message}>}
   */
  uploadFile: async (file, collectionName = null) => {
    const formData = new FormData();
    formData.append('file', file);
    if (collectionName) {
      formData.append('collection_name', collectionName);
    }

    const token = tokenStorage.get();
    const response = await fetch(`${API_BASE_URL}/sync/upload`, {
      method: 'POST',
      body: formData,
      // Note: Don't set Content-Type header - browser sets it with boundary
      headers: token ? { Authorization: `Bearer ${token}` } : undefined,
    });

    if (!response.ok) {
      const data = await response.json().catch(() => ({}));
      throw new ApiError(
        data.detail || `Upload failed: ${response.status}`,
        response.status,
        data
      );
    }

    return response.json();
  },

  /**
   * Sync all PDFs in a directory
   * @param {string} [directoryPath] - Directory path (defaults to ./data)
   * @returns {Promise<{total, successful, failed, results}>}
   */
  syncDirectory: (directoryPath = null) => {
    const endpoint = directoryPath
      ? `/sync/directory?directory_path=${encodeURIComponent(directoryPath)}`
      : '/sync/directory';
    return api.post(endpoint, {});
  },

  /**
   * Sync a single Notion page
   * @param {string} pageId - Notion page ID or URL
   * @param {string} [collectionName] - Optional collection name
   * @returns {Promise<{document_id, chunks_created, success, message}>}
   */
  syncNotionPage: (pageId, collectionName = null) =>
    api.post('/sync/notion', {
      page_id: pageId,
      collection_name: collectionName,
    }),

  /**
   * Sync all pages from a Notion database
   * @param {string} [databaseId] - Notion database ID (uses env default if null)
   * @param {number} [maxPages] - Limit number of pages
   * @param {string} [collectionName] - Optional collection name
   * @returns {Promise<{total, successful, failed, results}>}
   */
  syncNotionDatabase: (databaseId = null, maxPages = null, collectionName = null) =>
    api.post('/sync/notion/database', {
      database_id: databaseId,
      max_pages: maxPages,
      collection_name: collectionName,
    }),
};

export default syncApi;
