import { useState } from 'react';
import type { EquipmentPoint } from '../lib/equipment';
import { formatDateTime, formatSignal } from '../lib/format';

export interface EquipmentChartWindow { start: string; end: string; label: string; state: string }
type ChartPoint = Omit<EquipmentPoint, 'value'> & { value: number | null };

export function EquipmentSeriesChart({ points, label, unit, windows = [], onWindowSelect, threshold, anchors = [] }: {
  points: ChartPoint[]; label: string; unit: string; windows?: EquipmentChartWindow[]; anchors?: EquipmentPoint[];
  onWindowSelect?: (window: EquipmentChartWindow) => void; threshold?: number | null;
}) {
  const [selected, setSelected] = useState<number | null>(null);
  if (!points.length) return <p className="equipment-empty">No readings in this window.</p>;
  const values = points.flatMap((point) => point.value === null ? [] : [point.value]);
  if (!values.length) return <p className="equipment-empty">No eligible scored readings in this window.</p>;
  const lo = Math.min(...values, threshold ?? Infinity);
  const hi = Math.max(...values, threshold ?? -Infinity);
  const padding = Math.max((hi - lo) * .2, Math.abs(hi) * .02, .1);
  const min = lo - padding, max = hi + padding;
  const first = Date.parse(points[0].timestamp), last = Date.parse(points.at(-1)!.timestamp);
  const x = (timestamp: string) => 48 + (Date.parse(timestamp) - first) / Math.max(last - first, 1) * 892;
  const y = (value: number) => 210 - (value - min) / (max - min) * 184;
  const selectedPoint = selected === null ? null : points[selected];
  return <div className="equipment-series">
    <svg viewBox="0 0 960 240" role="img" aria-label={`${label}, ${points.length} dated readings`} onPointerLeave={() => setSelected(null)} onPointerMove={(event) => {
      const bounds = event.currentTarget.getBoundingClientRect();
      const position = (event.clientX - bounds.left) / bounds.width * 960;
      const closest = points.reduce((best, point, index) => Math.abs(x(point.timestamp) - position) < Math.abs(x(points[best].timestamp) - position) ? index : best, 0);
      setSelected(closest);
    }}>
      {[0, .5, 1].map((fraction) => <g key={fraction}><line x1="48" x2="940" y1={26 + 184 * fraction} y2={26 + 184 * fraction} className="equipment-chart-grid"/><text x="42" y={30 + 184 * fraction} textAnchor="end">{formatSignal(max - (max - min) * fraction)}</text></g>)}
      {windows.map((window) => <rect key={`${window.start}-${window.end}`} x={x(window.start)} y="26" width={Math.max(x(window.end) - x(window.start), 1)} height="184" className={`equipment-window state-${window.state.toLowerCase()}`} onClick={() => onWindowSelect?.(window)}><title>{window.label}</title></rect>)}
      {threshold != null && <line x1="48" x2="940" y1={y(threshold)} y2={y(threshold)} className="equipment-chart-limit"/>}
      <path d={points.map((point, index) => point.value === null ? '' : `${index && points[index - 1].value !== null ? 'L' : 'M'}${x(point.timestamp)},${y(point.value)}`).join(' ')} className="equipment-chart-line"/>
      {points.length <= 26 && points.map((point) => point.value !== null && <circle key={point.timestamp} cx={x(point.timestamp)} cy={y(point.value)} r="3" className="equipment-chart-point"/>)}
      {anchors.filter((point) => Date.parse(point.timestamp) >= first && Date.parse(point.timestamp) <= last).map((point) => <circle key={point.timestamp} cx={x(point.timestamp)} cy={y(point.value)} r="4" className="equipment-chart-anchor"><title>Weekly source anchor · {formatDateTime(point.timestamp)} · {formatSignal(point.value)} {unit}</title></circle>)}
      {selectedPoint && <line x1={x(selectedPoint.timestamp)} x2={x(selectedPoint.timestamp)} y1="26" y2="210" className="equipment-chart-cursor"/>}
    </svg>
    <div className="equipment-chart-readout" aria-live="polite">{selectedPoint ? <><strong>{selectedPoint.value === null ? 'Score unavailable · suppressed / warm-up' : `${formatSignal(selectedPoint.value)} ${unit}`}</strong><span>{formatDateTime(selectedPoint.timestamp)}</span><small>{selectedPoint.source_reference}</small></> : <><span>{formatDateTime(points[0].timestamp)}</span><span>{points.length} readings · {unit}{anchors.length ? ' · circles: weekly source anchors' : ''}</span><span>{formatDateTime(points.at(-1)!.timestamp)}</span></>}</div>
    {!!windows.length && <nav className="equipment-window-controls" aria-label="Inspect condition windows">{windows.map((window) => <button key={window.start} className={`state-${window.state.toLowerCase()}`} onClick={() => onWindowSelect?.(window)}>{window.label}</button>)}</nav>}
  </div>;
}
