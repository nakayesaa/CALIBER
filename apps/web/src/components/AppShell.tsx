import type { ReactNode } from 'react';
import { Icon } from './Icon';
import { SidebarIcon, type SidebarIconName } from './SidebarIcon';
import { SourceInspector } from './SourceInspector';
import { useTraceability } from './TraceabilityContext';
import { equipmentCatalog } from '../lib/equipment';
import type { WorkflowSession } from '../lib/apiContracts';
import './workspace-role.css';

export type PageId = 'overview' | 'plant' | 'problems' | 'investigation' | 'assets' | 'rca' | 'rca-investigation' | 'actions' | 'data' | 'production-review' | 'delegation' | 'operator-equipment' | 'equipment-review' | 'gm-review' | 'assigned-actions';

const navigation: Array<{ id: PageId; label: string; icon: SidebarIconName }> = [
  { id: 'plant', label: 'Manufacturing overview', icon: 'home' },
  { id: 'assets', label: 'Equipment investigation', icon: 'plant' },
  { id: 'problems', label: 'Problem tank', icon: 'problem' },
  { id: 'rca', label: 'RCA workspace', icon: 'rca' },
  { id: 'actions', label: 'Action tracker', icon: 'action' },
  { id: 'delegation', label: 'Scope verification', icon: 'problem' },
  { id: 'operator-equipment', label: 'Operator workspace', icon: 'plant' },
  { id: 'gm-review', label: 'GM review inbox', icon: 'problem' },
  { id: 'assigned-actions', label: 'My assigned actions', icon: 'action' },
  { id: 'data', label: 'Data foundation', icon: 'data' },
];

interface AppShellProps {
  activePage: PageId;
  assetId: string;
  onNavigate: (page: PageId) => void;
  children: ReactNode;
  session: WorkflowSession;
  onSwitchRole: (personId: string, page: PageId, assetId: string) => void;
}

export function AppShell({ activePage, assetId, onNavigate, children, session, onSwitchRole }: AppShellProps) {
  const { target } = useTraceability();
  const equipment = equipmentCatalog.find((asset) => `asset-${asset.tag.toLowerCase()}` === assetId);
  const operatorMode = ['OPERATOR', 'ENGINEER'].includes(session.current.role);
  const workspaceRole = operatorMode ? 'OPERATOR' : session.current.role;
  const productionOperator = operatorMode && session.current.scopes.includes('PRODUCTION');
  const home: PageId = operatorMode ? session.current.role === 'ENGINEER' ? 'assigned-actions' : productionOperator ? 'delegation' : 'operator-equipment' : session.current.role === 'MANAGER' ? 'gm-review' : 'plant';
  const visibleNavigation = navigation.filter((item) => operatorMode
    ? item.id === home || item.id === 'assigned-actions'
    : session.current.role === 'MANAGER' ? ['plant', 'gm-review', 'actions'].includes(item.id) : !['operator-equipment', 'gm-review', 'assigned-actions'].includes(item.id));
  const roles = [
    { role: 'OPERATOR', label: 'Operator', detail: 'Assigned equipment and evidence verification', person: assetId === 'asset-he-3301' ? 'demo-equipment-he' : 'demo-equipment-ko', page: 'operator-equipment' as PageId },
    { role: 'SUPERVISOR', label: 'Supervisor', detail: 'Monitor, review and delegate across scopes', person: 'demo-supervisor', page: 'plant' as PageId },
    { role: 'MANAGER', label: 'General Manager', detail: 'Review verified cases and record decisions', person: 'demo-manager', page: 'gm-review' as PageId },
  ];
  const activeLabel = activePage === 'overview' ? `${equipment?.tag ?? 'Equipment'} overview` : activePage === 'investigation'
    ? 'Problem investigation'
    : activePage === 'rca-investigation'
      ? 'RCA investigation'
    : activePage === 'production-review' ? 'Production evidence review'
    : activePage === 'equipment-review' ? 'Equipment evidence review'
    : navigation.find(({ id }) => id === activePage)?.label ?? 'Overview';

  return (
    <main className="page">
      <section className={`app-shell${target ? ' trace-open' : ''}`}>
        <aside className="rail">
          <button className="brand" aria-label="CALIBER home" onClick={() => onNavigate(home)}><span/><span/></button>
          <nav aria-label="Primary navigation">
            {visibleNavigation.map((item) => (
              <button
                key={item.id}
                data-flow={item.id === 'problems' ? 'problems-nav' : undefined}
                className={`nav-btn${activePage === item.id || (activePage === 'overview' && item.id === 'assets') || (activePage === 'investigation' && item.id === 'problems') || (activePage === 'rca-investigation' && item.id === 'rca') || (activePage === 'equipment-review' && item.id === 'operator-equipment') ? ' active' : ''}`}
                aria-label={item.label}
                title={item.label}
                onClick={() => onNavigate(item.id)}
              >
                <SidebarIcon name={item.icon}/>
              </button>
            ))}
          </nav>
          <div className="rail-bottom">
            <button className="avatar avatar-small workspace-role-trigger" popoverTarget="workflow-role-menu" aria-label="Switch workspace role" title={roles.find((item) => item.role === workspaceRole)?.label ?? session.current.role}>NA</button>
            <div id="workflow-role-menu" className="workspace-role-menu" popover="auto">
              <header><span>Workspace role</span><strong>{session.current.display_name}</strong></header>
              {session.can_switch ? roles.map((item) => <button key={item.role} aria-label={item.label} aria-pressed={workspaceRole === item.role} onClick={(event) => {
                event.currentTarget.closest<HTMLElement>('[popover]')?.hidePopover();
                onSwitchRole(workspaceRole === item.role ? session.current.person_id : item.person,
                  workspaceRole === item.role ? home : item.page,
                  workspaceRole === item.role && session.current.asset_ids.length ? session.current.asset_ids[0] : assetId === 'asset-he-3301' ? assetId : 'asset-ko-3201');
              }}><strong>{item.label}</strong><span>{item.detail}</span></button>) : <p>Role is assigned by your current session.</p>}
            </div>
          </div>
        </aside>

        <div className="workspace">
          <header className="topbar">
            <div className="breadcrumbs"><span>{roles.find((item) => item.role === workspaceRole)?.label ?? 'Reliability ops'}</span><b>/</b><span>{activePage === 'plant' || activePage === 'assets' ? 'Manufacturing' : equipment?.plant ?? 'Equipment'}</span><b>/</b><strong>{activeLabel}</strong></div>
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
