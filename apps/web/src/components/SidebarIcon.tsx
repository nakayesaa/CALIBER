import type { ReactNode } from 'react';

export type SidebarIconName = 'home' | 'problem' | 'asset' | 'rca' | 'action' | 'data';

const paths: Record<SidebarIconName, ReactNode> = {
  home: <path d="m4 11 8-7 8 7v8a1 1 0 0 1-1 1h-5v-6h-4v6H5a1 1 0 0 1-1-1z"/>,
  problem: <path d="M9 3h6M10 3v6l-5 9a2 2 0 0 0 2 3h10a2 2 0 0 0 2-3l-5-9V3M8 15h8"/>,
  asset: <><circle cx="12" cy="6" r="3"/><circle cx="6" cy="17" r="3"/><circle cx="18" cy="17" r="3"/><path d="m10 9-2.5 5M14 9l2.5 5M9 17h6"/></>,
  rca: <path d="M4 19V5M4 19h16M7 15l4-5 3 3 5-7"/>,
  action: <><circle cx="9" cy="8" r="3"/><path d="M3.5 19c.4-4 2.2-6 5.5-6s5.1 2 5.5 6M16 5a3 3 0 0 1 0 6M17 13c2.2.5 3.3 2.5 3.5 5"/></>,
  data: <path d="m4 9 8-5 8 5-8 5zM4 13l8 5 8-5M4 17l8 5 8-5"/>,
};

export function SidebarIcon({ name }: { name: SidebarIconName }) {
  return <svg className="sidebar-icon" viewBox="0 0 24 24" aria-hidden="true">{paths[name]}</svg>;
}
