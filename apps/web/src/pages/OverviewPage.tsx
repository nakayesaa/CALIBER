import { CompressorIllustration } from '../components/CompressorIllustration';
import { ErrorState, LoadingState } from '../components/ViewState';
import { Icon } from '../components/Icon';
import { api, type AlertDetail, type AlertEvent, type AssetOverview, type TelemetrySeries } from '../lib/api';
import { formatDate, formatDateTime, formatSignal, humanize } from '../lib/format';
import { rcaForAlert } from '../lib/demoWorkflow';
import { useApiResource } from '../lib/useApiResource';
import type { PageId } from '../components/AppShell';

const ASSET_ID = 'asset-ko-3201';

interface OverviewData {
  overview: AssetOverview;
  telemetry: TelemetrySeries;
  alerts: AlertEvent[];
  detail: AlertDetail | null;
}

async function loadOverview(): Promise<OverviewData> {
  const [overview, telemetry, alerts] = await Promise.all([
    api.assetOverview(ASSET_ID),
    api.telemetry(ASSET_ID, 480),
    api.alerts(ASSET_ID),
  ]);
  const detail = alerts[0] ? await api.alertDetail(alerts[0].alert_id) : null;
  return { overview, telemetry, alerts, detail };
}

export function OverviewPage({ onNavigate }: { onNavigate: (page: PageId) => void }) {
  const resource = useApiResource('overview', loadOverview);
  if (resource.loading) return <LoadingState/>;
  if (resource.error || !resource.data) return <ErrorState message={resource.error ?? 'No overview data returned'}/>;

  const { overview, telemetry, alerts, detail } = resource.data;
  const alert = alerts[0];
  const rca = detail && rcaForAlert(detail.alert.alert_id, detail.rca);
  const weekly = sampleBuckets(telemetry.points, 5);
  const maxVibration = Math.max(...weekly.map((point) => point.radial_vibration_micron), 1);
  const latest = telemetry.points.at(-1);
  const peak = alert?.peak_anomaly_score ?? Math.max(...telemetry.points.map((point) => point.anomaly_score ?? 0));
  const signalValues = detail?.opening_snapshot.top_drivers?.slice(0, 4) ?? [];

  return (
    <section className="dashboard-grid">
      <article className="health-card panel">
        <div className="panel-head"><div className="title-group"><span className="title-icon"><Icon name="pulse"/></span><h1>Health trajectory</h1></div><span className="soft-select">Full case window</span></div>
        <div className="divider"/>
        <button className="asset-picker" onClick={() => onNavigate('assets')}><span>{overview.asset.tag} · {overview.asset.name}</span><i><Icon name="arrow"/></i></button>
        <div className="health-visual">
          <div className="bar-chart" aria-label="Sampled vibration trend">
            <div className="threshold-line"><span>case trajectory</span></div>
            {weekly.map((point, index) => (
              <div className={`bar-column${point.is_anomaly ? ' incident' : ''}`} key={point.timestamp}>
                <div className="bar" style={{ height: `${Math.max(20, point.radial_vibration_micron / maxVibration * 100)}%` }}>
                  {index === weekly.length - 1 && <span className="bar-label">{formatSignal(point.radial_vibration_micron)} µm</span>}
                  <span/>
                </div>
                <small>{formatDate(point.timestamp, { day: '2-digit', month: 'short', year: undefined })}</small>
              </div>
            ))}
          </div>
          <div className="machine-wrap"><div className="machine-status"><span/>{humanize(overview.latest_decision_state)}</div><CompressorIllustration/></div>
        </div>
        <div className="headline-metric"><strong>{alert ? Math.round(alert.duration_hours / 24) : 0}<span> days</span></strong><p>grouped alert<br/>window</p></div>
        <div className="evidence-pill"><i/><span>{alert?.breached_signals.length ?? 0} signals breached</span><b>{formatSignal(peak)} peak score</b></div>
      </article>

      <section className="timeline-panel">
        <div className="section-heading"><h2>Event timeline</h2><button onClick={() => onNavigate('rca')}>View RCA <Icon name="arrow"/></button></div>
        <div className="timeline overview-timeline">
          {alert ? <>
            <div className="time-mark"><span>{formatDate(alert.opened_at)}</span></div>
            <article className="event-card expanded"><div className="event-toggle"><div><h3>Alert opened</h3><p>{humanize(alert.primary_driver)} became persistent.</p></div><span><Icon name="alert"/></span></div><div className="event-detail"><div className="event-chips"><b className="warning">Warning</b><em>{formatSignal(alert.peak_anomaly_score)} peak</em></div><p className="location">{formatDateTime(alert.opened_at)}</p></div></article>
            <div className="now-line"><b>{humanize(alert.highest_severity)}</b><span/></div>
            <article className="event-card compact"><div className="event-toggle"><div><h3>Highest severity reached</h3><p>{alert.breached_signals.length} condition signals contributed.</p></div><span><Icon name="pulse"/></span></div></article>
            <div className="time-mark later"><span>{formatDate(alert.closed_at ?? alert.peak_score_at)}</span></div>
            <article className="event-card compact muted-event"><div className="event-toggle"><div><h3>{alert.closed_at ? 'Alert closed' : 'Monitoring continues'}</h3><p>{alert.closed_at ? humanize(alert.status) : 'Current case remains open.'}</p></div><span><Icon name="check"/></span></div></article>
          </> : <p className="timeline-empty">No grouped alerts in this window.</p>}
        </div>
      </section>

      <section className="response-card">
        <div className="section-heading"><h2>Decision workflow</h2><button onClick={() => onNavigate('actions')}>Open tracker <Icon name="arrow"/></button></div>
        <WorkflowRow initials="AD" title="Anomaly detection" detail={`${telemetry.total_points.toLocaleString()} hourly decisions`} progress={100}/>
        <WorkflowRow initials="RC" title="RCA review" detail={rca ? humanize(rca.status) : 'Awaiting AI draft'} progress={rca?.status === 'APPROVED' ? 100 : rca ? 60 : 25}/>
      </section>

      <article className="signal-card">
        <div className="signal-head"><div><h2>Signal evidence <sup>MODEL</sup></h2><p>{signalValues.length || alert?.breached_signals.length || 0} leading condition signals</p></div></div>
        <div className="driver-list">
          {(signalValues.length ? signalValues : (alert?.breached_signals ?? []).map((name) => ({ name, score: 0 }))).map((driver) => <div key={driver.name}><span>{humanize(driver.name)}</span><b>{driver.score ? formatSignal(driver.score) : 'breached'}</b></div>)}
          {!signalValues.length && !alert?.breached_signals.length && <p>No active signal evidence</p>}
        </div>
      </article>

      <article className="exposure-card">
        <div className="exposure-head"><div className="title-group"><span className="title-icon orange"><Icon name="alert"/></span><h2>Alert exposure</h2></div><span className="severity-chip">{alert?.highest_severity ?? 'None'}</span></div>
        <div className="risk-chart" aria-hidden="true">{[36, 54, 41, 68, 74, 58, 95, 62, 78, 48].map((height, index) => <span key={index} style={{ left: `${2 + index * 10}%`, height: `${height}%` }} className={index === 6 ? 'selected' : ''}/>)}</div>
        <div className="exposure-foot"><strong>{formatSignal(peak)}</strong><div><b>{alert ? `${Math.round(alert.duration_hours).toLocaleString()} hours` : 'No event'}</b><span>peak anomaly score</span></div></div>
        {latest && <p className="card-caption">Latest state: {humanize(latest.decision_state)}</p>}
      </article>
    </section>
  );
}

function WorkflowRow({ initials, title, detail, progress }: { initials: string; title: string; detail: string; progress: number }) {
  return <div className="person-row"><div className="avatar avatar-one">{initials}</div><strong>{title}</strong><span>{detail}</span><div className="progress"><i style={{ width: `${progress}%` }}/></div><b>{progress}%</b></div>;
}

function sampleBuckets(points: TelemetrySeries['points'], count: number) {
  if (points.length <= count) return points;
  return Array.from({ length: count }, (_, index) => {
    const bucket = points.slice(
      Math.floor(index * points.length / count),
      Math.floor((index + 1) * points.length / count),
    );
    return bucket.reduce((peak, point) => point.radial_vibration_micron > peak.radial_vibration_micron ? point : peak);
  });
}
