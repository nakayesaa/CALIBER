import type { SVGProps } from 'react';

export type IconName =
  | 'alert'
  | 'arrow'
  | 'check'
  | 'database'
  | 'home'
  | 'inbox'
  | 'network'
  | 'pulse'
  | 'search'
  | 'spark'
  | 'tasks'
  | 'trend';

const paths: Record<IconName, React.ReactNode> = {
  alert: <><path d="M12 3 2.8 20h18.4z"/><path d="M12 9v5M12 17h.01"/></>,
  arrow: <path d="m9 5 7 7-7 7"/>,
  check: <path d="m5 12 4 4L19 6"/>,
  database: <><ellipse cx="12" cy="5" rx="8" ry="3"/><path d="M4 5v6c0 1.7 3.6 3 8 3s8-1.3 8-3V5M4 11v6c0 1.7 3.6 3 8 3s8-1.3 8-3v-6"/></>,
  home: <path d="m4 11 8-7 8 7v8a1 1 0 0 1-1 1h-5v-6h-4v6H5a1 1 0 0 1-1-1z"/>,
  inbox: <path d="M4 5h16l-2 14H6zM4.5 14h5l1.5 2h2l1.5-2h5"/>,
  network: <><circle cx="12" cy="6" r="3"/><circle cx="6" cy="17" r="3"/><circle cx="18" cy="17" r="3"/><path d="m10 9-2.5 5M14 9l2.5 5M9 17h6"/></>,
  pulse: <path d="M3 12h4l2-6 4 12 2-6h6"/>,
  search: <><circle cx="11" cy="11" r="6"/><path d="m16 16 4 4"/></>,
  spark: <><path d="m12 2 1.5 5.5L19 9l-5.5 1.5L12 16l-1.5-5.5L5 9l5.5-1.5z"/><path d="m19 16 .7 2.3L22 19l-2.3.7L19 22l-.7-2.3L16 19l2.3-.7z"/></>,
  tasks: <><path d="M9 6h11M9 12h11M9 18h11"/><path d="m3.5 6 1 1 2-2M3.5 12l1 1 2-2M3.5 18l1 1 2-2"/></>,
  trend: <path d="M4 19V5M4 19h16M7 15l4-5 3 3 5-7"/>,
};

export function Icon({ name, ...props }: { name: IconName } & SVGProps<SVGSVGElement>) {
  return <svg viewBox="0 0 24 24" aria-hidden="true" {...props}>{paths[name]}</svg>;
}
