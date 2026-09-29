import { useState, type ReactNode } from 'react';

import type { PageId } from '../components/AppShell';
import { ActionReportDialog } from '../components/ActionReportDialog';
import { Icon } from '../components/Icon';
import { api } from '../lib/api';
import type { PlantRateSeries } from '../lib/apiContracts';
import { PRIMARY_ASSET_ID } from '../lib/appConfig';
import { days, trendLabels, plantScenarios, performanceInsight, selectActionReport, selectPlantOverview, type PlantId, type PlantPerformance } from '../lib/plantOverviewDemoData';
import { useApiResource, type ResourceState } from '../lib/useApiResource';

function shortDate(date: string): string {
  return new Intl.DateTimeFormat('en-GB', { day: 'numeric', month: 'short', timeZone: 'UTC' }).format(new Date(`${date}T00:00:00Z`));
}

function TrendLine({ values, labels, label, unit = 't/h', showPoints = false }: { values: readonly number[]; labels: readonly string[]; label: string; unit?: string; showPoints?: boolean }) {
  const padding = Math.max((Math.max(...values) - Math.min(...values)) * 0.2, Math.max(...values) * 0.02, 0.01);
  const low = Math.min(...values) - padding;
  const range = Math.max(...values) - low + padding;
  const coordinates = values.map((value, index) => ({ x: index * 360 / Math.max(1, values.length - 1), y: 100 - (value - low) / range * 100 }));
  return <svg className="portfolio-trend" viewBox="0 0 360 100" preserveAspectRatio="none" role="img" aria-label={`${label}: ${values.map((value, index) => `${labels[index]} ${value.toFixed(2)}`).join(', ')}`}>
    <line x1="0" y1="50" x2="360" y2="50" stroke="#e5eee5" strokeDasharray="4 4" />
    <polyline points={coordinates.map(({ x, y }) => `${x},${y}`).join(' ')} fill="none" stroke="#447a4f" strokeWidth="3" strokeLinejoin="round" strokeLinecap="round" vectorEffect="non-scaling-stroke" />
    {coordinates.map(({ x, y }, index) => <circle className={showPoints ? '' : 'portfolio-hover-point'} key={labels[index]} cx={x} cy={y} r={showPoints ? 2.5 : 5} fill="#447a4f"><title>{`${labels[index]} · ${values[index].toFixed(2)} ${unit}`}</title></circle>)}
  </svg>;
}

function ChartCard({ eyebrow, title, value, note, children, className = '' }: { eyebrow: string; title: string; value: string; note: string; children: ReactNode; className?: string }) {
  return <section className={`portfolio-card portfolio-metric ${className}`}>
    <header><div><span>{eyebrow}</span><h2>{title}</h2></div><strong>{value}</strong></header>
    {children}<footer>{note}</footer>
  </section>;
}

type BarDrilldown = { day: string; asset: string; onClick: () => void };

function DailyBars({ values, label, kind, drilldown }: { values: readonly number[]; label: string; kind: 'condition' | 'downtime'; drilldown?: BarDrilldown }) {
  const scale = Math.max(1, ...values);
  return <div className={`portfolio-daily-bars ${kind}`} role="group" aria-label={`${label}: ${values.map((value, index) => `${days[index]} ${value}`).join(', ')}`}>
    {values.map((value, index) => {
      const content = <><b>{kind === 'downtime' ? `${value} h` : value}</b><span className="portfolio-bar-track"><i style={{ height: `${value / scale * 100}%` }} /></span><small>{days[index]}</small></>;
      return days[index] === drilldown?.day
        ? <button className="portfolio-bar-day is-linked" key={days[index]} onClick={drilldown.onClick} aria-label={`${days[index]}: ${value} asset needing attention. Open ${drilldown.asset} overview`} title={`Open ${drilldown.asset} overview`}>{content}</button>
        : <div className="portfolio-bar-day" key={days[index]}>{content}</div>;
    })}
  </div>;
}

