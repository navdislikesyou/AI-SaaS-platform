import { useState, useEffect } from 'react';
import { agentService } from '../services/agentService';

export function useAgents() {
  const [agents, setAgents] = useState([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    let mounted = true;
    agentService.getAgents()
      .then(data => {
        if (mounted) {
          setAgents(data);
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

  return { agents, isLoading, error };
}
