import { request, type AssetSummary, type AlertEvent, type AlertStateTransition, type InvestigationEvidenceEvent } from './api';

export interface EquipmentPoint { timestamp: string; value: number; source_reference: string; source_status?: string | null }
export interface EquipmentSignal {
  key: string; label: string; unit: string; direction: 'HIGH' | 'LOW' | null;
  alarm_limit: number | null; trip_limit: number | null; cadence: 'WEEKLY' | 'HOURLY'; source_key: string; points: EquipmentPoint[];
}
export interface EquipmentAssessment {
  timestamp: string; state: string; score: number | null; breached_signals: string[]; reason: string; source_status: string;
}
export interface EquipmentAnalytics {
  mode: 'HOURLY_MODEL'; version: string; model_id: string;
  signals: EquipmentSignal[]; assessments: EquipmentAssessment[];
  transitions: AlertStateTransition[]; alert: AlertEvent;
  recovery: { eligible_hours: number; anomalous_hours: number; anomaly_rate: number };
}
export interface EquipmentInvestigation {
  asset: AssetSummary; signals: EquipmentSignal[];
  assessments: Array<{ timestamp: string; state: string; score: number; breached_signals: string[]; reason: string; source_status: string }>;
  transitions: AlertStateTransition[]; alert: AlertEvent; events: InvestigationEvidenceEvent[];
  source_actions: Array<{ id: string; title: string; action_type: string; owner: string; due_date: string; status: string; source_reference: string }>;
  quality_issues: string[]; reported_downtime_hours: number; reported_production_loss_tonnes: number;
  analytics: EquipmentAnalytics | null;
}

export const equipmentApi = {
  investigation: (assetId: string) => request<EquipmentInvestigation>(`/assets/${encodeURIComponent(assetId)}/investigation`),
};

export const equipmentCatalog = [
  { assetId: 'asset-pu-2101b', tag: 'PU-2101B', plant: 'ARP', name: 'Pump' },
  { assetId: 'asset-ko-3201', tag: 'KO-3201', plant: 'ZCU', name: 'Compressor' },
  { assetId: 'asset-he-3301', tag: 'HE-3301', plant: 'ZCU', name: 'Feed/effluent heat exchanger' },
  { assetId: 'asset-pm-4405b', tag: 'PM-4405B', plant: 'NUP', name: 'Cooling-water pump motor' },
  { assetId: 'asset-bl-5702', tag: 'BL-5702', plant: 'OPP', name: 'Blower' },
] as const;
