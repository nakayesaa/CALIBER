import { useState, type ReactNode } from 'react';

import type { PageId } from '../components/AppShell';
import { ActionReportDialog } from '../components/ActionReportDialog';
import { Icon } from '../components/Icon';
import { api } from '../lib/api';
import type { PlantRateSeries } from '../lib/apiContracts';
import { PRIMARY_ASSET_ID } from '../lib/appConfig';
import { plantScenarios, performanceInsight, selectActionReport, selectPlantOverview, type PlantId, type PlantPerformance } from '../lib/plantOverviewDemoData';
import { operatingBrief, performanceWindow, resourcePerformance, type OverviewDays } from '../lib/plantPerformance';
import { useApiResource, type ResourceState } from '../lib/useApiResource';

function shortDate(date: string): string {
  return new Intl.DateTimeFormat('en-GB', { day: 'numeric', month: 'short', timeZone: 'UTC' }).format(new Date(`${date}T00:00:00Z`));
}

function TrendLine({ values, labels, label, unit = 't/h', showPoints = false, reference }: { values: readonly number[]; labels: readonly string[]; label: string; unit?: string; showPoints?: boolean; reference?: number }) {
  const scaleValues = reference === undefined ? values : [...values, reference];
  const padding = Math.max((Math.max(...scaleValues) - Math.min(...scaleValues)) * 0.2, Math.max(...scaleValues) * 0.02, 0.01);
  const low = Math.min(...scaleValues) - padding;
  const range = Math.max(...scaleValues) - low + padding;
  const coordinates = values.map((value, index) => ({ x: index * 360 / Math.max(1, values.length - 1), y: 100 - (value - low) / range * 100 }));
  return <svg className="portfolio-trend" viewBox="0 0 360 100" preserveAspectRatio="none" role="img" aria-label={`${label}: ${values.map((value, index) => `${labels[index]} ${value.toFixed(2)}`).join(', ')}`}>
    <line x1="0" y1="50" x2="360" y2="50" stroke="#e5eee5" strokeDasharray="4 4" />
    {reference !== undefined && <line x1="0" y1={100 - (reference - low) / range * 100} x2="360" y2={100 - (reference - low) / range * 100} stroke="#6B6B6B" strokeDasharray="6 4" vectorEffect="non-scaling-stroke"><title>Reference: {reference.toFixed(2)} {unit}</title></line>}
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

function DailyBars({ values, days, label, kind, drilldown }: { values: readonly number[]; days: readonly string[]; label: string; kind: 'condition' | 'downtime'; drilldown?: BarDrilldown }) {
  const scale = Math.max(1, ...values);
  return <div className={`portfolio-daily-bars ${kind}`} style={{ gridTemplateColumns: `repeat(${values.length}, minmax(0, 1fr))` }} role="group" aria-label={`${label}: ${values.map((value, index) => `${days[index]} ${value}`).join(', ')}`}>
    {values.map((value, index) => {
      const content = <><b>{kind === 'downtime' ? `${value} h` : value}</b><span className="portfolio-bar-track"><i style={{ height: `${value / scale * 100}%` }} /></span><small>{days[index]}</small></>;
      return days[index] === drilldown?.day
        ? <button className="portfolio-bar-day is-linked" key={days[index]} onClick={drilldown.onClick} aria-label={`${days[index]}: ${value} asset needing attention. Open ${drilldown.asset} overview`} title={`Open ${drilldown.asset} overview`}>{content}</button>
        : <div className="portfolio-bar-day" key={days[index]}>{content}</div>;
    })}
  </div>;
}

type ResourceMetrics = ReturnType<typeof resourcePerformance>;
const formatted = (value: number | undefined, unit: string) => value === undefined ? 'Unavailable' : `${value.toLocaleString('en-GB', { maximumFractionDigits: 1 })} ${unit}`;
const percent = (value: number | undefined) => value === undefined ? 'Unavailable' : `${value > 0 ? '+' : ''}${value.toFixed(1)}%`;

function PlantRateCard({ plant, window, metrics, resource }: { plant: PlantPerformance; window: ReturnType<typeof performanceWindow>; metrics: ResourceMetrics; resource: ResourceState<PlantRateSeries> }) {
  const latest = window.production.at(-1);
  const observed = plant.id === 'ZCU';
  return <ChartCard className="portfolio-production-chart is-single-plant" eyebrow="Production" title={`Plant rate${observed ? ' · daily mean' : ''}`} value={latest !== undefined ? `${latest.toFixed(2)} ${window.productionUnit}` : resource.loading ? 'Loading…' : 'Unavailable'} note={observed ? `${window.productionReadings} source hourly readings → ${window.production.length} daily means, including offline hours.${window.complete ? '' : ' Incomplete coverage.'}` : `${window.production.length} hourly scenario readings.`}>
    {window.production.length ? <div className="portfolio-production-lines"><div className="portfolio-production-line"><span>{plant.id}</span><TrendLine values={window.production} labels={window.productionLabels} label={`${plant.id} ${window.productionCadence} plant rate`} unit={window.productionUnit} showPoints={observed} reference={metrics.referenceRate} /><strong>{latest!.toFixed(2)} <small>{window.productionUnit}</small></strong></div></div> : <div className="portfolio-source-state">{resource.loading ? 'Loading observed PLANT_RATE readings…' : resource.error ?? 'No observed PLANT_RATE readings available.'}</div>}
    <div className="portfolio-chart-axis"><span>{shortDate(window.start)}</span><span>{shortDate(window.end)}</span></div>
    <p className="portfolio-kpi-context">{percent(metrics.productionDeviation)} vs reference · dashed line {formatted(metrics.referenceRate, window.productionUnit)}</p>
  </ChartCard>;
}

function IntensityCard({ plant, window, metrics, metric }: { plant: PlantPerformance; window: ReturnType<typeof performanceWindow>; metrics: ResourceMetrics; metric: 'energy' | 'emissions' }) {
  const energy = metric === 'energy';
  const unit = `${energy ? 'GJ' : 'tCO₂e'}/${plant.id === 'NUP' ? 't equiv.' : 't'}`;
  return <ChartCard className={`portfolio-production-chart portfolio-${metric} is-single-plant`} eyebrow={energy ? 'Energy efficiency' : 'Environmental performance'} title={energy ? 'Specific energy' : 'Emissions intensity'} value={`${plant[metric].at(-1)!.toFixed(2)} ${unit}`} note={`${window[metric].length} hourly scenario readings · latest daily mean shown above. ${energy ? 'Compare at similar load.' : 'Efficiency indicator, not compliance.'}`}>
    <div className="portfolio-production-lines"><div className="portfolio-production-line"><span>{plant.id}</span><TrendLine values={window[metric]} labels={window.labels} label={`${plant.id} hourly ${metric} intensity`} unit={unit} reference={energy ? metrics.energyReference : metrics.emissionsReference} /><strong>{window[metric].at(-1)!.toFixed(2)} <small>{unit}</small></strong></div></div>
    <div className="portfolio-chart-axis"><span>{window.days[0]}</span><span>{window.days.at(-1)}</span></div>
    <p className="portfolio-kpi-context">{percent(energy ? metrics.energyDeviation : metrics.emissionsDeviation)} vs 24 Apr scenario reference · dashed line</p>
    <p className="portfolio-kpi-context"><strong>{formatted(energy ? metrics.energyTotal : metrics.emissionsTotal, energy ? 'GJ' : 'tCO₂e')}</strong> · window total estimate from daily mean rate × intensity × 24 h</p>
  </ChartCard>;
}

export function PlantPage({ onNavigate }: { onNavigate: (page: PageId) => void }) {
  const [selectedPlant, setSelectedPlant] = useState<PlantId>('ZCU');
  const [query, setQuery] = useState('');
  const [windowDays, setWindowDays] = useState<OverviewDays>(7);
  const [plannedRate, setPlannedRate] = useState('');
  const [reportActionId, setReportActionId] = useState<string | null>(null);
  const plantRate = useApiResource(PRIMARY_ASSET_ID, () => api.plantRate(PRIMARY_ASSET_ID));
  const zcuSource = selectedPlant === 'ZCU';
  const overview = selectPlantOverview(selectedPlant, plantRate.data ? 'ready' : plantRate.loading ? 'loading' : 'unavailable');
  const { plants: visiblePlants, actions, issues } = overview;
  const plant = visiblePlants[0];
  const window = performanceWindow(plant, plantRate.data, windowDays);
  const metrics = resourcePerformance(plant, plantRate.data, windowDays, plannedRate.trim() ? Number(plannedRate) : undefined);
  const { attention, downtime } = window;
  const visibleIssues = issues.filter((item) => `${item.tag} ${item.title} ${item.plant} ${item.owner}`.toLowerCase().includes(query.trim().toLowerCase()));
  const actionStates = ['Open', 'In progress', 'Awaiting verification', 'Verified'] as const;
  const actionCounts = actionStates.map((status) => actions.filter((action) => action.status === status).length);
  const overdue = actions.filter((action) => action.overdue).length;
  const brief = operatingBrief(plant, metrics, downtime, issues, actions);
  const actionReport = reportActionId ? selectActionReport(selectedPlant, reportActionId) : undefined;

  return <div className="portfolio-page">
    <header className="portfolio-heading">
      <div><span>Manufacturing performance</span><h1>Plant overview</h1><p>Understand the shift. Find the exception. Follow it through.</p></div>
      <div className="portfolio-period"><strong>{shortDate(window.start)}–30 Apr 2026 · WIB</strong><label>Shared chart window <select value={windowDays} onChange={(event) => setWindowDays(Number(event.target.value) as OverviewDays)}><option value={1}>1 day</option><option value={3}>3 days</option><option value={7}>7 days</option></select></label></div>
    </header>

    <nav className="portfolio-plant-filter" aria-label="Select plant">
      {plantScenarios.map((plant) => <button key={plant.id} className={selectedPlant === plant.id ? 'active' : ''} aria-pressed={selectedPlant === plant.id} onClick={() => { setSelectedPlant(plant.id); setPlannedRate(''); }}>{plant.id} <small>{String(plant.assets).padStart(2, '0')}</small></button>)}
    </nav>

    <section className="portfolio-shift-brief" aria-label="Operating brief">
      <div><span className="portfolio-section-kicker">Operating brief</span><h2>{brief.title}</h2><p>{brief.summary}</p><p className="portfolio-brief-next">{brief.next}</p></div>
      <div className="portfolio-brief-stat"><strong>{attention.at(-1)}<small> / {overview.assetCount}</small></strong><span>assets flagged now</span></div>
      <div className="portfolio-brief-stat"><strong>{overdue}</strong><span>overdue actions</span></div>
    </section>

    <div className="portfolio-section-heading"><span>01 · Performance</span><p>Read production alongside resource efficiency.</p></div>

    <div className="portfolio-dashboard portfolio-performance-grid">
      <PlantRateCard plant={plant} window={window} metrics={metrics} resource={plantRate} />
      <IntensityCard plant={plant} window={window} metrics={metrics} metric="energy" />
      <IntensityCard plant={plant} window={window} metrics={metrics} metric="emissions" />
    </div>

    <section className="portfolio-card portfolio-forecast" aria-label="Energy forecast"><div><span className="portfolio-section-kicker">Next 24 hours · energy forecast</span><h2>{formatted(metrics.forecast, 'GJ')}</h2><p>Constant-load estimate: assumed rate × 24 Apr reference intensity × 24 hours.</p></div><label>Assumed plant rate ({window.productionUnit})<input type="number" min="0" step="0.1" value={plannedRate} placeholder={metrics.currentRate?.toFixed(2) ?? 'Unavailable'} onChange={(event) => setPlannedRate(event.target.value)} /></label><div><strong>{formatted(metrics.forecastLow, 'GJ')}–{formatted(metrics.forecastHigh, 'GJ')}</strong><p>±10% planning range, not a statistical interval. Default rate: latest daily mean; adjust for the operating plan.</p></div></section>

    <aside className="portfolio-output-context" aria-label="Plant performance insight"><span className="portfolio-section-kicker">Performance insight</span><p>{performanceInsight(selectedPlant, metrics.currentRate, metrics.referenceRate, window.productionUnit)} <small>{zcuSource ? 'Reference: 1–7 Apr observed mean, screening context only.' : 'Reference: 24 Apr scenario daily mean.'}</small></p></aside>

    <div className="portfolio-section-heading"><span>02 · Operating exceptions</span><p>Locate equipment exposure and follow-up gaps.</p></div>
    <div className="portfolio-dashboard portfolio-performance-grid">
      <ChartCard eyebrow="Equipment condition" title="Assets needing attention" value={`${attention.at(-1)} / ${overview.assetCount}`} note={`Current attention flags among monitored assets.${zcuSource ? ' Click 30 Apr to open KO-3201.' : ''}`}>
        <DailyBars values={attention} days={window.days} label="Assets needing attention by day" kind="condition" drilldown={zcuSource ? { day: '30 Apr', asset: 'KO-3201', onClick: () => onNavigate('overview') } : undefined} />
      </ChartCard>

      <ChartCard eyebrow="Equipment availability" title="Monitored equipment downtime" value={`${downtime.reduce((sum, value) => sum + value, 0)} h`} note={`Equipment-hours in the selected window, not plant outage duration.${zcuSource ? ' KO-3201 event: 32 h total.' : ''}`}>
        <DailyBars values={downtime} days={window.days} label="Monitored equipment downtime hours by day" kind="downtime" />
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
