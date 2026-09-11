import { Icon } from './Icon';

export function LoadingState() {
  return <div className="view-state"><span className="loader"/><p>Loading governed asset data</p></div>;
}

export function ErrorState({ message }: { message: string }) {
  return (
    <div className="view-state error-state">
      <Icon name="alert"/>
      <h2>Backend is not reachable</h2>
      <p>{message}</p>
      <code>make api</code>
    </div>
  );
}

export function EmptyState({ title, description }: { title: string; description: string }) {
  return <div className="empty-state"><span><Icon name="spark"/></span><h3>{title}</h3><p>{description}</p></div>;
}
