import { api } from '../lib/api';
import { equipmentCatalog } from '../lib/equipment';
import { useApiResource } from '../lib/useApiResource';
import { formatDate, humanize } from '../lib/format';
import { ErrorState, LoadingState } from '../components/ViewState';

export function EquipmentIndexPage({ onSelect }: { onSelect: (assetId: string) => void }) {
  const resource = useApiResource('equipment-index', async () => {
    const assets = await api.assets();
    return Promise.all(assets.map(async (asset) => ({ asset, overview: await api.assetOverview(asset.asset_id) })));
  });
  if (resource.loading) return <LoadingState/>;
  if (resource.error || !resource.data) return <ErrorState message={resource.error ?? 'Equipment coverage unavailable'}/>;
  return <div className="overview-dashboard equipment-dashboard"><header className="overview-heading"><div><p>Asset performance</p><h1>Equipment investigation</h1></div><span>Five case assets · four plants</span></header>
    <section className="equipment-card"><header><h2>Select equipment</h2><p>Open the condition, investigation, RCA and action journey for an integrated asset.</p></header>
      <div className="equipment-index-list">{equipmentCatalog.map((entry) => {
        const record = resource.data!.find(({ asset }) => asset.tag === entry.tag);
        return <button className="equipment-index-row" key={entry.tag} disabled={!record} onClick={() => record && onSelect(record.asset.asset_id)}>
          <span className="equipment-index-plant">{entry.plant}</span><span><strong>{entry.tag}</strong><span>{record?.asset.name ?? entry.name}</span></span>
          <span>{record ? `${formatDate(record.overview.timeline_start)} – ${formatDate(record.overview.timeline_end)}` : 'Data integration pending'}</span>
          <span className="equipment-status">{record ? humanize(record.overview.latest_decision_state) : 'Source known'}</span><span>{record ? `${record.overview.alert_count} alert${record.overview.alert_count === 1 ? '' : 's'} →` : 'Pending'}</span>
        </button>;
      })}</div>
    </section>
  </div>;
}
