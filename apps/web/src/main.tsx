import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import '@fontsource-variable/manrope';
import { App } from './App';
import { DemoAccess } from './DemoAccess';

const demoAuth = (import.meta as ImportMeta & { env: Record<string, string> }).env.VITE_DEMO_AUTH === 'true';
import './styles.css';

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    {demoAuth ? <DemoAccess><App /></DemoAccess> : <App />}
  </StrictMode>,
);
