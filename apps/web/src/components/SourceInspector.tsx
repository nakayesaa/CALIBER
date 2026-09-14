import { api, type DataSourceDetail, type TraceClaim } from '../lib/api';
import { formatDateTime, humanize } from '../lib/format';
import { useApiResource } from '../lib/useApiResource';
import { useTraceability } from './TraceabilityContext';

export function SourceInspector() {
  const { target, close, openSource } = useTraceability();
  if (!target) return null;
  return <InspectorContent kind={target.kind} id={target.id} onClose={close} onOpenSource={openSource}/>;
}

function InspectorContent({ kind, id, onClose, onOpenSource }: { kind: 'claim' | 'source'; id: string; onClose: () => void; onOpenSource: (sourceKey: string) => void }) {
  const resource = useApiResource<TraceClaim | DataSourceDetail>(
    `traceability-${kind}-${id}`,
    () => kind === 'claim' ? api.traceClaim(id) : api.dataSource(id),
  );
  return <aside className="source-inspector" aria-label="Source inspector">
    <header><div><span>Source inspector</span><h2>{resource.loading ? 'Loading evidence…' : resource.error ? 'Evidence unavailable' : kind === 'claim' ? (resource.data as TraceClaim).title : (resource.data as DataSourceDetail).source.title}</h2></div><button onClick={onClose} aria-label="Close source inspector">×</button></header>
    {resource.error && <div className="source-inspector-state"><p>{resource.error}</p><button onClick={resource.reload}>Try again</button></div>}
    {resource.data && (kind === 'claim'
      ? <ClaimDetail claim={resource.data as TraceClaim} onOpenSource={onOpenSource}/>
      : <SourceDetail detail={resource.data as DataSourceDetail}/>)}
  </aside>;
}

function ClaimDetail({ claim, onOpenSource }: { claim: TraceClaim; onOpenSource: (sourceKey: string) => void }) {
  return <div className="source-inspector-scroll">
    <section className="trace-claim-summary"><span>{humanize(claim.provenance)}</span><strong>{claim.value}{claim.unit ? <small>{claim.unit}</small> : null}</strong><p>{claim.summary}</p><time>Evidence as of {formatDateTime(claim.as_of)}</time></section>
    <InspectorSection title="How it was produced">
      <ol className="trace-calculation">{claim.calculation.map((line) => <li key={line}>{line}</li>)}</ol>
    </InspectorSection>
    <InspectorSection title="Data lineage">
      <ol className="trace-lineage">{claim.lineage.map((step) => <li key={step.sequence}><span>{step.kind}</span><strong>{step.label}</strong><small>{step.reference}</small></li>)}</ol>
    </InspectorSection>
    <InspectorSection title={`Supporting sources · ${claim.sources.length}`}>
      <div className="trace-source-list">{claim.sources.map((source) => <button key={source.source_key} onClick={() => onOpenSource(source.source_key)}><strong>{source.title}</strong><span>{source.role}</span><small>{source.mappings.length} governed field mappings</small></button>)}</div>
    </InspectorSection>
    {claim.quality_issues.length > 0 && <InspectorSection title={`Data quality · ${claim.quality_issues.length} items`}><QualityIssues issues={claim.quality_issues}/></InspectorSection>}
    {claim.preview && <InspectorSection title="Supporting records"><RecordPreview columns={claim.preview.columns} rows={claim.preview.rows}/></InspectorSection>}
  </div>;
}

function SourceDetail({ detail }: { detail: DataSourceDetail }) {
  return <div className="source-inspector-scroll">
    <section className="trace-claim-summary"><span>{humanize(detail.source.status)}</span><strong>{detail.source.record_count?.toLocaleString() ?? 'Reference'}<small>{detail.source.record_count === null ? 'source' : 'source records'}</small></strong><p>{detail.source.role}</p><a href={detail.source.source_url} target="_blank" rel="noreferrer">Open original source</a></section>
    <InspectorSection title="Source control"><dl className="trace-source-control"><div><dt>Domain</dt><dd>{detail.source.domain}</dd></div><div><dt>Cadence</dt><dd>{humanize(detail.source.cadence)}</dd></div><div><dt>Parser</dt><dd>{humanize(detail.parser)}</dd></div><div><dt>Local record</dt><dd>{detail.local_path}</dd></div><div><dt>Checksum</dt><dd>{detail.checksum.slice(0, 16)}…</dd></div></dl></InspectorSection>
    <InspectorSection title={`Field mappings · ${detail.mappings.length}`}><div className="trace-mapping-list">{detail.mappings.length ? detail.mappings.map((mapping) => <div key={mapping.source_field}><span>{mapping.source_field}</span><strong>{mapping.canonical_field}</strong><small>{mapping.unit} · {mapping.cadence} · {humanize(mapping.status)}</small></div>) : <p>No signal-level mappings required.</p>}</div></InspectorSection>
    {detail.quality_issues.length > 0 && <InspectorSection title={`Data quality · ${detail.quality_issues.length} items`}><QualityIssues issues={detail.quality_issues}/></InspectorSection>}
  </div>;
}

function InspectorSection({ title, children }: { title: string; children: React.ReactNode }) {
  return <section className="source-inspector-section"><h3>{title}</h3>{children}</section>;
}

function QualityIssues({ issues }: { issues: TraceClaim['quality_issues'] }) {
  return <div className="trace-quality-list">{issues.map((issue) => <article key={issue.issue_id}><header><strong>{humanize(issue.flag)}</strong><span>{humanize(issue.severity)}</span></header><p>{issue.description}</p><small>{humanize(issue.resolution_status)}</small></article>)}</div>;
}

function RecordPreview({ columns, rows }: NonNullable<TraceClaim['preview']>) {
  return <div className="trace-record-preview"><table><thead><tr>{columns.map((column) => <th key={column}>{humanize(column)}</th>)}</tr></thead><tbody>{rows.map((row, index) => <tr key={index}>{columns.map((column) => <td key={column}>{formatCell(row[column])}</td>)}</tr>)}</tbody></table></div>;
}

function formatCell(value: string | number | boolean | null): string {
  if (value === null) return '—';
  if (typeof value === 'boolean') return value ? 'Yes' : 'No';
  if (typeof value === 'number') return new Intl.NumberFormat('en-US', { maximumFractionDigits: 3 }).format(value);
  return value;
}
