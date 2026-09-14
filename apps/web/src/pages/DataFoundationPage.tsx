import { useTraceability } from '../components/TraceabilityContext';
import { ErrorState, LoadingState } from '../components/ViewState';
import { api, type DataSourceSummary, type SystemStatus } from '../lib/api';
import { humanize } from '../lib/format';
import { useApiResource } from '../lib/useApiResource';
import { Metric, ViewHeader } from './ProblemTankPage';

interface DataFoundationData {
  system: SystemStatus;
  sources: DataSourceSummary[];
}

async function loadDataFoundation(): Promise<DataFoundationData> {
  const [system, sources] = await Promise.all([api.status(), api.dataSources()]);
  return { system, sources };
}

export function DataFoundationPage() {
  const { openSource } = useTraceability();
  const resource = useApiResource('data-foundation', loadDataFoundation);
  if (resource.loading) return <LoadingState/>;
  if (resource.error || !resource.data) return <ErrorState message={resource.error ?? 'Data foundation unavailable'}/>;

  const { system, sources } = resource.data;
  const artifacts = Object.entries(system.pipeline_artifacts);
  const readyCount = artifacts.filter(([, ready]) => ready).length;
  const issueCount = sources.reduce((total, source) => total + source.quality_issue_count, 0);
  const mappedFields = sources.reduce((total, source) => total + source.mapping_count, 0);

  return <div className="product-view data-foundation-page">
    <ViewHeader eyebrow="One governed foundation" title="Data foundation" description="Trace every operational insight from its original dashboard source through standardized fields, calculations, model decisions, and product views."/>
    <div className="summary-strip"><Metric label="Connected sources" value={`${sources.filter((source) => source.status !== 'REFERENCE').length}`}/><Metric label="Governed field mappings" value={`${mappedFields}`}/><Metric label="Source-quality references" value={`${issueCount}`}/><Metric label="Pipeline artifacts" value={`${readyCount}/${artifacts.length}`}/></div>

    <section className="source-registry-panel panel">
      <header><div><span>Cross-dashboard registry</span><h2>Manufacturing data sources</h2><p>Each source is registered once and reused across monitoring, RCA, and action workflows.</p></div><strong>{sources.length} sources</strong></header>
      <div className="source-registry-head"><span>Source and purpose</span><span>Domain</span><span>Cadence</span><span>Records</span><span>Governance</span><span/></div>
      {sources.map((source) => <button className="source-registry-row" key={source.source_key} onClick={() => openSource(source.source_key)}>
        <div><strong>{source.title}</strong><p>{source.role}</p></div>
        <span>{source.domain}</span><span>{humanize(source.cadence)}</span><span>{source.record_count?.toLocaleString() ?? 'Reference'}</span>
        <div><strong>{humanize(source.status)}</strong><small>{source.mapping_count} mappings · {source.quality_issue_count} quality items</small></div><b>›</b>
      </button>)}
    </section>

    <section className="pipeline-panel panel"><div className="section-heading"><div><span>Reusable data products</span><h2>KO-3201 governed flow</h2></div><strong>{readyCount}/{artifacts.length} ready</strong></div><div className="pipeline-flow">{artifacts.map(([name, ready], index) => <div className="pipeline-step" key={name}><span>{String(index + 1).padStart(2, '0')}</span><div><h3>{humanize(name)}</h3><p>{stageDescription(name)}</p></div><b className={ready ? 'ready' : ''}>{ready ? 'Ready' : 'Pending'}</b></div>)}</div></section>
  </div>;
}

function stageDescription(stage: string): string {
  const descriptions: Record<string, string> = {
    canonical: 'Standardized asset and signal records',
    features: 'Reusable condition and operating variables',
    model_scores: 'Auditable hourly anomaly outputs',
    alerts: 'Persistent decisions grouped into events',
    retrieval: 'Historical incidents ranked as RCA evidence',
    rca: 'Grounded indication with review state',
    actions: 'Owned CA/PA and effectiveness records',
  };
  return descriptions[stage] ?? 'Governed workflow artifact';
}
