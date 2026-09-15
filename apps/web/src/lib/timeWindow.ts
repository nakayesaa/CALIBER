import type { AlertEvent, AlertStateTransition, TelemetryPoint } from './api';

export type HealthTimeRange = '6M' | '3M' | '1M' | 'DETECTION';

export interface TimeWindow {
  start: string;
  end: string;
}

export interface AlertTimeWindow extends TimeWindow {
  id: string;
  alertId: string;
  fromState: string;
  toState: string;
  milestoneIndex: number;
}

const RANGE_DAYS: Record<Exclude<HealthTimeRange, '6M' | 'DETECTION'>, number> = {
  '3M': 90,
  '1M': 30,
};

export function alertDetectionWindow(
  alert: AlertEvent,
  transitions: AlertStateTransition[],
): TimeWindow {
  return alertProgressionWindows(alert, transitions).find((window) => window.toState === 'WARNING')
    ?? { start: alert.first_signal_at, end: alert.opened_at };
}

export function alertProgressionWindows(
  alert: AlertEvent,
  transitions: AlertStateTransition[],
): AlertTimeWindow[] {
  const milestones = [
    { timestamp: alert.first_signal_at, state: 'FIRST_SIGNAL' },
    ...transitions.map((transition) => ({ timestamp: transition.timestamp, state: transition.new_state })),
  ];

  return milestones.slice(1).map((milestone, index) => ({
    id: `${alert.alert_id}:window-${index + 1}`,
    alertId: alert.alert_id,
    fromState: milestones[index].state,
    toState: milestone.state,
    start: milestones[index].timestamp,
    end: milestone.timestamp,
    milestoneIndex: index + 1,
  }));
}

export function selectTelemetryWindow(
  points: TelemetryPoint[],
  window: TimeWindow,
): TelemetryPoint[] {
  const start = new Date(window.start).getTime();
  const end = new Date(window.end).getTime();
  return points.filter((point) => {
    const timestamp = new Date(point.timestamp).getTime();
    return timestamp >= start && timestamp <= end;
  });
}

export function timeWindowHours(window: TimeWindow): number {
  return Math.max(0, (new Date(window.end).getTime() - new Date(window.start).getTime()) / 3_600_000);
}

export function selectIncidentWindow(
  points: TelemetryPoint[],
  range: HealthTimeRange,
  anchorTimestamp?: string,
  detectionWindow?: TimeWindow,
): TelemetryPoint[] {
  if (range === 'DETECTION') {
    return detectionWindow ? selectTelemetryWindow(points, detectionWindow) : points;
  }
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
