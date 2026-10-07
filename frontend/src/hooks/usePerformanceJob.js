import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { performanceService, TERMINAL_JOB_STATUSES } from '../services/performanceService';

const POLL_INTERVAL_MS = 1000;

/** Empty execution slice, shared so callers get a stable identity. */
const EMPTY_EXECUTION = Object.freeze({
  job: null,
  jobId: null,
  status: null,
  result: null,
  error: null,
  isSubmitting: false,
  isPolling: false,
  isLoading: false,
});

/**
 * Submit Performance jobs and poll them to a terminal state.
 *
 * State is tracked **per operation**, keyed by the operation name that created
 * the job. Five operations are selectable and each keeps its own job id, status,
 * result, and error, so switching between them never shows one operation's
 * result under another. Polling continues for operations that are not currently
 * on screen: switching tabs does not cancel anything, and a job submitted
 * earlier keeps running and keeps updating its own entry.
 *
 * Starting a new job for an operation replaces only that operation's state.
 * The others are left untouched.
 *
 * Job submission is deliberately NOT gated on the agent catalog's `available`
 * flag: PERFORMANCE_AGENT_ENABLED only controls the catalog entry, while the
 * job API runs independently of it.
 *
 * No client-side timeout is applied, matching the backend, which currently
 * enforces no time limit on a Performance job.
 */
/**
 * Return one operation's execution, with `status` and `result` derived.
 *
 * `job` stays the complete job object. `result` is the job's own inner
 * `result` payload -- what an operation actually computed, e.g.
 * `{generated, visualizations}` for a visualize job. Callers render from
 * `result`; they must not reach into `job.result` themselves, or the whole
 * job envelope leaks into a result renderer.
 */
function withDerivedFields(slice) {
  return {
    ...slice,
    status: slice.job?.status || null,
    result: slice.job?.result || null,
  };
}

export function usePerformanceJob() {
  const [executions, setExecutions] = useState({});

  // Timers keyed by operation so each poll loop is independent. A ref, because
  // rescheduling must not trigger a re-render.
  const timersRef = useRef({});
  const mountedRef = useRef(true);
  // Held in a ref so the poll function can reschedule itself without
  // referencing its own initialization.
  const pollRef = useRef(null);

  useEffect(() => {
    mountedRef.current = true;

    return () => {
      mountedRef.current = false;
      Object.keys(timersRef.current).forEach((operation) => {
        clearTimeout(timersRef.current[operation]);
      });
      timersRef.current = {};
    };
  }, []);

  /** Merge a delta into one operation's slice, leaving others alone. */
  const patch = useCallback((operation, delta) => {
    setExecutions((previous) => ({
      ...previous,
      [operation]: { ...EMPTY_EXECUTION, ...previous[operation], ...delta },
    }));
  }, []);

  /** Cancel one operation's poll loop. Scoped by operation on purpose. */
  const clearTimer = useCallback((operation) => {
    if (timersRef.current[operation]) {
      clearTimeout(timersRef.current[operation]);
      delete timersRef.current[operation];
    }
  }, []);

  const poll = useCallback(
    async (operation, id) => {
      if (!mountedRef.current) return;

      try {
        const next = await performanceService.getJob(id);

        if (!mountedRef.current) return;

        patch(operation, { job: next, jobId: id });

        if (TERMINAL_JOB_STATUSES.includes(next?.status)) {
          clearTimer(operation);

          if (next.status === 'failed') {
            patch(operation, {
              isPolling: false,
              error: {
                message: next.error || 'The job failed.',
                code: 'JOB_FAILED',
                status: 500,
              },
            });
          }
          return;
        }

        timersRef.current[operation] = setTimeout(
          () => pollRef.current?.(operation, id),
          POLL_INTERVAL_MS,
        );
      } catch (err) {
        if (!mountedRef.current) return;
        clearTimer(operation);
        patch(operation, { isPolling: false, error: err });
      }
    },
    [clearTimer, patch],
  );

  useEffect(() => {
    pollRef.current = poll;
  }, [poll]);

  const submit = useCallback(
    async (operation, filePath) => {
      // Only this operation's loop is cancelled. Any other operation keeps
      // running in the background.
      clearTimer(operation);

      patch(operation, {
        job: null,
        jobId: null,
        error: null,
        isSubmitting: true,
        isPolling: false,
      });

      try {
        const created = await performanceService.createJob(operation, filePath);

        if (!mountedRef.current) return null;

        patch(operation, {
          jobId: created.job_id,
          job: created,
          isSubmitting: false,
        });

        if (TERMINAL_JOB_STATUSES.includes(created?.status)) {
          if (created.status === 'failed') {
            patch(operation, {
              error: {
                message: created.error || 'The job failed.',
                code: 'JOB_FAILED',
                status: 500,
              },
            });
          }
          return created;
        }

        patch(operation, { isPolling: true });
        timersRef.current[operation] = setTimeout(
          () => pollRef.current?.(operation, created.job_id),
          POLL_INTERVAL_MS,
        );

        return created;
      } catch (err) {
        if (mountedRef.current) {
          patch(operation, { isSubmitting: false, error: err });
        }
        return null;
      }
    },
    [clearTimer, patch],
  );

  /** Drop one operation's state entirely. */
  const resetOperation = useCallback(
    (operation) => {
      clearTimer(operation);
      patch(operation, EMPTY_EXECUTION);
    },
    [clearTimer, patch],
  );

  const getExecution = useCallback(
    (operation) => withDerivedFields(executions[operation] || EMPTY_EXECUTION),
    [executions],
  );

  const isAnyRunning = useMemo(
    () =>
      Object.values(executions).some((entry) => entry.isSubmitting || entry.isPolling),
    [executions],
  );

  return {
    submit,
    resetOperation,
    getExecution,
    executions,
    isAnyRunning,
  };
}

export default usePerformanceJob;