function PlantRateCard({ selectedPlant, visiblePlants, resource }: { selectedPlant: PlantId; visiblePlants: readonly PlantPerformance[]; resource: ResourceState<PlantRateSeries> }) {
  if (selectedPlant === 'ZCU') {
    const points = resource.data?.points ?? [];
    const labels = points.map((point) => shortDate(point.date));
    const axis = [0, Math.floor((labels.length - 1) / 3), Math.floor((labels.length - 1) * 2 / 3), labels.length - 1]
      .map((index) => labels[index]);
    const latest = points.at(-1);
    return <ChartCard className="portfolio-production-chart is-source-backed" eyebrow="Production" title="Plant rate · daily mean" value={latest ? `${latest.average_rate_tph.toFixed(2)} t/h` : resource.loading ? 'Loading…' : 'Unavailable'} note={resource.data ? `${resource.data.source_reference} · ${resource.data.source_rows} hourly readings → ${points.length} daily means, including offline hours.` : resource.error ?? 'Loading observed production data.'}>
      {points.length ? <div className="portfolio-production-lines"><div className="portfolio-production-line"><span>ZCU</span><TrendLine values={points.map((point) => point.average_rate_tph)} labels={labels} label="ZCU observed daily mean plant rate in t/h" showPoints /><strong>{latest!.average_rate_tph.toFixed(2)} <small>t/h</small></strong></div></div> : <div className="portfolio-source-state">{resource.loading ? 'Loading observed PLANT_RATE readings…' : resource.error ?? 'No observed PLANT_RATE readings available.'}</div>}
      {points.length > 0 && <div className="portfolio-chart-axis">{axis.map((label) => <span key={label}>{label}</span>)}</div>}
    </ChartCard>;
  }

  const plant = visiblePlants[0];
  return <ChartCard className="portfolio-production-chart is-single-plant" eyebrow="Production" title="Plant rate" value={`${plant.production.at(-1)} t/h`} note="168 hourly scenario readings · latest daily mean shown above.">
    <div className="portfolio-production-lines"><div className="portfolio-production-line"><span>{plant.id}</span><TrendLine values={plant.trends.production} labels={trendLabels} label={`${plant.id} hourly production rate`} /><strong>{plant.trends.production.at(-1)!.toFixed(2)} <small>t/h</small></strong></div></div>
    <div className="portfolio-chart-axis"><span>{days[0]}</span><span>{days.at(-1)}</span></div>
  </ChartCard>;
}

function IntensityCard({ plants, metric }: { plants: readonly PlantPerformance[]; metric: 'energy' | 'emissions' }) {
  const plant = plants[0];
  const energy = metric === 'energy';
  const unit = energy ? 'GJ/t' : 'tCO₂e/t';
  return <ChartCard className={`portfolio-production-chart portfolio-${metric} is-single-plant`} eyebrow={energy ? 'Energy efficiency' : 'Environmental performance'} title={energy ? 'Specific energy' : 'Emissions intensity'} value={`${plant[metric].at(-1)!.toFixed(2)} ${unit}`} note={`168 hourly scenario readings · latest daily mean shown above. ${energy ? 'Compare at similar load.' : 'Efficiency indicator, not compliance.'}`}>
    <div className="portfolio-production-lines"><div className="portfolio-production-line"><span>{plant.id}</span><TrendLine values={plant.trends[metric]} labels={trendLabels} label={`${plant.id} hourly ${metric} intensity`} unit={unit} /><strong>{plant.trends[metric].at(-1)!.toFixed(2)} <small>{unit}</small></strong></div></div>
    <div className="portfolio-chart-axis"><span>{days[0]}</span><span>{days.at(-1)}</span></div>
  </ChartCard>;
}

