import { useState, useEffect } from 'react';
import { activityService } from '../services/activityService';

export function useSchedule() {
  const [schedule, setSchedule] = useState([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    let mounted = true;
    activityService.getCommunicationSchedule()
      .then(data => {
        if (mounted) {
          setSchedule(data);
          setIsLoading(false);
        }
      })
      .catch(err => {
        if (mounted) {
          setError(err);
          setIsLoading(false);
        }
      });
      
    return () => { mounted = false; };
  }, []);

  return { schedule, isLoading, error };
}
