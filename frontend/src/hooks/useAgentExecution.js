import { useState, useCallback } from 'react';
import { agentService } from '../services/agentService';

export function useAgentExecution() {
  const [isLoading, setIsLoading] = useState(false);
  const [response, setResponse] = useState(null);
  const [error, setError] = useState(null);
  const [executionMeta, setExecutionMeta] = useState(null);

  const execute = useCallback(async (agent, operation, payload = {}) => {
    setIsLoading(true);
    setError(null);
    setResponse(null);
    const startTime = performance.now();

    try {
      const res = await agentService.executeAgent(agent, operation, payload);
      const duration = Math.round(performance.now() - startTime);

      setResponse(res);
      setExecutionMeta({
        agent,
        operation,
        durationMs: res?.data?.duration_ms || duration,
        requestId: res?.request_id,
        status: 'success',
      });
      return { success: true, data: res?.data };
    } catch (err) {
      const duration = Math.round(performance.now() - startTime);
      const isUnavailable = err.status === 503 || err.code === 'AGENT_UNAVAILABLE';

      setError(err);
      setExecutionMeta({
        agent,
        operation,
        durationMs: duration,
        requestId: err.requestId,
        isUnavailable,
        errorCode: err.code,
        details: err.details,
        status: 'error',
      });

      return {
        success: false,
        error: err,
        isUnavailable,
        details: err.details,
      };
    } finally {
      setIsLoading(false);
    }
  }, []);

  const reset = useCallback(() => {
    setIsLoading(false);
    setResponse(null);
    setError(null);
    setExecutionMeta(null);
  }, []);

  return {
    execute,
    reset,
    isLoading,
    response,
    error,
    executionMeta,
    isUnavailable: executionMeta?.isUnavailable || false,
  };
}
