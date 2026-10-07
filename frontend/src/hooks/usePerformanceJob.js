import { useCallback, useEffect, useRef, useState } from 'react';
import { performanceService, TERMINAL_JOB_STATUSES } from '../services/performanceService';

const POLL_INTERVAL_MS = 1000;

/**
 * Submit a Performance job and poll until it reaches a terminal state.
 *
 * Performance analysis runs on the backend as a background job, so the result
 * is not available when the request returns. This hook owns the poll loop and
 * stops once the job reports `completed` or `failed`.
 *
 * Job submission is deliberately NOT gated on the agent catalog's `available`
 * flag: PERFORMANCE_AGENT_ENABLED only controls the catalog entry, while the
 * job API runs independently of it.
 *
 * No client-side timeout is applied, matching the backend, which currently
 * enforces no time limit on a Performance job.
 */
export function usePerformanceJob() {
  const [job, setJob] = useState(null);
  const [jobId, setJobId] = useState(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isPolling, setIsPolling] = useState(false);
  const [error, setError] = useState(null);

  const timerRef = useRef(null);
  const mountedRef = useRef(true);
  // Held in a ref so the poll function can reschedule itself without
  // referencing its own initialization.
  const pollRef = useRef(null);

  useEffect(() => {
    mountedRef.current = true;

    return () => {
      mountedRef.current = false;
      if (timerRef.current) {
        clearTimeout(timerRef.current);
        timerRef.current = null;
      }
    };
  }, []);

  const poll = useCallback(async (id) => {
    if (!mountedRef.current) return;

    try {
      const next = await performanceService.getJob(id);

      if (!mountedRef.current) return;

      setJob(next);

      if (TERMINAL_JOB_STATUSES.includes(next?.status)) {
        if (timerRef.current) {
          clearTimeout(timerRef.current);
          timerRef.current = null;
        }
        setIsPolling(false);

        if (next.status === 'failed') {
          setError({
            message: next.error || 'The job failed.',
            code: 'JOB_FAILED',
            status: 500,
          });
        }
        return;
      }

      timerRef.current = setTimeout(() => pollRef.current?.(id), POLL_INTERVAL_MS);
    } catch (err) {
      if (!mountedRef.current) return;
      if (timerRef.current) {
        clearTimeout(timerRef.current);
        timerRef.current = null;
      }
      setIsPolling(false);
      setError(err);
    }
  }, []);

  useEffect(() => {
    pollRef.current = poll;
  }, [poll]);

  const submit = useCallback(
    async (operation, filePath) => {
      if (timerRef.current) {
        clearTimeout(timerRef.current);
        timerRef.current = null;
      }
      setIsPolling(false);
      setError(null);
      setJob(null);
      setJobId(null);
      setIsSubmitting(true);

      try {
        const created = await performanceService.createJob(operation, filePath);

        if (!mountedRef.current) return null;

        setJobId(created.job_id);
        setJob(created);
        setIsSubmitting(false);

        if (TERMINAL_JOB_STATUSES.includes(created?.status)) {
          if (created.status === 'failed') {
            setError({
              message: created.error || 'The job failed.',
              code: 'JOB_FAILED',
              status: 500,
            });
          }
          return created;
        }

        setIsPolling(true);
        timerRef.current = setTimeout(() => pollRef.current?.(created.job_id), POLL_INTERVAL_MS);

        return created;
      } catch (err) {
        if (mountedRef.current) {
          setError(err);
        }
        setIsSubmitting(false);
        return null;
      }
    },
    [],
  );

  const reset = useCallback(() => {
    if (timerRef.current) {
      clearTimeout(timerRef.current);
      timerRef.current = null;
    }
    setJob(null);
    setJobId(null);
    setIsSubmitting(false);
    setIsPolling(false);
    setError(null);
  }, []);

  return {
    submit,
    reset,
    job,
    jobId,
    status: job?.status || null,
    result: job?.result || null,
    error,
    isSubmitting,
    isPolling,
    isLoading: isSubmitting || isPolling,
  };
}

export default usePerformanceJob;
