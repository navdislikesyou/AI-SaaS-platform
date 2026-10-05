import { useState, useEffect, useCallback } from 'react';
import { apiClient } from '../services/api';

export function useSystemHealth() {
  const [health, setHealth] = useState(null);
  const [readiness, setReadiness] = useState(null);
  const [isOnline, setIsOnline] = useState(false);
  const [isLoading, setIsLoading] = useState(true);

  const fetchStatus = useCallback(async () => {
    try {
      const [healthRes, readyRes] = await Promise.all([
        apiClient.getHealth(),
        apiClient.getReadiness().catch(() => null),
      ]);

      if (healthRes && healthRes.status === 'ok') {
        setHealth(healthRes);
        setReadiness(readyRes);
        setIsOnline(true);
      } else {
        setIsOnline(false);
      }
    } catch {
      setIsOnline(false);
      setHealth(null);
      setReadiness(null);
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchStatus();
    const interval = setInterval(fetchStatus, 15000);
    return () => clearInterval(interval);
  }, [fetchStatus]);

  return {
    isOnline,
    isLoading,
    health,
    readiness,
    refresh: fetchStatus,
  };
}
