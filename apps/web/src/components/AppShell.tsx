import type { ReactNode } from 'react';
import { Icon, type IconName } from './Icon';

export type PageId = 'overview' | 'problems' | 'assets' | 'rca' | 'actions' | 'data';

const navigation: Array<{ id: PageId; label: string; icon: IconName }> = [
  { id: 'overview', label: 'Overview', icon: 'home' },
  { id: 'problems', label: 'Problem tank', icon: 'alert' },
  { id: 'assets', label: 'Asset health', icon: 'trend' },
  { id: 'rca', label: 'RCA workspace', icon: 'spark' },
  { id: 'actions', label: 'Action tracker', icon: 'tasks' },
  { id: 'data', label: 'Data foundation', icon: 'database' },
];

interface AppShellProps {
  activePage: PageId;
  onNavigate: (page: PageId) => void;
  children: ReactNode;
}

export function AppShell({ activePage, onNavigate, children }: AppShellProps) {
  const activeLabel = navigation.find(({ id }) => id === activePage)?.label ?? 'Overview';

  return (
    <main className="page">
      <section className="app-shell">
        <aside className="rail">
          <button className="brand" aria-label="CALIBER home" onClick={() => onNavigate('overview')}><span/><span/></button>
          <nav aria-label="Primary navigation">
            {navigation.map((item) => (
              <button
                key={item.id}
                className={`nav-btn${activePage === item.id ? ' active' : ''}`}
                aria-label={item.label}
                title={item.label}
                onClick={() => onNavigate(item.id)}
              >
                <Icon name={item.icon}/>
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
          <div className="workspace-scroll">
            {children}
            <a className="icon-credit" href="https://thenounproject.com/adisena/" target="_blank" rel="noreferrer">Icons by adi_sena, Noun Project · CC BY 3.0</a>
          </div>
        </div>
      </section>
    </main>
  );
}
