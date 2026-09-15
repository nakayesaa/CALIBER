import { useState, type PointerEvent } from 'react';
import type { TelemetryPoint } from '../lib/api';
import type { TimeWindow } from '../lib/timeWindow';

export type SignalField = keyof Pick<TelemetryPoint,
  'anomaly_score' | 'radial_vibration_micron' | 'water_in_oil_ppm' |
  'lube_oil_pressure_barg' | 'bearing_metal_temperature_degc' |
  'feed_rate_tph' | 'discharge_pressure_barg' | 'motor_current_a' | 'plant_rate_tph'>;

const signalMetadata: Record<SignalField, { label: string; unit: string }> = {
  anomaly_score: { label: 'Anomaly score', unit: '' },
  radial_vibration_micron: { label: 'Radial vibration', unit: 'µm' },
  water_in_oil_ppm: { label: 'Water in oil', unit: 'ppm' },
  lube_oil_pressure_barg: { label: 'Lube oil pressure', unit: 'barg' },
  bearing_metal_temperature_degc: { label: 'Bearing temperature', unit: '°C' },
  feed_rate_tph: { label: 'Feed rate', unit: 'tph' },
  discharge_pressure_barg: { label: 'Discharge pressure', unit: 'barg' },
  motor_current_a: { label: 'Motor current', unit: 'A' },
  plant_rate_tph: { label: 'Plant rate', unit: 'tph' },
};

interface SignalChartProps {
  points: TelemetryPoint[];
  field: SignalField;
  threshold?: number;
  highlightTimestamp?: string;
  highlightWindow?: TimeWindow;
  showRunStatus?: boolean;
  yPaddingRatio?: number;
}

export function SignalChart({ points, field, threshold, highlightTimestamp, highlightWindow, showRunStatus = false, yPaddingRatio = 0 }: SignalChartProps) {
  const [hoveredIndex, setHoveredIndex] = useState<number | null>(null);
  if (!points.length) return <div className="chart-empty">No telemetry points</div>;

  const values = points.map((point) => Number(point[field] ?? 0));
  const rawMin = Math.min(...values, threshold ?? Number.POSITIVE_INFINITY);
  const rawMax = Math.max(...values, threshold ?? Number.NEGATIVE_INFINITY);
  const rawSpan = Math.max(rawMax - rawMin, 1);
  const padding = rawSpan * yPaddingRatio;
  const min = rawMin - padding;
  const max = rawMax + padding;
  const span = max - min;
  const coordinates = values.map((value, index) => ({
    x: values.length === 1 ? 0 : index / (values.length - 1) * 100,
    y: 96 - (value - min) / span * 88,
  }));
  const path = coordinates.map(({ x, y }, index) => `${index === 0 ? 'M' : 'L'}${x.toFixed(2)} ${y.toFixed(2)}`).join(' ');
  const thresholdY = threshold === undefined ? null : 96 - (threshold - min) / span * 88;
  const hoveredPoint = hoveredIndex === null ? null : points[hoveredIndex];
  const hoveredCoordinate = hoveredIndex === null ? null : coordinates[hoveredIndex];
  const highlightedIndex = highlightTimestamp ? pointIndexWithinRange(points, highlightTimestamp) : null;
  const highlightedCoordinate = highlightedIndex === null ? null : coordinates[highlightedIndex];
  const windowCoordinates = highlightWindow ? visibleWindowCoordinates(points, coordinates, highlightWindow) : null;
  const stoppedRanges = showRunStatus ? runStatusRanges(points) : [];

  function trackPointer(event: PointerEvent<HTMLDivElement>) {
    const bounds = event.currentTarget.getBoundingClientRect();
    const position = Math.min(1, Math.max(0, (event.clientX - bounds.left) / bounds.width));
    setHoveredIndex(Math.round(position * (points.length - 1)));
  }

  return (
    <div className="interactive-chart" onPointerMove={trackPointer} onPointerLeave={() => setHoveredIndex(null)}>
      <svg className="line-chart" viewBox="0 0 100 100" preserveAspectRatio="none" role="img" aria-label={`${signalMetadata[field].label} trend`}>
        {stoppedRanges.map((range) => <rect className="run-status-off" x={range.start} y="4" width={range.width} height="92" key={`${range.start}-${range.width}`}/>)}
        {windowCoordinates && <rect className="evidence-window-fill" x={windowCoordinates.start} y="4" width={Math.max(windowCoordinates.end - windowCoordinates.start, .4)} height="92"/>}
        <path className="grid-line" d="M0 25H100M0 50H100M0 75H100"/>
        {thresholdY !== null && <path className="threshold-path" d={`M0 ${thresholdY}H100`}/>}
        <path className="data-path" d={path}/>
        {windowCoordinates && <>
          <line className="window-marker-line window-start-line" x1={windowCoordinates.start} x2={windowCoordinates.start} y1="4" y2="96"/>
          <line className="window-marker-line window-end-line" x1={windowCoordinates.end} x2={windowCoordinates.end} y1="4" y2="96"/>
        </>}
        {highlightedCoordinate && <line className="event-marker-line" x1={highlightedCoordinate.x} x2={highlightedCoordinate.x} y1="4" y2="96"/>}
        {hoveredCoordinate && <line className="tracking-line" x1={hoveredCoordinate.x} x2={hoveredCoordinate.x} y1="4" y2="96"/>}
      </svg>
      {hoveredPoint && hoveredCoordinate && <div className={`chart-tooltip${hoveredCoordinate.x > 72 ? ' align-right' : hoveredCoordinate.x < 28 ? ' align-left' : ''}`} style={{ left: `${hoveredCoordinate.x}%`, top: `${Math.min(82, Math.max(12, hoveredCoordinate.y))}%` }}>
        <time>{formatTimestamp(hoveredPoint.timestamp)}</time>
        <strong>{formatValue(Number(hoveredPoint[field]))} {signalMetadata[field].unit}</strong>
        <span>{signalMetadata[field].label}{field === 'anomaly_score' ? ` · ${formatDecisionState(hoveredPoint.decision_state)}` : showRunStatus ? ` · ${hoveredPoint.run_status}` : ''}</span>
      </div>}
    </div>
  );
}

