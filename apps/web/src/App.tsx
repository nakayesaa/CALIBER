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

const pages: Record<Exclude<PageId, 'assets'>, React.ComponentType<{ assetId?: string; onNavigate: (page: PageId, assetId?: string, alertId?: string) => void }>> = {
  overview: OverviewPage,
  plant: PlantPage,
  problems: ProblemTankPage,
  investigation: InvestigationPage,
  rca: RcaPage,
  'rca-investigation': RcaInvestigationPage,
  actions: ActionsPage,
  data: DataFoundationPage,
};

function routeFromHash() {
  const [path, query] = window.location.hash.slice(1).split('?');
  const params = new URLSearchParams(query);
  const page = path === 'assets' || Object.hasOwn(pages, path) ? path as PageId : 'plant';
  return { page, assetId: params.get('asset') ?? PRIMARY_ASSET_ID, alertId: params.get('alert') };
}

export function App() {
  const [route, setRoute] = useState(routeFromHash);
  useEffect(() => {
    const syncPage = () => setRoute(routeFromHash());
    window.addEventListener('hashchange', syncPage);
    return () => window.removeEventListener('hashchange', syncPage);
  }, []);
  const navigate = (page: PageId, assetId = route.assetId, alertId?: string | null) => {
    const params = new URLSearchParams({ asset: assetId });
    const selectedAlert = alertId ?? (assetId === route.assetId ? route.alertId : null);
    if (selectedAlert) params.set('alert', selectedAlert);
    window.location.hash = `${page}?${params}`;
    setRoute(routeFromHash());
  };
  const content = route.page === 'assets'
    ? <EquipmentIndexPage onSelect={(assetId) => navigate('overview', assetId)}/>
    : (() => { const Page = pages[route.page as Exclude<PageId, 'assets'>]; return <Page key={route.assetId} assetId={route.assetId} onNavigate={navigate}/>; })();
  return <TraceabilityProvider key={route.assetId} assetId={route.assetId}><AppShell activePage={route.page} assetId={route.assetId} onNavigate={navigate}>{content}</AppShell></TraceabilityProvider>;
}
