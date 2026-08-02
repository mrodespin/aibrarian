/**
 * Base API client with error handling
 */

import { tokenStorage } from './tokenStorage';

const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

/**
 * Custom error class for API errors
 */
export class ApiError extends Error {
  constructor(message, status, data) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.data = data;
  }
}

/**
 * Base request function with error handling
 */
async function request(endpoint, options = {}) {
  const url = `${API_BASE_URL}${endpoint}`;
  const token = tokenStorage.get();

  const config = {
    headers: {
      'Content-Type': 'application/json',
      // Adjunta el JWT de sesión a mano (en vez de cookie) — ver
      // tokenStorage.js para el porqué (Safari ITP + cross-site).
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...options.headers,
    },
    ...options,
  };

  if (options.body && typeof options.body === 'object') {
    config.body = JSON.stringify(options.body);
  }

  try {
    const response = await fetch(url, config);

    if (!response.ok) {
      const data = await response.json().catch(() => ({}));
      throw new ApiError(
        data.detail || `HTTP error ${response.status}`,
        response.status,
        data
      );
    }

    return response.json();
  } catch (err) {
    if (err instanceof ApiError) throw err;
    throw new ApiError(
      err.message || 'Network error',
      0,
      { originalError: err.message }
    );
  }
}

/**
 * API client with HTTP method helpers
 */
export const api = {
  get: (endpoint) => request(endpoint, { method: 'GET' }),
  post: (endpoint, body) => request(endpoint, { method: 'POST', body }),
  delete: (endpoint) => request(endpoint, { method: 'DELETE' }),
};

export default api;