export function PlantPage({ onNavigate }: { onNavigate: (page: PageId) => void }) {
  const [selectedPlant, setSelectedPlant] = useState<PlantId>('ZCU');
  const [query, setQuery] = useState('');
  const [reportActionId, setReportActionId] = useState<string | null>(null);
  const plantRate = useApiResource(PRIMARY_ASSET_ID, () => api.plantRate(PRIMARY_ASSET_ID));
  const zcuSource = selectedPlant === 'ZCU';
  const overview = selectPlantOverview(selectedPlant, plantRate.data ? 'ready' : plantRate.loading ? 'loading' : 'unavailable');
  const { plants: visiblePlants, attention, downtime, actions, issues } = overview;
  const visibleIssues = issues.filter((item) => `${item.tag} ${item.title} ${item.plant} ${item.owner}`.toLowerCase().includes(query.trim().toLowerCase()));
  const actionStates = ['Open', 'In progress', 'Awaiting verification', 'Verified'] as const;
  const actionCounts = actionStates.map((status) => actions.filter((action) => action.status === status).length);
  const overdue = actions.filter((action) => action.overdue).length;
  const firstIssue = issues[0];
  const actionReport = reportActionId ? selectActionReport(selectedPlant, reportActionId) : undefined;
  const observed = plantRate.data?.points;
  const currentRate = zcuSource ? observed?.at(-1)?.average_rate_tph : visiblePlants[0].production.at(-1);
  const referenceRate = zcuSource && observed?.length ? observed.slice(0, 7).reduce((sum, point) => sum + point.average_rate_tph, 0) / Math.min(7, observed.length) : zcuSource ? undefined : visiblePlants[0].production[0];

  return <div className="portfolio-page">
    <header className="portfolio-heading">
      <div><span>Manufacturing performance</span><h1>Plant overview</h1><p>Understand the shift. Find the exception. Follow it through.</p></div>
      <div className="portfolio-period"><strong>{zcuSource ? 'Production: 1–30 Apr 2026' : 'Trends: 24–30 Apr 2026'}</strong></div>
    </header>

    <nav className="portfolio-plant-filter" aria-label="Select plant">
      {plantScenarios.map((plant) => <button key={plant.id} className={selectedPlant === plant.id ? 'active' : ''} aria-pressed={selectedPlant === plant.id} onClick={() => setSelectedPlant(plant.id)}>{plant.id} <small>{String(plant.assets).padStart(2, '0')}</small></button>)}
    </nav>

    <section className="portfolio-shift-brief" aria-label="Operating brief">
      <div><span className="portfolio-section-kicker">Shift brief</span><h2>{firstIssue ? `${firstIssue.plant} needs a closer look.` : 'No open issues in this scenario.'}</h2><p>{firstIssue?.impact ?? 'The selected plant has no current attention flags. Continue routine trend monitoring.'}</p></div>
      <div className="portfolio-brief-stat"><strong>{attention.at(-1)}<small> / {overview.assetCount}</small></strong><span>assets flagged now</span></div>
      <div className="portfolio-brief-stat"><strong>{overdue}</strong><span>overdue actions</span></div>
    </section>

    <div className="portfolio-section-heading"><span>01 · Performance</span><p>Read production alongside resource efficiency.</p></div>

    <div className="portfolio-dashboard portfolio-performance-grid">
      <PlantRateCard selectedPlant={selectedPlant} visiblePlants={visiblePlants} resource={plantRate} />
      <IntensityCard plants={visiblePlants} metric="energy" />
      <IntensityCard plants={visiblePlants} metric="emissions" />
    </div>

    <aside className="portfolio-output-context" aria-label="Plant performance insight"><span className="portfolio-section-kicker">Performance insight</span><p>{performanceInsight(selectedPlant, currentRate, referenceRate)} <small>{zcuSource ? 'Reference: 1–7 Apr observed mean.' : 'Reference: 24 Apr scenario daily mean.'}</small></p></aside>

    <div className="portfolio-section-heading"><span>02 · Operating exceptions</span><p>Locate equipment exposure and follow-up gaps.</p></div>
    <div className="portfolio-dashboard portfolio-performance-grid">
      <ChartCard eyebrow="Equipment condition" title="Assets needing attention" value={`${attention.at(-1)} / ${overview.assetCount}`} note={`Current attention flags among monitored assets.${zcuSource ? ' Click 30 Apr to open KO-3201.' : ''}`}>
        <DailyBars values={attention} label="Assets needing attention by day" kind="condition" drilldown={zcuSource ? { day: '30 Apr', asset: 'KO-3201', onClick: () => onNavigate('overview') } : undefined} />
      </ChartCard>

      <ChartCard eyebrow="Equipment availability" title="Monitored equipment downtime" value={`${downtime.reduce((sum, value) => sum + value, 0)} h`} note={`Sum of equipment-hours, not plant outage duration.${zcuSource ? ' ZCU: 32 h on KO-3201.' : ''}`}>
        <DailyBars values={downtime} label="Monitored equipment downtime hours by day" kind="downtime" />
      </ChartCard>

      <ChartCard eyebrow="Follow-up" title="Action progress" value={`${actionCounts[3]} / ${actions.length} verified`} note={actions.length ? `${overdue} overdue · ${actionCounts[2]} awaiting effectiveness verification.` : 'No follow-up actions for the selected plant in this snapshot.'}>
        <div className="portfolio-action-chart">{actionStates.map((status, index) => <div key={status}><span>{status}</span><i><b className={`state-${index}`} style={{ width: `${actionCounts[index] / Math.max(1, ...actionCounts) * 100}%` }} /></i><strong>{actionCounts[index]}</strong></div>)}</div>
      </ChartCard>
    </div>

    <div className="portfolio-section-heading"><span>03 · Decisions & ownership</span><p>Start with the highest priority, then track the response.</p></div>
    <section className="portfolio-card portfolio-issue-list" aria-labelledby="portfolio-issues-title">
      <header><div><span>Problem tank</span><h2 id="portfolio-issues-title">What needs a decision?</h2><p>Current scenario issues, ordered by severity. Expand to read the supporting rationale.</p></div><button onClick={() => onNavigate('problems')}>Problem tank <Icon name="arrow" /></button></header>
      <div className="portfolio-issue-tools"><label><Icon name="search"/><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search equipment or issue" aria-label="Search equipment or issue"/></label><span>{visibleIssues.length} {visibleIssues.length === 1 ? 'result' : 'results'}</span></div>
      <div className="portfolio-issue-rows">{visibleIssues.map((item) => <details className="portfolio-operating-issue" key={item.id}>
        <summary><span className={`portfolio-status ${item.severity.toLowerCase()}`}>{item.severity}</span><span><strong>{item.tag} <small>· {item.plant}</small></strong><span>{item.title}</span></span><span className="portfolio-issue-owner">{item.owner}</span><span className="portfolio-disclosure" aria-hidden="true">+</span></summary>
        <div className="portfolio-issue-evidence"><div><span>Operating impact</span><p>{item.impact}</p></div><div><span>Probable cause</span><p>{item.indication}</p></div><div><span>Supporting checks</span><p>{item.evidence}</p></div><div><span>Next action</span><p>{item.nextStep}</p></div>{item.investigationAvailable && <button onClick={() => onNavigate('investigation')}>Open KO-3201 investigation <Icon name="arrow" /></button>}</div>
      </details>)}{!visibleIssues.length && <p className="portfolio-issue-empty">{query ? 'No issues match this search.' : 'No open issues in this plant scenario.'}</p>}</div>
    </section>

    <section className="portfolio-card portfolio-ownership" aria-labelledby="portfolio-ownership-title"><header><div><span className="portfolio-section-kicker">Action tracking</span><h2 id="portfolio-ownership-title">Who does what next?</h2></div><span>{actions.length} actions</span></header>
      {actions.map((action) => <button className="portfolio-owner-row" key={action.id} onClick={() => setReportActionId(action.id)} aria-haspopup="dialog" aria-label={`Open action report: ${action.title}`}><div><strong>{action.title}</strong><span>{action.owner} · View report</span></div><span className={`portfolio-status ${action.overdue ? 'high' : action.status === 'Verified' ? 'verified' : 'watch'}`}>{action.status}</span><div className={action.overdue ? 'portfolio-due is-overdue' : 'portfolio-due'}><strong>{action.due}</strong><span>{action.overdue ? 'Overdue at snapshot' : 'Due date'}</span></div></button>)}
      {!actions.length && <p className="portfolio-issue-empty">No actions assigned in this scenario.</p>}
    </section>

    <details className="portfolio-card portfolio-data-coverage"><summary><div><span className="portfolio-section-kicker">Connected data</span><strong>Five source views. One operating picture.</strong><span>Production · Energy · HSE · Equipment · Follow-up</span></div><span className="portfolio-disclosure" aria-hidden="true">+</span></summary>
      <div className="portfolio-source-grid">{overview.sources.map((source) => <div key={source.name}><strong>{source.name}</strong><span>{source.system}</span><b>{source.metric}</b><p>{source.basis}</p><small>{source.freshness}</small></div>)}</div>
      <div className="portfolio-source-note"><span>Scope: {overview.assetCount} monitored assets · new metrics and issue records use one aligned demo fixture.</span><button onClick={() => onNavigate('data')}>View source mapping <Icon name="arrow" /></button></div>
    </details>
    {actionReport && <ActionReportDialog record={actionReport} production={plantRate.data} onClose={() => setReportActionId(null)} />}
  </div>;
}
