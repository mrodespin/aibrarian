/**
 * Global application context
 * Manages health status and stats with polling
 */

import { createContext, useState, useEffect, useCallback } from 'react';
import { healthApi } from '../api';

const AppContext = createContext(null);

const POLL_INTERVAL = 30000; // 30 seconds

export function AppProvider({ children }) {
  const [health, setHealth] = useState({
    status: 'unknown',
    api: false,
    llm: false,
    vectorDb: false,
    llmProvider: null,
    vectorDbProvider: null,
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
        llm: data.services?.ollama ?? false,
        vectorDb: data.services?.chromadb ?? false,
        llmProvider: data.config?.llm_provider ?? null,
        vectorDbProvider: data.config?.vector_db_provider ?? null,
        lastChecked: new Date(),
      });
    } catch {
      // La API no responde
      setHealth(prev => ({
        ...prev,
        status: 'error',
        api: false,
        llm: false,
        vectorDb: false,
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

export default AppContext;
