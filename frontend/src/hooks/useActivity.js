import { useState, useEffect, useCallback } from 'react';
import { activityService } from '../services/activityService';

/**
 * Load the unified Activity History.
 *
 * Reads GET /activity-history, which returns lightweight metadata records for
 * Knowledge, Automation, and Performance, newest first. An empty history is a
 * valid state, so `activities` is simply an empty array and `error` stays null.
 */
export function useActivity() {
  const [activities, setActivities] = useState([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState(null);

  const load = useCallback(async () => {
    setIsLoading(true);

    try {
      const data = await activityService.getActivityHistory();

      setActivities(Array.isArray(data) ? data : []);
      setError(null);
    } catch (err) {
      setError(err);
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    let mounted = true;

    activityService
      .getActivityHistory()
      .then((data) => {
        if (mounted) {
          setActivities(Array.isArray(data) ? data : []);
          setIsLoading(false);
        }
      })
      .catch((err) => {
        if (mounted) {
          setError(err);
          setIsLoading(false);
        }
      });

    return () => {
      mounted = false;
    };
  }, []);

  return { activities, isLoading, error, refresh: load };
}
