import { useCallback, useEffect, useState } from 'react';
import { automationService } from '../services/automationService';

/**
 * Load the employee directories the backend has accepted.
 *
 * The backend manifest is the source of truth for the directory selector.
 * Directories whose records did not validate come back with `status: 'failed'`
 * and are kept out of `directories`, so a directory that cannot resolve any
 * recipient is never offered as a choice.
 *
 * @returns {{
 *   directories: Array<object>,
 *   failedDirectories: Array<object>,
 *   isLoading: boolean,
 *   error: Error|null,
 *   refresh: () => Promise<void>,
 *   addDirectory: (directory: object) => void,
 * }}
 */
export function useEmployeeDirectories() {
  const [directories, setDirectories] = useState([]);
  const [failedDirectories, setFailedDirectories] = useState([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState(null);

  /**
   * Split a backend listing into ready and failed directories.
   *
   * @param {Array<object>} all
   */
  const applyListing = useCallback((all) => {
    const rows = Array.isArray(all) ? all : [];

    setDirectories(rows.filter((row) => row?.status === 'ready'));
    setFailedDirectories(rows.filter((row) => row?.status !== 'ready'));
  }, []);

  /**
   * Reload the directory list from the backend.
   */
  const refresh = useCallback(async () => {
    setIsLoading(true);

    try {
      applyListing(await automationService.listDirectories());
      setError(null);
    } catch (err) {
      setError(err);
    } finally {
      setIsLoading(false);
    }
  }, [applyListing]);

  useEffect(() => {
    let mounted = true;

    automationService
      .listDirectories()
      .then((all) => {
        if (mounted) applyListing(all);
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
   * Insert a newly uploaded directory at the head of the list.
   *
   * Used after an upload so the selector updates without a second round trip.
   * The backend remains authoritative; this only avoids a redundant refetch.
   *
   * @param {object} directory
   */
  const addDirectory = useCallback((directory) => {
    if (!directory?.directory_id) return;

    setDirectories((current) => [
      directory,
      ...current.filter((row) => row.directory_id !== directory.directory_id),
    ]);
  }, []);

  return {
    directories,
    failedDirectories,
    isLoading,
    error,
    refresh,
    addDirectory,
  };
}