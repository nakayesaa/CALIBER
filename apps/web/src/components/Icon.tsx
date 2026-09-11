export type IconName =
  | 'alert'
  | 'arrow'
  | 'check'
  | 'database'
  | 'inbox'
  | 'pulse'
  | 'search'
  | 'spark';

export function Icon({ name }: { name: IconName }) {
  return <span className={`noun-icon noun-icon-${name}`} aria-hidden="true"/>;
}
