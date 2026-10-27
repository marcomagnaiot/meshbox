// Métricas de telemetría: etiqueta, formato y rango por defecto para los gráficos.
import type { TelemetryKind, TelemetrySeries } from '$lib/api/types';
import { formatNumber, formatUnit } from '$lib/i18n/format';
import { m } from '$lib/paraglide/messages';

export interface MetricDef {
	key: string;
	kind: TelemetryKind;
	label: () => string;
	format: (v: number, locale: string) => string;
	range?: [number, number];
}

const num = (digits: number, suffix: string) => (v: number, locale: string) =>
	`${formatNumber(v, { locale }, digits)} ${suffix}`;

export const METRICS: MetricDef[] = [
	{
		key: 'battery_level',
		kind: 'device',
		label: m.chart_battery,
		// Más de 100 = alimentación externa (la placa informa 101 mientras carga con sol o USB).
		format: (v, locale) => (v > 100 ? m.chart_battery_external() : num(0, '%')(v, locale)),
		range: [0, 105]
	},
	{ key: 'voltage', kind: 'device', label: m.chart_voltage, format: num(2, 'V') },
	{ key: 'channel_utilization', kind: 'device', label: m.chart_channel_util, format: num(1, '%') },
	{ key: 'air_util_tx', kind: 'device', label: m.chart_air_util, format: num(1, '%') },
	{
		key: 'temperature',
		kind: 'environment',
		label: m.chart_temperature,
		format: (v, locale) => formatUnit(v, 'celsius', { locale }, 1)
	},
	{
		key: 'relative_humidity',
		kind: 'environment',
		label: m.chart_humidity,
		format: num(0, '%'),
		range: [0, 100]
	},
	{
		key: 'barometric_pressure',
		kind: 'environment',
		label: m.chart_pressure,
		format: num(0, 'hPa')
	},
	{ key: 'lux', kind: 'environment', label: m.chart_lux, format: num(0, 'lx') }
];

export function metricDef(kind: TelemetryKind, key: string): MetricDef {
	return (
		METRICS.find((d) => d.kind === kind && d.key === key) ?? {
			key,
			kind,
			label: () => key.replaceAll('_', ' '),
			format: num(2, '')
		}
	);
}

export const TELEMETRY_RANGES = [
	{ value: '3600', label: '1 h' },
	{ value: '21600', label: '6 h' },
	{ value: '86400', label: '24 h' },
	{ value: '172800', label: '48 h' },
	{ value: '604800', label: '7 d' },
	{ value: '2592000', label: '30 d' }
] as const;

export const HISTORY_RANGES = [
	{ value: '3600', label: '1 h' },
	{ value: '21600', label: '6 h' },
	{ value: '43200', label: '12 h' },
	{ value: '86400', label: '1 d' },
	{ value: '172800', label: '2 d' },
	{ value: '259200', label: '3 d' },
	{ value: '432000', label: '5 d' },
	{ value: '604800', label: '7 d' }
] as const;

/** Cómo vienen los datos del gráfico: cada muestra, grupos de minutos o promedios. */
export function resolutionLabel(data: TelemetrySeries | null): string {
	if (!data) return '';
	if (data.resolution === 'bucket' && data.bucket_s)
		return m.chart_resolution_bucket({ minutes: Math.round(data.bucket_s / 60) });
	if (data.resolution === 'hour') return m.chart_resolution_hour();
	if (data.resolution === 'day') return m.chart_resolution_day();
	return m.chart_resolution_raw();
}
