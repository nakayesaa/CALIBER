import type { ReactNode } from 'react';
import { Icon } from './Icon';
import { SidebarIcon, type SidebarIconName } from './SidebarIcon';
import { SourceInspector } from './SourceInspector';
import { useTraceability } from './TraceabilityContext';
import { equipmentCatalog } from '../lib/equipment';

export type PageId = 'overview' | 'plant' | 'problems' | 'investigation' | 'assets' | 'rca' | 'rca-investigation' | 'actions' | 'data';

const navigation: Array<{ id: PageId; label: string; icon: SidebarIconName }> = [
  { id: 'plant', label: 'Manufacturing overview', icon: 'home' },
  { id: 'assets', label: 'Equipment investigation', icon: 'plant' },
  { id: 'problems', label: 'Problem tank', icon: 'problem' },
  { id: 'rca', label: 'RCA workspace', icon: 'rca' },
  { id: 'actions', label: 'Action tracker', icon: 'action' },
  { id: 'data', label: 'Data foundation', icon: 'data' },
];

interface AppShellProps {
  activePage: PageId;
  assetId: string;
  onNavigate: (page: PageId) => void;
  children: ReactNode;
}

export function AppShell({ activePage, assetId, onNavigate, children }: AppShellProps) {
  const { target } = useTraceability();
  const equipment = equipmentCatalog.find((asset) => `asset-${asset.tag.toLowerCase()}` === assetId);
  const activeLabel = activePage === 'overview' ? `${equipment?.tag ?? 'Equipment'} overview` : activePage === 'investigation'
    ? 'Problem investigation'
    : activePage === 'rca-investigation'
      ? 'RCA investigation'
    : navigation.find(({ id }) => id === activePage)?.label ?? 'Overview';

  return (
    <main className="page">
      <section className={`app-shell${target ? ' trace-open' : ''}`}>
        <aside className="rail">
          <button className="brand" aria-label="CALIBER home" onClick={() => onNavigate('plant')}><span/><span/></button>
          <nav aria-label="Primary navigation">
            {navigation.map((item) => (
              <button
                key={item.id}
                className={`nav-btn${activePage === item.id || (activePage === 'overview' && item.id === 'assets') || (activePage === 'investigation' && item.id === 'problems') || (activePage === 'rca-investigation' && item.id === 'rca') ? ' active' : ''}`}
                aria-label={item.label}
                title={item.label}
                onClick={() => onNavigate(item.id)}
              >
                <SidebarIcon name={item.icon}/>
              </button>
            ))}
          </nav>
          <div className="rail-bottom"><div className="avatar avatar-small">NA</div></div>
        </aside>

        <div className="workspace">
          <header className="topbar">
            <div className="breadcrumbs"><span>Reliability ops</span><b>/</b><span>{activePage === 'plant' || activePage === 'assets' ? 'Manufacturing' : equipment?.plant ?? 'Equipment'}</span><b>/</b><strong>{activeLabel}</strong></div>
            <div className="top-actions">
              <label className="search"><Icon name="search"/><input placeholder="Search asset, incident, or owner"/></label>
              <button className="round-button notification" aria-label="Notifications"><Icon name="inbox"/><i/></button>
            </div>
          </header>
          <div key={activePage} className={`workspace-scroll${activePage === 'investigation' ? ' investigation-scroll' : ''}`}>
            {children}
          </div>
        </div>
        <SourceInspector/>
      </section>
    </main>
  );
}
