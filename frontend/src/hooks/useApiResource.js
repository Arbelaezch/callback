'use client';

import { useCallback, useEffect, useState } from 'react';
import { apiClient } from '@/lib/apiClient';

/**
 * Load a JSON resource through apiClient.
 *
 * Returns { data, error, loading, reload }. `reload()` refetches in the
 * background: `data` keeps its previous value (no loading flash) until the
 * new response lands. Pass `null` as the path to skip fetching.
 */
export function useApiResource(path) {
  const [state, setState] = useState({ data: null, error: null, loading: Boolean(path) });
  const [version, setVersion] = useState(0);

  useEffect(() => {
    if (!path) return undefined;
    let active = true;
    apiClient.get(path).then(
      (data) => active && setState({ data, error: null, loading: false }),
      (error) => active && setState((prev) => ({ data: prev.data, error, loading: false })),
    );
    return () => {
      active = false;
    };
  }, [path, version]);

  const reload = useCallback(() => setVersion((v) => v + 1), []);

  return { ...state, reload };
}
