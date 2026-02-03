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

  const checkHealth = useCallback(async () => {
    try {
      const data = await healthApi.getHealth();
      setHealth({
        status: data.status || 'healthy',
        ollama: data.services?.ollama ?? false,
        chromadb: data.services?.chromadb ?? false,
        lastChecked: new Date(),
      });
    } catch (err) {
      setHealth(prev => ({
        ...prev,
        status: 'error',
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
    setIsLoading(true);
    await Promise.all([checkHealth(), fetchStats()]);
    setIsLoading(false);
  }, [checkHealth, fetchStats]);

  // Initial fetch and polling
  useEffect(() => {
    refreshAll();
    const interval = setInterval(() => {
      checkHealth();
      fetchStats();
    }, POLL_INTERVAL);
    return () => clearInterval(interval);
  }, [refreshAll, checkHealth, fetchStats]);

  const value = {
    health,
    stats,
    isLoading,
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
