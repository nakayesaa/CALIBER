import { useCallback, useEffect, useState, type FormEvent, type ReactNode } from 'react';
import './demo-access.css';
import { flowHash } from './lib/flowTour';
import './components/flow-tour.css';

type Identity = { person_id: string; username: string };

function homePage(identity: Identity) {
  const role = `${identity.username} ${identity.person_id}`.toLowerCase();
  if (role.includes('supervisor')) return 'plant';
  if (role.includes('production')) return 'production-review';
  if (role.includes('equipment')) return 'operator-equipment';
  if (role.includes('gm') || role.includes('general-manager')) return 'gm-review';
  return 'assigned-actions';
}

function bindRoute(identity: Identity, first = false) {
  const [page, query = ''] = window.location.hash.slice(1).split('?');
  const params = new URLSearchParams(query);
  if (first || params.get('person') !== identity.person_id) {
    params.set('person', identity.person_id);
    window.location.hash = `${homePage(identity)}?${params}`;
  } else if (!page) {
    window.location.hash = `${homePage(identity)}?${params}`;
  }
}

export function DemoAccess({ children }: { children: ReactNode }) {
  const [identity, setIdentity] = useState<Identity | null>(null);
  const [checking, setChecking] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const checkSession = useCallback(async () => {
    setChecking(true);
    setError('');
    try {
      const response = await fetch('/auth/session', { credentials: 'same-origin', cache: 'no-store' });
      if (response.status === 401 || response.status === 403) { setIdentity(null); return; }
      if (!response.ok) throw new Error();
      const user: Identity = await response.json();
      bindRoute(user, new URLSearchParams(window.location.hash.split('?')[1]).get('person') !== user.person_id);
      setIdentity(user);
    } catch {
      setIdentity(null);
      setError('Unable to connect to IRIS. Please retry.');
    } finally { setChecking(false); }
  }, []);
  useEffect(() => { void checkSession(); }, [checkSession]);
  useEffect(() => {
    const expired = () => { setIdentity(null); setPassword(''); setError('Your session has expired. Please sign in again.'); };
    window.addEventListener('iris-session-expired', expired);
    return () => window.removeEventListener('iris-session-expired', expired);
  }, []);
  useEffect(() => {
    if (!identity) return;
    const guard = () => bindRoute(identity);
    window.addEventListener('hashchange', guard);
    return () => window.removeEventListener('hashchange', guard);
  }, [identity]);
  async function login(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true); setError('');
    try {
      const response = await fetch('/auth/login', {
        method: 'POST', credentials: 'same-origin', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username: username.trim(), password }),
      });
      if (response.status === 401 || response.status === 403) { setError('The username or password is incorrect.'); return; }
      if (!response.ok) throw new Error();
      const user: Identity = await response.json();
      bindRoute(user, true);
      const [page, query = ''] = window.location.hash.slice(1).split('?');
      const params = new URLSearchParams(query);
      params.delete('flow');
      params.delete('flowStep');
      window.location.hash = `${page}?${params}`;
      setPassword(''); setIdentity(user);
    } catch { setError('Unable to sign in. Please check your connection and try again.'); }
    finally { setBusy(false); }
  }
  async function logout() {
    setBusy(true); setError('');
    try {
      const response = await fetch('/auth/logout', { method: 'POST', credentials: 'same-origin' });
      if (!response.ok && response.status !== 401) throw new Error();
      setIdentity(null); setPassword('');
    } catch { setError('Unable to sign out. Please try again.'); }
    finally { setBusy(false); }
  }
  if (identity) return <><div className="demo-session"><span>{identity.username}</span>{homePage(identity) === 'plant' && <button className="demo-flow-button" type="button" disabled={busy} onClick={() => { window.dispatchEvent(new Event('iris-flow-start')); window.location.hash = flowHash(identity.person_id); }}>Flow · KO-3201</button>}<button type="button" disabled={busy} onClick={() => void logout()}>{busy ? 'Signing out…' : 'Sign out'}</button>{error && <span role="alert">{error}</span>}</div>{children}</>;
  return <main className="demo-access"><section className="demo-access-card" aria-labelledby="demo-access-title">
    <div className="demo-access-brand"><span aria-hidden="true" className="demo-access-mark">I</span><span>IRIS</span></div>
    <p className="demo-access-eyebrow">Competition prototype</p>
    <h1 id="demo-access-title">Sign in to IRIS</h1>
    <p className="demo-access-intro">Access your operations workspace.</p>
    {checking ? <p role="status" className="demo-access-status">Checking your session…</p> : <form onSubmit={event => void login(event)}>
      <label htmlFor="demo-username">Username</label>
      <input id="demo-username" name="username" autoComplete="username" required value={username} onChange={event => setUsername(event.target.value)} disabled={busy} />
      <label htmlFor="demo-password">Password</label>
      <input id="demo-password" name="password" type="password" autoComplete="current-password" required value={password} onChange={event => setPassword(event.target.value)} disabled={busy} />
      {error && <p className="demo-access-error" role="alert">{error}</p>}
      <button className="demo-access-submit" type="submit" disabled={busy}>{busy ? 'Signing in…' : 'Sign in'}</button>
      {error.includes('retry') && <button className="demo-access-retry" type="button" onClick={() => void checkSession()}>Retry connection</button>}
    </form>}
    <p className="demo-access-footer">Industrial Reliability Intelligence System</p>
  </section></main>;
}
