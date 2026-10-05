import { useEffect, useState } from 'react';
import { AppShell, type PageId } from './components/AppShell';
import { TraceabilityProvider } from './components/TraceabilityContext';
import { ActionsPage } from './pages/ActionsPage';
import { EquipmentIndexPage } from './pages/EquipmentIndexPage';
import { PRIMARY_ASSET_ID } from './lib/appConfig';
import './equipment.css';
import { DataFoundationPage } from './pages/DataFoundationPage';
import { OverviewPage } from './pages/OverviewPage';
import { PlantPage } from './pages/PlantPage';
import { InvestigationPage } from './pages/InvestigationPage';
import { ProblemTankPage } from './pages/ProblemTankPage';
import { RcaPage } from './pages/RcaPage';
import { RcaInvestigationPage } from './pages/RcaInvestigationPage';
import { ProductionReviewPage } from './pages/ProductionReviewPage';
import { DelegationPage } from './pages/DelegationPage';
import { OperatorEquipmentPage } from './pages/OperatorEquipmentPage';
import { EquipmentReviewPage } from './pages/EquipmentReviewPage';
import { GmReviewPage } from './pages/GmReviewPage';
import { AssignedActionsPage } from './pages/AssignedActionsPage';
import { selectWorkflowSession } from './lib/api';
import { useApiResource } from './lib/useApiResource';
import { LoadingState } from './components/ViewState';

const pages: Record<Exclude<PageId, 'assets'>, React.ComponentType<{ assetId?: string; alertId?: string; requestId?: string; personId?: string; onNavigate: (page: PageId, assetId?: string, alertId?: string) => void }>> = {
  overview: OverviewPage,
  plant: PlantPage,
  problems: ProblemTankPage,
  investigation: InvestigationPage,
  rca: RcaPage,
  'rca-investigation': RcaInvestigationPage,
  actions: ActionsPage,
  data: DataFoundationPage,
  'production-review': ProductionReviewPage,
  delegation: DelegationPage,
  'operator-equipment': OperatorEquipmentPage,
  'equipment-review': EquipmentReviewPage,
  'gm-review': GmReviewPage,
  'assigned-actions': AssignedActionsPage,
};

function routeFromHash() {
  const [path, query] = window.location.hash.slice(1).split('?');
  const params = new URLSearchParams(query);
  const page = path === 'assets' || Object.hasOwn(pages, path) ? path as PageId : 'plant';
  return { page, assetId: params.get('asset') ?? PRIMARY_ASSET_ID, alertId: params.get('alert'), requestId: params.get('request') ?? undefined, personId: params.get('person') ?? undefined };
}

export function App() {
  const [route, setRoute] = useState(routeFromHash);
  const personId = route.personId ?? (route.page === 'operator-equipment' ? 'demo-equipment-ko' : 'demo-supervisor');
  const identity = useApiResource(`workspace-session:${personId}`, async () => ({ personId, session: await selectWorkflowSession(personId) }));
  useEffect(() => {
    const syncPage = () => setRoute(routeFromHash());
    window.addEventListener('hashchange', syncPage);
    return () => window.removeEventListener('hashchange', syncPage);
  }, []);
  const navigate = (page: PageId, assetId = route.assetId, alertId?: string | null) => {
    const params = new URLSearchParams({ asset: assetId });
    params.set('person', personId);
    const selectedAlert = alertId ?? (assetId === route.assetId ? route.alertId : null);
    if (selectedAlert) params.set('alert', selectedAlert);
    window.location.hash = `${page}?${params}`;
    setRoute(routeFromHash());
  };
  if (identity.error) return <div className="production-review-error"><h1>Workspace unavailable</h1><p role="alert">{identity.error}</p><button onClick={identity.reload}>Retry</button></div>;
  if (!identity.data || identity.data.personId !== personId) return <LoadingState/>;
  const session = identity.data.session;
  const switchRole = (person: string, page: PageId, asset: string) => {
    window.location.hash = `${page}?${new URLSearchParams({ asset, person })}`;
  };
  const content = route.page === 'assets'
    ? <EquipmentIndexPage onSelect={(assetId) => navigate('overview', assetId)}/>
    : (() => { const Page = pages[route.page as Exclude<PageId, 'assets'>]; return <Page key={`${route.assetId}:${route.requestId ?? ''}:${route.personId ?? ''}`} assetId={route.assetId} alertId={route.alertId ?? undefined} requestId={route.requestId} personId={route.personId} onNavigate={navigate}/>; })();
  return <TraceabilityProvider key={route.assetId} assetId={route.assetId}><AppShell activePage={route.page} assetId={route.assetId} session={session} onSwitchRole={switchRole} onNavigate={navigate}>{content}</AppShell></TraceabilityProvider>;
}
