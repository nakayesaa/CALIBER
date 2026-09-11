import type { ReactNode } from 'react';
import { Icon } from './Icon';
import { SidebarIcon, type SidebarIconName } from './SidebarIcon';

export type PageId = 'overview' | 'problems' | 'investigation' | 'assets' | 'rca' | 'actions' | 'data';

const navigation: Array<{ id: PageId; label: string; icon: SidebarIconName }> = [
  { id: 'overview', label: 'Overview', icon: 'home' },
  { id: 'problems', label: 'Problem tank', icon: 'problem' },
  { id: 'assets', label: 'Asset health', icon: 'asset' },
  { id: 'rca', label: 'RCA workspace', icon: 'rca' },
  { id: 'actions', label: 'Action tracker', icon: 'action' },
  { id: 'data', label: 'Data foundation', icon: 'data' },
];

interface AppShellProps {
  activePage: PageId;
  onNavigate: (page: PageId) => void;
  children: ReactNode;
}

export function AppShell({ activePage, onNavigate, children }: AppShellProps) {
  const activeLabel = activePage === 'investigation'
    ? 'Problem investigation'
    : navigation.find(({ id }) => id === activePage)?.label ?? 'Overview';

  return (
    <main className="page">
      <section className="app-shell">
        <aside className="rail">
          <button className="brand" aria-label="CALIBER home" onClick={() => onNavigate('overview')}><span/><span/></button>
          <nav aria-label="Primary navigation">
            {navigation.map((item) => (
              <button
                key={item.id}
                className={`nav-btn${activePage === item.id || (activePage === 'investigation' && item.id === 'problems') ? ' active' : ''}`}
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
            <div className="breadcrumbs"><span>Reliability ops</span><b>/</b><span>ZCU</span><b>/</b><strong>{activeLabel}</strong></div>
            <div className="top-actions">
              <label className="search"><Icon name="search"/><input placeholder="Search asset, incident, or owner"/></label>
              <button className="round-button notification" aria-label="Notifications"><Icon name="inbox"/><i/></button>
            </div>
          </header>
          <div className={`workspace-scroll${activePage === 'investigation' ? ' investigation-scroll' : ''}`}>
            {children}
          </div>
        </div>
      </section>
    </main>
  );
}
