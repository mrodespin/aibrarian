/**
 * Global application context
 * Manages health status and stats with polling
 */

import { createContext, useContext, useState, useEffect, useCallback } from 'react';
import { healthApi } from '../api';

const AppContext = createContext(null);

const POLL_INTERVAL = 30000; // 30 seconds

export function AppProvider({ children }) {
  const [health, setHealth] = useState({
    status: 'unknown',
    api: false,
    ollama: false,
    chromadb: false,
    lastChecked: null,
  });

  const [stats, setStats] = useState({
    documentCount: 0,
    collectionName: '',
    modelInfo: null,
  });

  const [isLoading, setIsLoading] = useState(true);
  const [isRefreshing, setIsRefreshing] = useState(false);

  const checkHealth = useCallback(async () => {
    try {
      const data = await healthApi.getHealth();
      setHealth({
        status: data.status || 'healthy',
        api: true, // Si llegamos aquí, la API responde
        ollama: data.services?.ollama ?? false,
        chromadb: data.services?.chromadb ?? false,
        lastChecked: new Date(),
      });
    } catch (err) {
      // La API no responde
      setHealth(prev => ({
        ...prev,
        status: 'error',
        api: false,
        ollama: false,
        chromadb: false,
        lastChecked: new Date(),
      }));
    }
  }, []);

  const fetchStats = useCallback(async () => {
    try {
      const data = await healthApi.getStats();
      setStats({
        documentCount: data.stats?.count ?? data.stats?.document_count ?? 0,
        collectionName: data.stats?.collection_name ?? data.collection ?? '',
        modelInfo: data.model_info ?? null,
      });
    } catch (err) {
      // Stats fetch failed, keep previous values
      console.warn('Failed to fetch stats:', err.message);
    }
  }, []);

  const refreshAll = useCallback(async () => {
    setIsRefreshing(true);
    await Promise.all([checkHealth(), fetchStats()]);
    setIsRefreshing(false);
  }, [checkHealth, fetchStats]);

  // Initial fetch and polling
  useEffect(() => {
    // Carga inicial
    const initialLoad = async () => {
      setIsLoading(true);
      await Promise.all([checkHealth(), fetchStats()]);
      setIsLoading(false);
    };
    
    initialLoad();
    
    // Polling silencioso (sin cambiar isLoading)
    const interval = setInterval(() => {
      checkHealth();
      fetchStats();
    }, POLL_INTERVAL);
    return () => clearInterval(interval);
  }, [checkHealth, fetchStats]);

  const value = {
    health,
    stats,
    isLoading,
    isRefreshing,
    refreshAll,
    refreshStats: fetchStats,
  };

  return (
    <AppContext.Provider value={value}>
      {children}
    </AppContext.Provider>
  );
}

export function useApp() {
  const context = useContext(AppContext);
  if (!context) {
    throw new Error('useApp must be used within AppProvider');
  }
  return context;
}

export default AppContext;
