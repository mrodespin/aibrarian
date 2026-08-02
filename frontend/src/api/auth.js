/**
 * Auth API — login/logout/me
 * La sesión viaja en una cookie httpOnly (ver client.js: credentials: 'include'),
 * el frontend nunca ve ni maneja el token directamente.
 */

import { api } from './client';

export const authApi = {
  login: (email, password) => api.post('/auth/login', { email, password }),
  logout: () => api.post('/auth/logout'),
  me: () => api.get('/auth/me'),
};

export default authApi;
