import { useState, useEffect } from 'react';
import { api } from '@/lib/api';

let cache = null;

/**
 * Fetches job choice fields from the API once and caches in memory.
 * Returns { choices, loading, error }.
 *
 * choices shape:
 * {
 *   location_types:      [{ value, label }]
 *   seniority_levels:    [{ value, label }]
 *   application_statuses:[{ value, label }]
 *   submission_methods:  [{ value, label }]
 *   remote_types:        [{ value, label }]
 * }
 */
export function useChoices() {
  const [choices, setChoices] = useState(cache);
  const [loading, setLoading] = useState(!cache);
  const [error, setError] = useState(null);

  useEffect(() => {
    if (cache) return;

    api.get('/api/jobs/choices/')
      .then((data) => {
        cache = data;
        setChoices(data);
      })
      .catch((err) => setError(err))
      .finally(() => setLoading(false));
  }, []);

  return { choices, loading, error };
}