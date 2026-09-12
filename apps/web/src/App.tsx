import { useEffect, useState } from 'react';
import { AppShell, type PageId } from './components/AppShell';
import { ActionsPage } from './pages/ActionsPage';
import { AssetPage } from './pages/AssetPage';
import { DataFoundationPage } from './pages/DataFoundationPage';
import { OverviewPage } from './pages/OverviewPage';
import { OverviewV2Page } from './pages/OverviewV2Page';
import { InvestigationPage } from './pages/InvestigationPage';
import { ProblemTankPage } from './pages/ProblemTankPage';
import { RcaPage } from './pages/RcaPage';

const pages: Record<PageId, React.ComponentType<{ onNavigate: (page: PageId) => void }>> = {
  overview: OverviewPage,
  'overview-v2': OverviewV2Page,
  problems: ProblemTankPage,
  investigation: InvestigationPage,
  assets: AssetPage,
  rca: RcaPage,
  actions: ActionsPage,
  data: DataFoundationPage,
};

function pageFromHash(): PageId {
  const candidate = window.location.hash.slice(1) as PageId;
  return candidate in pages ? candidate : 'overview';
}

export function App() {
  const [activePage, setActivePage] = useState<PageId>(pageFromHash);
  useEffect(() => {
    const syncPage = () => setActivePage(pageFromHash());
    window.addEventListener('hashchange', syncPage);
    return () => window.removeEventListener('hashchange', syncPage);
  }, []);
  const navigate = (page: PageId) => {
    window.location.hash = page;
    setActivePage(page);
  };
  const Page = pages[activePage];
  return <AppShell activePage={activePage} onNavigate={navigate}><Page onNavigate={navigate}/></AppShell>;
}
