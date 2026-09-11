import { useState } from 'react';
import type { PageId } from '../components/AppShell';
import { Icon } from '../components/Icon';
import { SignalChart } from '../components/SignalChart';
import { ErrorState, LoadingState } from '../components/ViewState';
import { api, type AlertDetail, type AlertEvent, type AssetOverview, type TelemetryPoint, type TelemetrySeries } from '../lib/api';
import { actionsForAlert, rcaForAlert } from '../lib/demoWorkflow';
import { formatDate, formatDateTime, formatSignal, humanize } from '../lib/format';
import { useApiResource } from '../lib/useApiResource';

const ASSET_ID = 'asset-ko-3201';

type SignalField = keyof Pick<TelemetryPoint,
  'radial_vibration_micron' | 'water_in_oil_ppm' | 'lube_oil_pressure_barg' |
  'bearing_metal_temperature_degc' | 'feed_rate_tph' | 'discharge_pressure_barg'>;

const signals: Array<{ field: SignalField; label: string; shortLabel: string; unit: string }> = [
  { field: 'water_in_oil_ppm', label: 'Water in oil', shortLabel: 'Oil moisture', unit: 'ppm' },
  { field: 'radial_vibration_micron', label: 'Radial vibration', shortLabel: 'Vibration', unit: 'µm' },
  { field: 'lube_oil_pressure_barg', label: 'Lube oil pressure', shortLabel: 'Oil pressure', unit: 'barg' },
  { field: 'bearing_metal_temperature_degc', label: 'Bearing temperature', shortLabel: 'Temperature', unit: '°C' },
  { field: 'feed_rate_tph', label: 'Feed rate', shortLabel: 'Feed rate', unit: 'tph' },
  { field: 'discharge_pressure_barg', label: 'Discharge pressure', shortLabel: 'Discharge', unit: 'barg' },
];

interface OverviewData {
  overview: AssetOverview;
  telemetry: TelemetrySeries;
  alerts: AlertEvent[];
  detail: AlertDetail | null;
}

async function loadOverview(): Promise<OverviewData> {
  const [overview, telemetry, alerts] = await Promise.all([
    api.assetOverview(ASSET_ID),
    api.telemetry(ASSET_ID, 720),
    api.alerts(ASSET_ID),
  ]);
  const detail = alerts[0] ? await api.alertDetail(alerts[0].alert_id) : null;
  return { overview, telemetry, alerts, detail };
}

