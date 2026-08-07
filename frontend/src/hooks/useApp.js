/**
 * Hook to consume the AppContext (health/stats state + polling).
 *
 * Lives in a separate file from context/AppContext.jsx (which only
 * exports the AppProvider component) because
 * react-refresh/only-export-components requires that a component file
 * not mix component exports with exports of another kind (here, a
 * hook) — otherwise Fast Refresh can't hot-reload that file without
 * losing React's state.
 */
import { useContext } from 'react';
import AppContext from '../context/AppContext';

export function useApp() {
  const context = useContext(AppContext);
  if (!context) {
    throw new Error('useApp must be used within AppProvider');
  }
  return context;
}

export default useApp;
