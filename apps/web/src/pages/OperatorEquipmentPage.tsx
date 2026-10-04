import { useState } from 'react';
import { EquipmentOperatorEvidence } from '../components/EquipmentOperatorEvidence';
import { LoadingState } from '../components/ViewState';
import { api, selectWorkflowSession } from '../lib/api';
import { orderedEquipmentRequests, scopeReportLink } from '../lib/equipmentReview';
import { formatDate, humanize } from '../lib/format';
import { useApiResource } from '../lib/useApiResource';
import '../production-review.css';
import '../equipment-operator.css';

export function OperatorEquipmentPage({ personId, assetId }: { personId?: string; assetId?: string }) {
  const resource = useApiResource(`operator-equipment:${personId ?? 'demo-equipment-ko'}`, async () => {
    const session = await selectWorkflowSession(personId ?? 'demo-equipment-ko');
    const [assets, requests] = await Promise.all([api.equipmentMonitoring(), api.equipmentReports()]);
    return { session, assets, requests: orderedEquipmentRequests(requests) };
  });
  const [tab, setTab] = useState<'monitoring' | 'requests'>('monitoring');
  const [selectedAsset, setSelectedAsset] = useState(assetId ?? '');
  const scopedAsset = resource.data?.assets.find((item) => item.asset.asset_id === selectedAsset) ?? resource.data?.assets[0];
  const evidence = useApiResource(`operator-condition:${scopedAsset?.asset.asset_id ?? ''}:${personId ?? ''}`, () => scopedAsset ? api.operatorEquipmentEvidence(scopedAsset.asset.asset_id) : Promise.resolve(null));
  if (!resource.data) return resource.loading ? <LoadingState/> : <div className="production-review-error"><h1>Equipment workspace unavailable</h1><p role="alert">{resource.error}</p><button onClick={resource.reload}>Retry</button></div>;
  const { session, assets, requests } = resource.data;
  const pending = requests.filter((report) => report.status === 'SENT');
  const overdue = pending.filter((report) => Date.parse(report.due_at) < Date.now());
  return <div className="decision-workspace equipment-operator-page">
    <header className="decision-workspace-heading"><div><span>Equipment performance operator · {session.current.plant_ids.join(', ')}</span><h1>Equipment workspace</h1><p>Your assigned condition monitoring and evidence verification, in one place.</p></div><span>{session.current.display_name}</span></header>
    <section className="operator-scope-brief" aria-label="Assigned equipment scope"><div><span>Assigned scope</span><strong>{assets.length ? assets.map((item) => item.asset.tag).join(' · ') : 'No assigned equipment'}</strong><p>Equipment evidence only. No production approval or maintenance authorization.</p></div><div><strong>{pending.length}</strong><span>Awaiting your review</span></div><div><strong>{overdue.length}</strong><span>Overdue requests</span></div></section>
    <nav className="operator-workspace-tabs" aria-label="Equipment workspace sections"><button className={tab === 'monitoring' ? 'active' : ''} aria-pressed={tab === 'monitoring'} onClick={() => setTab('monitoring')}>Equipment monitoring</button><button className={tab === 'requests' ? 'active' : ''} aria-pressed={tab === 'requests'} onClick={() => setTab('requests')}>Verification inbox <span>{pending.length}</span></button><button disabled={resource.loading} onClick={() => { resource.reload(); evidence.reload(); }}>Refresh</button></nav>
    {tab === 'monitoring' ? <>
      {scopedAsset && <section className="operator-asset-context"><label>Assigned equipment<select aria-label="Assigned equipment" value={scopedAsset.asset.asset_id} onChange={(event) => setSelectedAsset(event.target.value)}>{assets.map((item) => <option value={item.asset.asset_id} key={item.asset.asset_id}>{item.asset.tag} · {item.asset.name}</option>)}</select></label><div><span>Recorded timeline</span><strong>{formatDate(scopedAsset.timeline_start)} → {formatDate(scopedAsset.timeline_end)}</strong></div><div><span>Last recorded state</span><strong>{humanize(scopedAsset.latest_decision_state)}</strong></div></section>}
      {!assets.length ? <section className="production-review-card"><h2>No equipment assigned</h2><p>A supervisor must assign your asset scope before condition records appear here.</p></section> : evidence.loading ? <LoadingState/> : evidence.error ? <section className="production-review-card"><h2>Condition evidence unavailable</h2><p role="alert">{evidence.error}</p><button onClick={evidence.reload}>Retry evidence</button></section> : evidence.data && <EquipmentOperatorEvidence evidence={evidence.data}/>}
    </> : <section className="production-review-card production-delegation-list"><header><div><span>Your equipment requests</span><h2>Verification inbox</h2></div></header>{!requests.length ? <p>No reports assigned yet. Monitoring remains available while you wait for a supervisor request.</p> : <ul>{requests.map((report) => <li key={report.report_id}><div><strong>{report.asset.tag} · Equipment verification</strong><p>{report.supervisor} · {report.evidence.alert.highest_severity} · v{report.version}</p><p>Due {formatDate(report.due_at, { hour: '2-digit', minute: '2-digit', timeZone: 'Asia/Jakarta' })} WIB{report.status === 'SENT' && Date.parse(report.due_at) < Date.now() ? ' · Overdue' : ''}</p></div><span className={`production-request-status ${report.status.toLowerCase()}`}>{report.status === 'APPROVED' ? 'Verified' : humanize(report.status)}</span><a href={scopeReportLink(report, session.current.person_id)}>Open report</a></li>)}</ul>}</section>}
  </div>;
}
