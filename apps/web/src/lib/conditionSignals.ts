import type { TelemetryPoint } from './api';

export type ConditionField = keyof Pick<TelemetryPoint,
  'water_in_oil_ppm' | 'radial_vibration_micron' |
  'bearing_metal_temperature_degc' | 'lube_oil_pressure_barg'>;

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
