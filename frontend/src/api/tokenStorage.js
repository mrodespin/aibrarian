/**
 * Session JWT storage (localStorage).
 *
 * The token travels in the Authorization header instead of an httpOnly
 * cookie (see client.js) because in prod, the frontend and API are on
 * different Render subdomains (cross-site) and Safari (ITP) blocks
 * cross-site cookies even with SameSite=None; Secure=True.
 *
 * Trade-off: living in localStorage means the token is readable by JS,
 * so an XSS could steal it (with an httpOnly cookie it couldn't). No
 * additional mitigation here (e.g. rotation, blocklist) — accepted
 * given the project's scope.
 */

const TOKEN_KEY = 'bibliotecario_token';

export const tokenStorage = {
  get: () => localStorage.getItem(TOKEN_KEY),
  set: (token) => localStorage.setItem(TOKEN_KEY, token),
  clear: () => localStorage.removeItem(TOKEN_KEY),
};

export default tokenStorage;
