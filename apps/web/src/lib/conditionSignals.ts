import type { TelemetryPoint } from './api';

export type ConditionField = keyof Pick<TelemetryPoint,
  'water_in_oil_ppm' | 'radial_vibration_micron' |
  'bearing_metal_temperature_degc' | 'lube_oil_pressure_barg' |
  'tube_dp' | 'heat_duty' | 'cold_outlet_temp' | 'heavy_ends'>;

export type OperatingField = keyof Pick<TelemetryPoint,
  'feed_rate_tph' | 'discharge_pressure_barg' | 'motor_current_a' | 'plant_rate_tph'>;

export type EquipmentSignalField = ConditionField | OperatingField;

export interface EquipmentSignal<Field extends EquipmentSignalField = EquipmentSignalField> {
  field: Field;
  label: string;
  unit: string;
  role: string;
}

export const conditionSignals: readonly EquipmentSignal<ConditionField>[] = [
  { field: 'water_in_oil_ppm', label: 'Water in oil', unit: 'ppm', role: 'Primary driver' },
  { field: 'radial_vibration_micron', label: 'Radial vibration', unit: 'µm', role: 'Mechanical response' },
  { field: 'bearing_metal_temperature_degc', label: 'Bearing temperature', unit: '°C', role: 'Thermal response' },
  { field: 'lube_oil_pressure_barg', label: 'Lube oil pressure', unit: 'barg', role: 'Supporting condition' },
];

export const operatingSignals: readonly EquipmentSignal<OperatingField>[] = [
  { field: 'feed_rate_tph', label: 'Feed rate', unit: 't/h', role: 'Equipment throughput' },
  { field: 'discharge_pressure_barg', label: 'Discharge pressure', unit: 'barg', role: 'Process delivery' },
  { field: 'motor_current_a', label: 'Motor current', unit: 'A', role: 'Drive load' },
  { field: 'plant_rate_tph', label: 'Plant rate', unit: 't/h', role: 'Plant load context' },
];

const exchangerSignals: readonly EquipmentSignal<ConditionField>[] = [
  { field: 'tube_dp', label: 'Tube pressure drop', unit: 'bar', role: 'Hydraulic resistance' },
  { field: 'heat_duty', label: 'Heat duty', unit: '% design', role: 'Thermal performance' },
  { field: 'cold_outlet_temp', label: 'Cold outlet temperature', unit: '°C', role: 'Thermal response' },
  { field: 'heavy_ends', label: 'Heavy ends', unit: '%', role: 'Feed quality context' },
];

export function conditionSignalsFor(assetId: string) {
  return assetId === 'asset-he-3301' ? exchangerSignals : conditionSignals;
}

export function operatingSignalsFor(assetId: string) {
  return assetId === 'asset-he-3301' ? operatingSignals.filter((signal) => ['feed_rate_tph', 'plant_rate_tph'].includes(signal.field)) : operatingSignals;
}

export function equipmentPresentation(assetId: string) {
  const exchanger = assetId === 'asset-he-3301';
  return {
    tag: exchanger ? 'HE-3301' : 'KO-3201',
    name: exchanger ? 'Heat exchanger performance degradation' : 'Compressor degradation',
    firstSignalTitle: exchanger ? 'Exchanger performance began to deviate' : 'Oil condition began to deviate',
    firstSignalDetail: exchanger ? 'Review hydraulic, thermal and feed-quality changes before identifying a physical cause.' : 'Water-in-oil became persistent before the broader equipment response.',
    escalationDetail: exchanger ? 'Pressure drop, duty, outlet temperature and feed-quality evidence support exchanger inspection.' : 'Oil, pressure, thermal, and vibration evidence formed a critical pattern.',
  };
}
