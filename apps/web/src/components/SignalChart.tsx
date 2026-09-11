import type { TelemetryPoint } from '../lib/api';

interface SignalChartProps {
  points: TelemetryPoint[];
  field: keyof Pick<TelemetryPoint, 'anomaly_score' | 'radial_vibration_micron' | 'water_in_oil_ppm' | 'lube_oil_pressure_barg' | 'bearing_metal_temperature_degc'>;
  threshold?: number;
}

export function SignalChart({ points, field, threshold }: SignalChartProps) {
  const values = points.map((point) => Number(point[field] ?? 0));
  const min = Math.min(...values, threshold ?? Number.POSITIVE_INFINITY);
  const max = Math.max(...values, threshold ?? Number.NEGATIVE_INFINITY);
  const span = Math.max(max - min, 1);
  const path = values.map((value, index) => {
    const x = values.length === 1 ? 0 : (index / (values.length - 1)) * 100;
    const y = 96 - ((value - min) / span) * 88;
    return `${index === 0 ? 'M' : 'L'}${x.toFixed(2)} ${y.toFixed(2)}`;
  }).join(' ');
  const thresholdY = threshold === undefined ? null : 96 - ((threshold - min) / span) * 88;

  return (
    <svg className="line-chart" viewBox="0 0 100 100" preserveAspectRatio="none" role="img" aria-label={`${String(field)} trend`}>
      <path className="grid-line" d="M0 25H100M0 50H100M0 75H100"/>
      {thresholdY !== null && <path className="threshold-path" d={`M0 ${thresholdY}H100`}/>} 
      <path className="data-path" d={path}/>
    </svg>
  );
}
