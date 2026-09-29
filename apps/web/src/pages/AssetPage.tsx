import { useState } from 'react';

import { SignalChart } from '../components/SignalChart';
import { TraceButton } from '../components/TraceabilityContext';
import { ErrorState, LoadingState } from '../components/ViewState';
import { api } from '../lib/api';
import { PRIMARY_ASSET_ID } from '../lib/appConfig';
import { formatDate, formatSignal, humanize } from '../lib/format';
import { useApiResource } from '../lib/useApiResource';
import { Metric, ViewHeader } from './ProblemTankPage';

async function loadAsset() {
  const [overview, telemetry] = await Promise.all([api.assetOverview(PRIMARY_ASSET_ID), api.telemetry(PRIMARY_ASSET_ID, 720)]);
  return { overview, telemetry };
}

export function AssetPage() {
  const [view, setView] = useState<'condition' | 'operating'>('condition');
  const resource = useApiResource(PRIMARY_ASSET_ID, loadAsset);
  if (resource.loading) return <LoadingState/>;
  if (resource.error || !resource.data) return <ErrorState message={resource.error ?? 'No asset data returned'}/>;
  const { overview, telemetry } = resource.data;
  const latest = telemetry.points.at(-1)!;
  const impact = overview.production_impact;

  return <div className="product-view asset-performance-view">
    <ViewHeader eyebrow={`${overview.asset.plant_name} · ${overview.asset.equipment_family}`} title={`${overview.asset.tag} asset performance`} description={`${overview.asset.name}. Condition and operating behaviour from ${formatDate(overview.timeline_start)} to ${formatDate(overview.timeline_end)}.`}/>
    <div className="summary-strip"><Metric label="Current state" value={humanize(overview.latest_decision_state)}/><Metric label="Hourly records" value={telemetry.total_points.toLocaleString()}/><Metric label="Estimated incident shortfall" value={impact ? `${Math.round(impact.estimated_shortfall_tonnes).toLocaleString()} tonnes` : '—'}/><Metric label="Offline time" value={impact ? `${formatSignal(impact.offline_hours)} h` : '—'}/></div>
    <nav className="asset-performance-tabs" aria-label="Asset performance data"><button className={view === 'condition' ? 'active' : ''} aria-current={view === 'condition' ? 'page' : undefined} onClick={() => setView('condition')}>Equipment condition</button><button className={view === 'operating' ? 'active' : ''} aria-current={view === 'operating' ? 'page' : undefined} onClick={() => setView('operating')}>Operating & production</button></nav>
    {view === 'operating' && <div className="asset-production-context"><p>KO-3201 feed is the asset throughput signal. Plant rate provides operating context, not compressor output.</p><TraceButton traceId="production-shortfall">View shortfall calculation</TraceButton></div>}
    {view === 'condition' ? <div className="chart-grid asset-condition-grid">
      <SignalPanel title="Anomaly score" value={formatSignal(latest.anomaly_score ?? 0)}><SignalChart points={telemetry.points} field="anomaly_score" threshold={latest.anomaly_threshold}/></SignalPanel>
      <SignalPanel title="Radial vibration" value={`${formatSignal(latest.radial_vibration_micron)} µm`}><SignalChart points={telemetry.points} field="radial_vibration_micron"/></SignalPanel>
      <SignalPanel title="Water in oil" value={`${formatSignal(latest.water_in_oil_ppm)} ppm`}><SignalChart points={telemetry.points} field="water_in_oil_ppm"/></SignalPanel>
      <SignalPanel title="Lube oil pressure" value={`${formatSignal(latest.lube_oil_pressure_barg)} barg`}><SignalChart points={telemetry.points} field="lube_oil_pressure_barg"/></SignalPanel>
      <SignalPanel title="Bearing temperature" value={`${formatSignal(latest.bearing_metal_temperature_degc)} °C`}><SignalChart points={telemetry.points} field="bearing_metal_temperature_degc"/></SignalPanel>
    </div> : <div className="chart-grid">
      <SignalPanel title="KO-3201 feed rate" value={`${formatSignal(latest.feed_rate_tph)} t/h`}><SignalChart points={telemetry.points} field="feed_rate_tph" showRunStatus/></SignalPanel>
      <SignalPanel title="Discharge pressure" value={`${formatSignal(latest.discharge_pressure_barg)} barg`}><SignalChart points={telemetry.points} field="discharge_pressure_barg"/></SignalPanel>
      <SignalPanel title="Motor current" value={`${formatSignal(latest.motor_current_a)} A`}><SignalChart points={telemetry.points} field="motor_current_a"/></SignalPanel>
      <SignalPanel title="Plant rate · context" value={`${formatSignal(latest.plant_rate_tph)} t/h`}><SignalChart points={telemetry.points} field="plant_rate_tph"/></SignalPanel>
    </div>}
  </div>;
}

function SignalPanel({ title, value, children }: { title: string; value: string; children: React.ReactNode }) {
  return <article className="chart-panel panel"><header><span>{title}</span><strong>{value}</strong></header>{children}</article>;
}
