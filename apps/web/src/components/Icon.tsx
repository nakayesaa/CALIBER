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

export function Icon({ name }: { name: IconName }) {
  return <span className={`noun-icon noun-icon-${name}`} aria-hidden="true"/>;
}
