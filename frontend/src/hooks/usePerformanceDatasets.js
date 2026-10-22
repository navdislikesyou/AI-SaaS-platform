/**
 * Load the datasets the Performance Analyzer can analyse.
 *
 * The backend list is the source of truth for the dataset selector. It reports
 * the packaged sample first and this instance's uploads after it, together with
 * the server's own size limit and accepted formats, so the UI states the real
 * constraints rather than a hardcoded copy that could drift from configuration.
 *
 * Entries that are not `ready` are kept out of `datasets`, so an unusable dataset
 * is never offered as a choice.
 */

import { useCallback, useEffect, useState } from 'react';
import { performanceService } from '../services/performanceService';

/**
 * Return the selectable datasets plus the server's upload constraints.
 *
 * @returns {{
 *   datasets: Array<object>,
 *   failedDatasets: Array<object>,
 *   maxUploadBytes: number,
 *   supportedExtensions: string[],
 *   isLoading: boolean,
 *   error: Error|null,
 *   refresh: () => Promise<void>,
 *   addDataset: (dataset: object) => void,
 * }}
 */
export function usePerformanceDatasets() {
  const [datasets, setDatasets] = useState([]);
  const [failedDatasets, setFailedDatasets] = useState([]);
  const [maxUploadBytes, setMaxUploadBytes] = useState(0);
  const [supportedExtensions, setSupportedExtensions] = useState([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState(null);

  /**
   * Split a backend listing into usable and unusable datasets.
   *
   * @param {Array<object>} all
   */
  const applyListing = useCallback((all) => {
    const rows = Array.isArray(all) ? all : [];

    setDatasets(rows.filter((row) => row?.status === 'ready' && row?.available !== false));
    setFailedDatasets(rows.filter((row) => row?.status && row.status !== 'ready'));
  }, []);

  /**
   * Reload the dataset list from the backend.
   */
  const refresh = useCallback(async () => {
    setIsLoading(true);

    try {
      const listing = await performanceService.listDatasets();

      applyListing(listing?.datasets);
      setMaxUploadBytes(listing?.max_upload_bytes || 0);
      setSupportedExtensions(
        Array.isArray(listing?.supported_extensions) ? listing.supported_extensions : []
      );
      setError(null);
    } catch (err) {
      setError(err);
    } finally {
      setIsLoading(false);
    }
  }, [applyListing]);

  useEffect(() => {
    let mounted = true;

    performanceService
      .listDatasets()
      .then((listing) => {
        if (!mounted) return;

        applyListing(listing?.datasets);
        setMaxUploadBytes(listing?.max_upload_bytes || 0);
        setSupportedExtensions(
          Array.isArray(listing?.supported_extensions) ? listing.supported_extensions : []
        );
      })
      .catch((err) => {
        if (mounted) setError(err);
      })
      .finally(() => {
        if (mounted) setIsLoading(false);
      });

    return () => {
      mounted = false;
    };
  }, [applyListing]);

  /**
   * Insert a newly uploaded dataset at the head of the uploads.
   *
   * Used after an upload so the selector updates without a second round trip.
   * The backend remains authoritative; this only avoids a redundant refetch. The
   * packaged sample stays first regardless, because it is not an upload.
   *
   * @param {object} dataset
   */
  const addDataset = useCallback((dataset) => {
    if (!dataset?.dataset_id) return;

    setDatasets((current) => {
      const kept = current.filter((row) => row.dataset_id !== dataset.dataset_id);
      const samples = kept.filter((row) => row.is_sample);
      const uploads = kept.filter((row) => !row.is_sample);

      return [...samples, dataset, ...uploads];
    });
  }, []);

  return {
    datasets,
    failedDatasets,
    maxUploadBytes,
    supportedExtensions,
    isLoading,
    error,
    refresh,
    addDataset,
  };
}