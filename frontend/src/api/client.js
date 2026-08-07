/**
 * Base API client with error handling
 */

import { tokenStorage } from './tokenStorage';

// Exported so chat.js (askStream) can build the /ask/stream URL without
// duplicating the VITE_API_URL logic — it needs its own fetch() instead
// of going through request() because the latter always calls response.json().
export const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

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
      // Attach the session JWT by hand (instead of a cookie) — see
      // tokenStorage.js for why (Safari ITP + cross-site).
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
