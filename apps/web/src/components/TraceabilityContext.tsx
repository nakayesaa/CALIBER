import { createContext, useContext, useMemo, useState, type ReactNode } from 'react';

export type TraceTarget =
  | { kind: 'claim'; id: string }
  | { kind: 'source'; id: string };

interface TraceabilityContextValue {
  target: TraceTarget | null;
  openClaim: (traceId: string) => void;
  openSource: (sourceKey: string) => void;
  close: () => void;
}

const TraceabilityContext = createContext<TraceabilityContextValue | null>(null);

export function TraceabilityProvider({ children }: { children: ReactNode }) {
  const [target, setTarget] = useState<TraceTarget | null>(null);
  const value = useMemo<TraceabilityContextValue>(() => ({
    target,
    openClaim: (id) => setTarget({ kind: 'claim', id }),
    openSource: (id) => setTarget({ kind: 'source', id }),
    close: () => setTarget(null),
  }), [target]);
  return <TraceabilityContext.Provider value={value}>{children}</TraceabilityContext.Provider>;
}

export function useTraceability(): TraceabilityContextValue {
  const context = useContext(TraceabilityContext);
  if (!context) throw new Error('useTraceability must be used within TraceabilityProvider');
  return context;
}

export function TraceButton({ traceId, children = 'View sources', className = '' }: { traceId: string; children?: ReactNode; className?: string }) {
  const { openClaim } = useTraceability();
  return <button className={`trace-button ${className}`.trim()} onClick={() => openClaim(traceId)}>{children}</button>;
}
