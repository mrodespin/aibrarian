/**
 * Hook to consume the AuthContext (session/current user).
 *
 * Lives in a separate file from context/AuthContext.jsx (which only
 * exports the AuthProvider component) for the same reason as
 * hooks/useApp.js: mixing a component export with a hook export in the
 * same file breaks react-refresh/only-export-components, and with it
 * Fast Refresh.
 */
import { useContext } from 'react';
import AuthContext from '../context/AuthContext';

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within AuthProvider');
  }
  return context;
}

export default useAuth;
