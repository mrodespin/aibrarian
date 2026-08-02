/**
 * Auth API — login/logout/me
 * La sesión viaja como JWT en el header Authorization (ver client.js),
 * guardado en localStorage (ver tokenStorage.js) tras el login.
 */

import { api } from './client';
import { tokenStorage } from './tokenStorage';

export const authApi = {
  login: async (email, password) => {
    const data = await api.post('/auth/login', { email, password });
    tokenStorage.set(data.access_token);
    return data;
  },
  logout: async () => {
    try {
      await api.post('/auth/logout');
    } finally {
      tokenStorage.clear();
    }
  },
  me: () => api.get('/auth/me'),
};

export default authApi;
