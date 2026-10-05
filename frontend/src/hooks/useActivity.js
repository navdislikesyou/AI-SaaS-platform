import { useState, useEffect } from 'react';
import { activityService } from '../services/activityService';

export function useActivity() {
  const [activities, setActivities] = useState([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    let mounted = true;
    activityService.getRecentActivity()
      .then(data => {
        if (mounted) {
          setActivities(data);
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

  return { activities, isLoading, error };
}