export function OverviewPage({ onNavigate }: { onNavigate: (page: PageId) => void }) {
  const [selectedField, setSelectedField] = useState<SignalField>('water_in_oil_ppm');
  const resource = useApiResource('overview', loadOverview);
  if (resource.loading) return <LoadingState/>;
  if (resource.error || !resource.data) return <ErrorState message={resource.error ?? 'No overview data returned'}/>;

  const { overview, telemetry, alerts, detail } = resource.data;
  const alert = alerts[0];
  const latest = telemetry.points.at(-1)!;
  const selectedSignal = signals.find((signal) => signal.field === selectedField)!;
  const selectedValues = telemetry.points.map((point) => Number(point[selectedField]));
  const rca = detail && rcaForAlert(detail.alert.alert_id, detail.rca);
  const plans = detail ? actionsForAlert(detail.alert.alert_id, detail.action_plans, Boolean(detail.rca)) : [];
  const actions = plans.flatMap((plan) => plan.actions);

  return <div className="equipment-dashboard">
    <header className="equipment-heading">
      <div><h1>Equipment health</h1><button className="equipment-select" onClick={() => onNavigate('assets')}>{overview.asset.tag}<Icon name="arrow"/></button></div>
      <button className="dark-action" onClick={() => onNavigate('rca')}>Open RCA <Icon name="arrow"/></button>
    </header>

    <section className="equipment-top-grid">
      <article className="health-map panel">
        <div className="health-map-head"><div><span className="live-pill"><i/> Historical case</span><h2>Health trajectory</h2><p>Anomaly score across the six-month KO-3201 monitoring window</p></div><div className="peak-score"><span>Peak score</span><strong>{formatSignal(alert?.peak_anomaly_score ?? 0)}</strong></div></div>
        <div className="health-map-chart">
          <div className="trajectory-facts"><Fact label="First signal" value={formatDate(alert?.first_signal_at ?? overview.timeline_start)}/><Fact label="Alert window" value={`${formatSignal((alert?.duration_hours ?? 0) / 24)} days`}/><Fact label="Signals" value={String(alert?.breached_signals.length ?? 0)}/></div>
          <div className="health-chart-canvas"><SignalChart points={telemetry.points} field="anomaly_score" threshold={50}/><span className="threshold-label">Decision threshold 50</span><div className="peak-callout"><b>{humanize(alert?.highest_severity ?? 'normal')}</b><span>{formatDateTime(alert?.peak_score_at ?? overview.timeline_end)}</span></div></div>
          <div className="health-map-dates"><span>{formatDate(overview.timeline_start)}</span><span>{formatDate(overview.timeline_end)}</span></div>
        </div>
      </article>

      <article className="equipment-detail panel">
        <div className="overview-card-head"><div><p>Asset context</p><h2>Equipment details</h2></div><button onClick={() => onNavigate('assets')} aria-label="Open asset"><Icon name="arrow"/></button></div>
        <div className="equipment-mark"><span>{overview.asset.tag}</span><Icon name="pulse"/></div>
        <dl><Detail label="Equipment type" value={overview.asset.equipment_type}/><Detail label="Plant" value={overview.asset.plant_name}/><Detail label="Criticality" value={overview.asset.criticality}/><Detail label="Discipline" value={overview.asset.discipline}/><Detail label="Current state" value={humanize(overview.latest_decision_state)}/></dl>
        <div className="asset-monitor-note"><i/><span>Latest monitor</span><b>{formatDateTime(latest.timestamp)}</b></div>
      </article>
    </section>

    <section className="equipment-bottom-grid">
      <article className="signal-performance panel">
        <div className="overview-card-head"><div><p>Condition monitoring</p><h2>Signal performance</h2></div><span className="status-tag">Hourly</span></div>
        <div className="signal-workspace">
          <nav className="signal-selector" aria-label="Condition variables">{signals.map((signal) => <button key={signal.field} className={selectedField === signal.field ? 'active' : ''} onClick={() => setSelectedField(signal.field)}><span>{signal.shortLabel}</span><strong>{formatSignal(Number(latest[signal.field]))} <small>{signal.unit}</small></strong></button>)}</nav>
          <div className="selected-signal-chart">
            <header><div><span>{selectedSignal.label}</span><strong>{formatSignal(Number(latest[selectedField]))} <small>{selectedSignal.unit}</small></strong></div><div><span>Window peak</span><b>{formatSignal(Math.max(...selectedValues))} {selectedSignal.unit}</b></div></header>
            <SignalChart points={telemetry.points} field={selectedField}/>
            <div className="signal-chart-dates"><span>{formatDate(overview.timeline_start)}</span><span>{formatDate(overview.timeline_end)}</span></div>
          </div>
        </div>
      </article>

      <article className="event-tracker panel">
        <div className="overview-card-head"><div><p>Case progression</p><h2>Key events</h2></div><button onClick={() => onNavigate('problems')} aria-label="Open problem tank"><Icon name="arrow"/></button></div>
        {alert && <div className="compact-events">
          <CompactEvent tone="signal" status="Signal" time={formatDateTime(alert.first_signal_at)} title="Oil condition changed" detail="Water-in-oil became persistent."/>
          <CompactEvent tone="warning" status="Warning" time={formatDateTime(alert.opened_at)} title="Alert opened" detail={`${formatSignal(detail?.opening_snapshot.anomaly_score ?? 0)} anomaly score.`}/>
          <CompactEvent tone="critical" status="Critical" time={formatDateTime(alert.peak_score_at)} title="Signals converged" detail={`${alert.breached_signals.length} parameters supported escalation.`}/>
          <CompactEvent tone="closed" status="Response" time={formatDateTime(alert.closed_at ?? alert.peak_score_at)} title="RCA to CA/PA" detail={`${rca ? 'Cause approved' : 'RCA pending'} · ${actions.filter((action) => action.status === 'CLOSED').length}/${actions.length} actions closed.`}/>
        </div>}
      </article>
    </section>
  </div>;
}

function Fact({ label, value }: { label: string; value: string }) { return <div><span>{label}</span><strong>{value}</strong></div>; }
function Detail({ label, value }: { label: string; value: string }) { return <div><dt>{label}</dt><dd>{humanize(value)}</dd></div>; }
function CompactEvent({ tone, status, time, title, detail }: { tone: string; status: string; time: string; title: string; detail: string }) {
  return <div className={`compact-event ${tone}`}><span><Icon name={tone === 'closed' ? 'check' : tone === 'critical' ? 'alert' : 'pulse'}/></span><div><header><b>{status}</b><time>{time}</time></header><h3>{title}</h3><p>{detail}</p></div></div>;
}
