import type { AssetOverview, AssetSummary, ProductionImpact, TelemetryPoint } from './apiContracts';

export type ProductionReviewDecision = 'APPROVED' | 'CHANGES_REQUESTED' | 'UNABLE_TO_VALIDATE';
export type ProductionEvidencePoint = Pick<TelemetryPoint, 'timestamp' | 'feed_rate_tph' | 'plant_rate_tph' | 'run_status' | 'operating_mode'>;

export interface ProductionReport {
  report_id: string;
  version: string;
  revision: number;
  status: 'DRAFT' | 'SENT' | ProductionReviewDecision;
  scope: 'PRODUCTION';
  asset: AssetSummary;
  impact: ProductionImpact;
  points: ProductionEvidencePoint[];
  alert_id?: string | null;
  created_by: string;
  supervisor: string;
  recipient_id: string;
  recipient_name: string;
  created_at: string;
  due_at: string;
  sent_at: string | null;
  note: string;
  review: { decision: ProductionReviewDecision; note: string; actor_id: string; at: string } | null;
}

export interface ProductionReviewReport {
  reportId: string;
  version: string;
  scope: string;
  supervisor: string;
  requestedAt: string;
  dueAt: string;
  impact: ProductionImpact;
  points: ProductionEvidencePoint[];
  statement: string;
  response: string;
  delivery?: { status: string; recipient: string };
}

// The request is a preview fixture; figures and supporting records come from the API snapshot.
export function buildProductionReview(overview: AssetOverview, points: TelemetryPoint[]): ProductionReviewReport | null {
  const impact = overview.production_impact;
  if (!impact) return null;
  const requestedAt = new Date(new Date(impact.window_end).getTime() + 6 * 3600000).toISOString();
  return {
    reportId: `PR-${overview.asset.tag}-001`,
    version: '03',
    scope: `${overview.asset.plant_id} / Production`,
    supervisor: `${overview.asset.plant_id} shift supervisor`,
    requestedAt,
    dueAt: new Date(new Date(requestedAt).getTime() + 24 * 3600000).toISOString(),
    impact,
    points,
    statement: productionStatement(impact),
    response: `Validate the production evidence for ${overview.asset.tag} before the supervisor submits the consolidated investigation and proposed follow-up to the GM. This review does not approve maintenance or confirm the equipment root cause.`,
  };
}

export function verificationReport(report: ProductionReport): ProductionReviewReport {
  return {
    reportId: report.report_id, version: report.version,
    scope: `${report.asset.plant_id} / Production`, supervisor: report.supervisor,
    requestedAt: report.created_at, dueAt: report.due_at, impact: report.impact,
    points: report.points, statement: productionStatement(report.impact), response: report.note,
    delivery: { status: report.status, recipient: report.recipient_name },
  };
}

function productionStatement(impact: ProductionImpact): string {
  return `The report estimates ${impact.estimated_shortfall_tonnes.toFixed(1)} tonnes of equipment-feed shortfall across ${impact.offline_hours.toFixed(0)} sampled offline hours. The estimate compares recorded feed against a ${impact.baseline.expected_feed_tph.toFixed(2)} t/h reference at comparable plant load.`;
}

export function canRecordProductionDecision(decision: ProductionReviewDecision, note: string, checked: boolean): boolean {
  return Boolean(note.trim()) && (decision !== 'APPROVED' || checked);
}
