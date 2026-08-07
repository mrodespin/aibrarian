/**
 * Hook para consumir el AuthContext (sesión/usuario actual).
 *
 * Vive en un archivo aparte de context/AuthContext.jsx (que solo exporta el
 * componente AuthProvider) por la misma razón que hooks/useApp.js: mezclar
 * un export de componente con un export de hook en el mismo archivo rompe
 * react-refresh/only-export-components y con ello el Fast Refresh.
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
