import type { TelemetryPoint } from './api';

export type HealthTimeRange = '6M' | '3M' | '1M';

const RANGE_DAYS: Record<Exclude<HealthTimeRange, '6M'>, number> = {
  '3M': 90,
  '1M': 30,
};

export function selectIncidentWindow(
  points: TelemetryPoint[],
  range: HealthTimeRange,
  anchorTimestamp?: string,
): TelemetryPoint[] {
  if (range === '6M' || !anchorTimestamp || points.length < 2) return points;

  const timelineStart = new Date(points[0].timestamp).getTime();
  const timelineEnd = new Date(points.at(-1)!.timestamp).getTime();
  const duration = RANGE_DAYS[range] * 24 * 60 * 60 * 1000;
  const anchor = new Date(anchorTimestamp).getTime();
  let windowStart = anchor - duration / 2;
  let windowEnd = anchor + duration / 2;

  if (windowStart < timelineStart) {
    windowStart = timelineStart;
    windowEnd = Math.min(timelineStart + duration, timelineEnd);
  }
  if (windowEnd > timelineEnd) {
    windowEnd = timelineEnd;
    windowStart = Math.max(timelineEnd - duration, timelineStart);
  }

  return points.filter((point) => {
    const timestamp = new Date(point.timestamp).getTime();
    return timestamp >= windowStart && timestamp <= windowEnd;
  });
}
