/**
 * Auth API — login/logout/me
 * The session travels as a JWT in the Authorization header (see
 * client.js), stored in localStorage (see tokenStorage.js) after login.
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
