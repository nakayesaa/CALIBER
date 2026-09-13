import type { AlertEvent, AlertStateTransition, TelemetryPoint } from './api';
import { formatSignal, humanize } from './format';

export type EventTone = 'signal' | 'warning' | 'high' | 'critical' | 'closed';

export interface EventMilestone {
  id: string;
  timestamp: string;
  state: string;
  label: string;
  title: string;
  description: string;
  tone: EventTone;
  snapshot?: TelemetryPoint;
  synthesis: {
    title: string;
    detail: string;
  };
}

interface StatePresentation {
  title: string;
  description: string;
  tone: EventTone;
}

const statePresentation: Record<string, StatePresentation> = {
  FIRST_SIGNAL: {
    title: 'Oil condition began to deviate',
    description: 'Water-in-oil became the earliest persistent signal before the wider equipment response.',
    tone: 'signal',
  },
  WARNING: {
    title: 'Persistent condition warning opened',
    description: 'The leading condition remained abnormal long enough to satisfy the alert policy.',
    tone: 'warning',
  },
  HIGH: {
    title: 'Alert escalated to high priority',
    description: 'Persistent evidence increased the urgency of engineering review before wider signal convergence.',
    tone: 'high',
  },
  CRITICAL: {
    title: 'Multi-signal degradation became critical',
    description: 'Oil, pressure, thermal, and vibration evidence converged into a critical equipment condition.',
    tone: 'critical',
  },
  CLOSED: {
    title: 'Alert monitoring window closed',
    description: 'The operating-state transition ended this alert window and preserved it for investigation.',
    tone: 'closed',
  },
};

export function buildEventMilestones(
  alert: AlertEvent,
  transitions: AlertStateTransition[],
  telemetry: TelemetryPoint[],
): EventMilestone[] {
  const events = [
    { timestamp: alert.first_signal_at, state: 'FIRST_SIGNAL', reason: 'MODEL_CONDITION_DEVIATION' },
    ...transitions.map(({ timestamp, new_state: state, reason }) => ({ timestamp, state, reason })),
  ];

  return events.map((event, index) => {
    const presentation = statePresentation[event.state] ?? fallbackPresentation(event.state, event.reason);
    const snapshot = nearestTelemetryPoint(telemetry, event.timestamp);
    return {
      id: `${index}-${event.timestamp}-${event.state}`,
      timestamp: event.timestamp,
      state: event.state,
      label: humanize(event.state),
      title: presentation.title,
      description: presentation.description,
      tone: presentation.tone,
      snapshot,
      synthesis: buildConditionSynthesis(event.state, snapshot),
    };
  });
}

function fallbackPresentation(state: string, reason: string): StatePresentation {
  return {
    title: `${humanize(state)} state recorded`,
    description: humanize(reason),
    tone: 'signal',
  };
}

function nearestTelemetryPoint(points: TelemetryPoint[], timestamp: string): TelemetryPoint | undefined {
  if (!points.length) return undefined;
  const target = new Date(timestamp).getTime();
  let low = 0;
  let high = points.length - 1;

  while (low < high) {
    const middle = Math.floor((low + high) / 2);
    if (new Date(points[middle].timestamp).getTime() < target) low = middle + 1;
    else high = middle;
  }

  if (low === 0) return points[0];
  const before = points[low - 1];
  const after = points[low];
  return target - new Date(before.timestamp).getTime() <= new Date(after.timestamp).getTime() - target
    ? before
    : after;
}

function buildConditionSynthesis(state: string, snapshot?: TelemetryPoint): EventMilestone['synthesis'] {
  const score = snapshot?.anomaly_score == null ? 'not yet available' : formatSignal(snapshot.anomaly_score);
  const breadth = snapshot?.breached_signals.length ?? 0;

  if (state === 'FIRST_SIGNAL') return {
    title: 'An isolated lubrication signal is emerging',
    detail: `Water-in-oil moved first while broader mechanical evidence had not yet converged. The anomaly score was ${score}, so observation and verification were appropriate rather than a confirmed RCA.`,
  };
  if (state === 'WARNING') return {
    title: 'Lubrication contamination is the earliest working hypothesis',
    detail: `The persistent oil-condition deviation satisfied the warning policy with ${breadth} breached signal. Evidence was still narrow, so an oil sample and sensor verification were needed before escalation.`,
  };
  if (state === 'HIGH') return {
    title: 'Persistent oil-condition evidence raises the priority',
    detail: `The model reached ${score} with ${breadth} breached ${breadth === 1 ? 'signal' : 'signals'}. Persistence and risk intensity drove this escalation before broad signal convergence, making impaired lubrication a stronger but still unconfirmed hypothesis.`,
  };
  if (state === 'CRITICAL') return {
    title: 'Multi-signal convergence supports bearing oil-film degradation',
    detail: 'Oil condition, pressure, temperature, and vibration now form a mechanically coherent pattern. Moisture ingress degrading the lubricant film is the leading probable cause and immediate equipment inspection is justified.',
  };
  return {
    title: 'The alert window ended, but the cause remains actionable',
    detail: 'Closure records the operating-state termination rather than proof that the equipment recovered. The accumulated evidence remains available for RCA, corrective action, and effectiveness verification.',
  };
}