function runStatusRanges(points: TelemetryPoint[]): Array<{ start: number; width: number }> {
  const ranges: Array<{ start: number; width: number }> = [];
  let rangeStart: number | null = null;
  points.forEach((point, index) => {
    if (point.run_status === 'OFF' && rangeStart === null) rangeStart = index;
    if (rangeStart === null || (point.run_status === 'OFF' && index !== points.length - 1)) return;
    const start = rangeStart;
    const end = point.run_status === 'OFF' ? index + 1 : index;
    const denominator = Math.max(points.length, 1);
    ranges.push({ start: start / denominator * 100, width: Math.max((end - start) / denominator * 100, .25) });
    rangeStart = null;
  });
  return ranges;
}

function pointIndexWithinRange(points: TelemetryPoint[], timestamp: string): number | null {
  const target = new Date(timestamp).getTime();
  if (target < new Date(points[0].timestamp).getTime() || target > new Date(points.at(-1)!.timestamp).getTime()) return null;
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

function visibleWindowCoordinates(
  points: TelemetryPoint[],
  coordinates: Array<{ x: number; y: number }>,
  window: TimeWindow,
): { start: number; end: number } | null {
  const timelineStart = new Date(points[0].timestamp).getTime();
  const timelineEnd = new Date(points.at(-1)!.timestamp).getTime();
  const windowStart = new Date(window.start).getTime();
  const windowEnd = new Date(window.end).getTime();
  if (windowEnd < timelineStart || windowStart > timelineEnd) return null;

  const startIndex = pointIndexWithinRange(points, new Date(Math.max(windowStart, timelineStart)).toISOString()) ?? 0;
  const endIndex = pointIndexWithinRange(points, new Date(Math.min(windowEnd, timelineEnd)).toISOString()) ?? points.length - 1;
  return { start: coordinates[startIndex].x, end: coordinates[endIndex].x };
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

function formatDecisionState(value: string): string {
  return value.toLowerCase().replaceAll('_', ' ').replace(/^./, (letter) => letter.toUpperCase());
}
