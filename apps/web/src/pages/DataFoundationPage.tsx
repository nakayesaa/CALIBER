import { ErrorState, LoadingState } from '../components/ViewState';
import { Icon } from '../components/Icon';
import { api } from '../lib/api';
import { humanize } from '../lib/format';
import { useApiResource } from '../lib/useApiResource';
import { Metric, ViewHeader } from './ProblemTankPage';

export function DataFoundationPage() {
  const resource = useApiResource('system-status', () => api.status());
  if (resource.loading) return <LoadingState/>;
  if (resource.error || !resource.data) return <ErrorState message={resource.error ?? 'No pipeline status returned'}/>;
  const entries = Object.entries(resource.data.pipeline_artifacts);
  const readyCount = entries.filter(([, ready]) => ready).length;
  return <div className="product-view"><ViewHeader eyebrow="One governed foundation" title="Data foundation" description="Source evidence is standardized once, then reused by monitoring, retrieval, RCA, and action workflows."/><div className="summary-strip"><Metric label="API status" value={humanize(resource.data.api_status)}/><Metric label="Pipeline artifacts" value={`${readyCount}/${entries.length}`}/><Metric label="RCA provider" value={resource.data.llm_enabled ? 'Connected' : 'Key pending'}/></div><section className="pipeline-panel panel"><div className="section-heading"><h2>KO-3201 data flow</h2><span className="governed-label"><Icon name="database"/> Canonical contracts</span></div><div className="pipeline-flow">{entries.map(([name, ready], index) => <div className="pipeline-step" key={name}><span>{String(index + 1).padStart(2, '0')}</span><div><h3>{humanize(name)}</h3><p>{stageDescription(name)}</p></div><b className={ready ? 'ready' : ''}>{ready ? 'Ready' : 'Pending'}</b></div>)}</div></section></div>;
}

function stageDescription(stage: string): string {
  const descriptions: Record<string, string> = {
    canonical: 'Hourly asset observations on one schema',
    features: 'Model-ready condition and context variables',
    model_scores: 'Anomaly score for each eligible hour',
    alerts: 'Persistent decisions grouped into events',
    retrieval: 'Historical incidents ranked for RCA evidence',
    rca: 'Audited AI draft and review state',
    actions: 'CA/PA ownership and effectiveness records',
  };
  return descriptions[stage] ?? 'Governed workflow artifact';
}
