import type { MetricSource } from '../lib/plantPerformance';
import { useTraceability } from './TraceabilityContext';

export function MetricSourceDisclosure({ title, source }: { title: string; source: MetricSource }) {
  const { openSource } = useTraceability();
  return <details className="portfolio-metric-source"><summary>Data basis · {title}</summary><dl>{Object.entries(source.fields).map(([key, value]) => <div key={key}><dt>{key}</dt><dd>{value}</dd></div>)}</dl>{source.sourceKey && <button onClick={() => openSource(source.sourceKey!)}>Open workbook mapping and source rows</button>}</details>;
}
