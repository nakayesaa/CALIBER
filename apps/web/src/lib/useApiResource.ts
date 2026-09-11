import { useEffect, useState } from 'react';

export interface ResourceState<T> {
  data: T | null;
  error: string | null;
  loading: boolean;
}

export function useApiResource<T>(key: string, loader: () => Promise<T>): ResourceState<T> {
  const [state, setState] = useState<ResourceState<T>>({
    data: null,
    error: null,
    loading: true,
  });

  useEffect(() => {
    let active = true;
    setState((current) => ({ ...current, error: null, loading: true }));
    loader()
      .then((data) => {
        if (active) setState({ data, error: null, loading: false });
      })
      .catch((error: unknown) => {
        if (active) {
          setState({
            data: null,
            error: error instanceof Error ? error.message : 'Unable to load data',
            loading: false,
          });
        }
      });
    return () => {
      active = false;
    };
  }, [key]);

  return state;
}
