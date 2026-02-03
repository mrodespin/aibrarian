/**
 * Document sync API services
 * Consumes: POST /sync, /sync/directory, /sync/notion, /sync/notion/database
 */

import { api } from './client';

export const syncApi = {
  /**
   * Sync a single PDF file
   * @param {string} filePath - Path to the PDF file
   * @param {string} [collectionName] - Optional collection name
   * @returns {Promise<{document_id, chunks_created, success, message}>}
   */
  syncFile: (filePath, collectionName = null) =>
    api.post('/sync', {
      file_path: filePath,
      collection_name: collectionName,
    }),

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
