/**
 * Hook para consumir el AppContext (estado de salud/stats + polling).
 *
 * Vive en un archivo aparte de context/AppContext.jsx (que solo exporta el
 * componente AppProvider) porque react-refresh/only-export-components exige
 * que un archivo de componente no mezcle exports de componentes con exports
 * de otro tipo (aquí, un hook) — si no, Fast Refresh no puede recargar en
 * caliente ese archivo sin perder el estado de React.
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
