import { SignalChart } from '../components/SignalChart';
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
  const resource = useApiResource(PRIMARY_ASSET_ID, loadAsset);
  if (resource.loading) return <LoadingState/>;
  if (resource.error || !resource.data) return <ErrorState message={resource.error ?? 'No asset data returned'}/>;
  const { overview, telemetry } = resource.data;
  const latest = telemetry.points.at(-1)!;
  const peakVibration = Math.max(...telemetry.points.map((point) => point.radial_vibration_micron));

  return <div className="product-view">
    <ViewHeader eyebrow={`${overview.asset.plant_name} · ${overview.asset.equipment_family}`} title={`${overview.asset.tag} asset health`} description={`${overview.asset.name}. Condition model evidence across the complete case timeline.`}/>
    <div className="summary-strip"><Metric label="Current state" value={humanize(overview.latest_decision_state)}/><Metric label="Hourly records" value={telemetry.total_points.toLocaleString()}/><Metric label="Peak vibration" value={`${formatSignal(peakVibration)} µm`}/><Metric label="Case range" value={`${formatDate(overview.timeline_start)} to ${formatDate(overview.timeline_end)}`}/></div>
    <div className="chart-grid">
      <SignalPanel title="Anomaly score" value={formatSignal(latest.anomaly_score ?? 0)}><SignalChart points={telemetry.points} field="anomaly_score" threshold={latest.anomaly_threshold}/></SignalPanel>
      <SignalPanel title="Radial vibration" value={`${formatSignal(latest.radial_vibration_micron)} µm`}><SignalChart points={telemetry.points} field="radial_vibration_micron"/></SignalPanel>
      <SignalPanel title="Water in oil" value={`${formatSignal(latest.water_in_oil_ppm)} ppm`}><SignalChart points={telemetry.points} field="water_in_oil_ppm"/></SignalPanel>
      <SignalPanel title="Lube oil pressure" value={`${formatSignal(latest.lube_oil_pressure_barg)} barg`}><SignalChart points={telemetry.points} field="lube_oil_pressure_barg"/></SignalPanel>
    </div>
  </div>;
}

function SignalPanel({ title, value, children }: { title: string; value: string; children: React.ReactNode }) {
  return <article className="chart-panel panel"><header><span>{title}</span><strong>{value}</strong></header>{children}</article>;
}
