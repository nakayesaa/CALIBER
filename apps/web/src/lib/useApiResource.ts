import { useCallback, useEffect, useState } from 'react';

export interface ResourceState<T> {
  data: T | null;
  error: string | null;
  loading: boolean;
  reload: () => void;
}

export function useApiResource<T>(key: string, loader: () => Promise<T>): ResourceState<T> {
  const [revision, setRevision] = useState(0);
  const reload = useCallback(() => setRevision((value) => value + 1), []);
  const [state, setState] = useState<ResourceState<T>>({
    data: null,
    error: null,
    loading: true,
    reload,
  });

  useEffect(() => {
    let active = true;
    setState((current) => ({ ...current, error: null, loading: true }));
    loader()
      .then((data) => {
        if (active) setState({ data, error: null, loading: false, reload });
      })
      .catch((error: unknown) => {
        if (active) {
          setState({
            data: null,
            error: error instanceof Error ? error.message : 'Unable to load data',
            loading: false,
            reload,
          });
        }
      });
    return () => {
      active = false;
    };
  }, [key, reload, revision]);

  return state;
}
