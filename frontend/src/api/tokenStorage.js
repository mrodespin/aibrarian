/**
 * Almacenamiento del JWT de sesión (localStorage).
 *
 * El token viaja en el header Authorization en vez de en una cookie
 * httpOnly (ver client.js) porque en prod, frontend y API están en
 * subdominios distintos de Render (cross-site) y Safari (ITP) bloquea
 * las cookies cross-site incluso con SameSite=None; Secure=True.
 *
 * Trade-off: al vivir en localStorage, el token es legible por JS, así
 * que un XSS podría robarlo (con la cookie httpOnly no podía). No hay
 * mitigación adicional aquí (p.ej. rotación, blocklist) — asumido por
 * el alcance del proyecto.
 */

const TOKEN_KEY = 'bibliotecario_token';

export const tokenStorage = {
  get: () => localStorage.getItem(TOKEN_KEY),
  set: (token) => localStorage.setItem(TOKEN_KEY, token),
  clear: () => localStorage.removeItem(TOKEN_KEY),
};

export default tokenStorage;
