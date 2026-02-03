/**
 * Health and stats API services
 * Consumes: GET /health, GET /stats
 */

import { api } from './client';

export const healthApi = {
  /**
   * Get detailed health status
   * @returns {Promise<{status, services, config}>}
   */
  getHealth: () => api.get('/health'),

  /**
   * Get collection statistics
   * @returns {Promise<{collection, stats, model_info}>}
   */
  getStats: () => api.get('/stats'),
};

export default healthApi;
