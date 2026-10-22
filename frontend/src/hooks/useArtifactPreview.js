/**
 * Load generated charts for the Performance Analyzer.
 *
 * A chart is fetched through the authenticated API client and shown from an
 * object URL. The alternative, pointing an `<img>` straight at the artifact
 * endpoint, cannot work: that endpoint is scoped to the organization that owns
 * the job and expects a bearer token, and an image element cannot send an
 * Authorization header. The server therefore refuses the direct request with a
 * 404, which the browser reports as a broken image rather than as an
 * authentication problem.
 *
 * Object URLs are revoked when they are replaced, when the job changes, and
 * when the component unmounts, so a session that opens many charts does not
 * leak them.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { performanceService } from '../services/performanceService';

/**
 * Describe a failed chart load in terms the user can act on.
 *
 * @param {Error|null} error
 * @returns {string}
 */
function describeArtifactError(error) {
  if (!error) return 'The chart could not be loaded.';

  if (error.status === 0) {
    return 'Could not reach the backend. Check that the API is running and try again.';
  }

  if (error.status === 401) {
    return 'Your session has expired. Sign in again to view this chart.';
  }

  if (error.code === 'JOB_NOT_FOUND') {
    return 'This chart is no longer available. Run the analysis again.';
  }

  return error.message || 'The chart could not be loaded.';
}

/**
 * Manage the object URLs that back the chart preview.
 *
 * @param {string|null} jobId The job whose charts are being previewed. A change
 *   invalidates every chart the previous job produced.
 * @returns {{
 *   artifactUrls: Record<string, string>,
 *   artifactErrors: Record<string, string>,
 *   isLoading: boolean,
 *   loadArtifact: (filename: string) => Promise<string|null>,
 *   markArtifactFailed: (filename: string, message: string) => void,
 * }}
 */
export function useArtifactPreview(jobId) {
  // The charts belong to one job. A different job starts from nothing, so the
  // state carries the job it belongs to and the caller reads only the charts
  // of the job it is looking at.
  const [charts, setCharts] = useState({ jobId: null, urls: {}, errors: {} });
  const [isLoading, setIsLoading] = useState(false);

  // The object URLs this hook created, grouped by job, so they can be revoked.
  // A ref, because revoking must not trigger a re-render.
  const objectUrls = useRef({});

  const artifactUrls = useMemo(
    () => (charts.jobId === jobId ? charts.urls : {}),
    [charts, jobId]
  );

  const artifactErrors = useMemo(
    () => (charts.jobId === jobId ? charts.errors : {}),
    [charts, jobId]
  );

  // Release the charts of the job being left behind, whether that is because
  // another job took over or because the component went away.
  useEffect(() => {
    return () => {
      const released = objectUrls.current[jobId];

      if (!released) return;

      Object.values(released).forEach((url) => URL.revokeObjectURL(url));

      delete objectUrls.current[jobId];
    };
  }, [jobId]);

  const loadArtifact = useCallback(
    async (filename) => {
      if (!jobId || !filename) return null;

      setIsLoading(true);

      try {
        const blob = await performanceService.fetchArtifact(jobId, filename);

        const url = URL.createObjectURL(blob);

        const forJob = objectUrls.current[jobId] || {};

        // Replace any URL this chart already held, so the old one is released
        // rather than left to the garbage collector.
        const previous = forJob[filename];

        if (previous) URL.revokeObjectURL(previous);

        forJob[filename] = url;

        objectUrls.current[jobId] = forJob;

        setCharts((current) => {
          const urls = current.jobId === jobId ? current.urls : {};
          const errors = current.jobId === jobId ? current.errors : {};

          return {
            jobId,
            urls: { ...urls, [filename]: url },
            errors: Object.fromEntries(
              Object.entries(errors).filter(([name]) => name !== filename)
            ),
          };
        });

        return url;
      } catch (error) {
        setCharts((current) => {
          const errors = current.jobId === jobId ? current.errors : {};

          return {
            jobId,
            urls: current.jobId === jobId ? current.urls : {},
            errors: { ...errors, [filename]: describeArtifactError(error) },
          };
        });

        return null;
      } finally {
        setIsLoading(false);
      }
    },
    [jobId]
  );

  const markArtifactFailed = useCallback(
    (filename, message) => {
      setCharts((current) => {
        const errors = current.jobId === jobId ? current.errors : {};

        return {
          jobId,
          urls: current.jobId === jobId ? current.urls : {},
          errors: { ...errors, [filename]: message },
        };
      });
    },
    [jobId]
  );

  return {
    artifactUrls,
    artifactErrors,
    isLoading,
    loadArtifact,
    markArtifactFailed,
  };
}

export default useArtifactPreview;
