import { useState, type PointerEvent } from 'react';
import type { TelemetryPoint } from '../lib/api';

export type SignalField = keyof Pick<TelemetryPoint,
  'anomaly_score' | 'radial_vibration_micron' | 'water_in_oil_ppm' |
  'lube_oil_pressure_barg' | 'bearing_metal_temperature_degc' |
  'feed_rate_tph' | 'discharge_pressure_barg'>;

const signalMetadata: Record<SignalField, { label: string; unit: string }> = {
  anomaly_score: { label: 'Anomaly score', unit: '' },
  radial_vibration_micron: { label: 'Radial vibration', unit: 'µm' },
  water_in_oil_ppm: { label: 'Water in oil', unit: 'ppm' },
  lube_oil_pressure_barg: { label: 'Lube oil pressure', unit: 'barg' },
  bearing_metal_temperature_degc: { label: 'Bearing temperature', unit: '°C' },
  feed_rate_tph: { label: 'Feed rate', unit: 'tph' },
  discharge_pressure_barg: { label: 'Discharge pressure', unit: 'barg' },
};

interface SignalChartProps {
  points: TelemetryPoint[];
  field: SignalField;
  threshold?: number;
  highlightTimestamp?: string;
}

export function SignalChart({ points, field, threshold, highlightTimestamp }: SignalChartProps) {
  const [hoveredIndex, setHoveredIndex] = useState<number | null>(null);
  if (!points.length) return <div className="chart-empty">No telemetry points</div>;

  const values = points.map((point) => Number(point[field] ?? 0));
  const min = Math.min(...values, threshold ?? Number.POSITIVE_INFINITY);
  const max = Math.max(...values, threshold ?? Number.NEGATIVE_INFINITY);
  const span = Math.max(max - min, 1);
  const coordinates = values.map((value, index) => ({
    x: values.length === 1 ? 0 : index / (values.length - 1) * 100,
    y: 96 - (value - min) / span * 88,
  }));
  const path = coordinates.map(({ x, y }, index) => `${index === 0 ? 'M' : 'L'}${x.toFixed(2)} ${y.toFixed(2)}`).join(' ');
  const thresholdY = threshold === undefined ? null : 96 - (threshold - min) / span * 88;
  const hoveredPoint = hoveredIndex === null ? null : points[hoveredIndex];
  const hoveredCoordinate = hoveredIndex === null ? null : coordinates[hoveredIndex];
  const highlightedIndex = highlightTimestamp ? nearestPointIndex(points, highlightTimestamp) : null;
  const highlightedCoordinate = highlightedIndex === null ? null : coordinates[highlightedIndex];

  function trackPointer(event: PointerEvent<HTMLDivElement>) {
    const bounds = event.currentTarget.getBoundingClientRect();
    const position = Math.min(1, Math.max(0, (event.clientX - bounds.left) / bounds.width));
    setHoveredIndex(Math.round(position * (points.length - 1)));
  }

  return (
    <div className="interactive-chart" onPointerMove={trackPointer} onPointerLeave={() => setHoveredIndex(null)}>
      <svg className="line-chart" viewBox="0 0 100 100" preserveAspectRatio="none" role="img" aria-label={`${signalMetadata[field].label} trend`}>
        <path className="grid-line" d="M0 25H100M0 50H100M0 75H100"/>
        {thresholdY !== null && <path className="threshold-path" d={`M0 ${thresholdY}H100`}/>}
        <path className="data-path" d={path}/>
        {highlightedCoordinate && <line className="event-marker-line" x1={highlightedCoordinate.x} x2={highlightedCoordinate.x} y1="4" y2="96"/>}
        {hoveredCoordinate && <line className="tracking-line" x1={hoveredCoordinate.x} x2={hoveredCoordinate.x} y1="4" y2="96"/>}
      </svg>
      {hoveredPoint && hoveredCoordinate && <div className={`chart-tooltip${hoveredCoordinate.x > 72 ? ' align-right' : hoveredCoordinate.x < 28 ? ' align-left' : ''}`} style={{ left: `${hoveredCoordinate.x}%`, top: `${Math.min(82, Math.max(12, hoveredCoordinate.y))}%` }}>
        <time>{formatTimestamp(hoveredPoint.timestamp)}</time>
        <strong>{formatValue(Number(hoveredPoint[field]))} {signalMetadata[field].unit}</strong>
        <span>{signalMetadata[field].label}</span>
      </div>}
    </div>
  );
}

function nearestPointIndex(points: TelemetryPoint[], timestamp: string): number {
  const target = new Date(timestamp).getTime();
  let nearest = 0;
  let distance = Number.POSITIVE_INFINITY;
  points.forEach((point, index) => {
    const nextDistance = Math.abs(new Date(point.timestamp).getTime() - target);
    if (nextDistance < distance) {
      nearest = index;
      distance = nextDistance;
    }
  });
  return nearest;
}

function formatTimestamp(value: string): string {
  return new Intl.DateTimeFormat('en-GB', {
    day: '2-digit',
    month: 'short',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  }).format(new Date(value));
}

function formatValue(value: number): string {
  return new Intl.NumberFormat('en-US', { minimumFractionDigits: 1, maximumFractionDigits: 2 }).format(value);
}
