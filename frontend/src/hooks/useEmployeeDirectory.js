import { useCallback, useEffect, useState } from 'react';
import { apiClient } from '../services/api';

/**
 * Hook for fetching active registered employees from the organization.
 *
 * Returns the active employees in the authenticated user's organisation,
 * sourced from the backend User model. Results are sorted by full_name
 * and include id, email, full_name, and role.
 *
 * @returns {{
 *   employees: Array<{id, email, full_name, role}>,
 *   isLoading: boolean,
 *   error: Error|null,
 *   refresh: () => Promise<void>,
 * }}}
 */
export function useEmployeeDirectory() {
  const [employees, setEmployees] = useState([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState(null);

  /**
   * Reload the employee list from the backend.
   */
  const refresh = useCallback(async () => {
    setIsLoading(true);
    setError(null);

    try {
      const res = await apiClient.get('/automation/employees');
      const data = res?.data;

      if (data && Array.isArray(data)) {
        setEmployees(data);
      } else {
        setEmployees([]);
      }
    } catch (err) {
      setError(err);
      setEmployees([]);
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  return {
    employees,
    isLoading,
    error,
    refresh,
  };
}