// Estado de un nodo según cuándo se lo escuchó por última vez (17.3); umbrales del sitio.
import type { NodeStatus, Thresholds } from '$lib/api/types';

export const DEFAULT_THRESHOLDS: Thresholds = { active_s: 3600, recent_s: 7200, late_s: 86400 };

export const STATUSES: readonly NodeStatus[] = ['active', 'recent', 'late', 'inactive'];

/** Igual que `State.status_of` del backend: activo < reciente < tardío < inactivo. */
export function classify(
	lastHeard: number | null | undefined,
	now: number,
	thresholds: Thresholds = DEFAULT_THRESHOLDS
): NodeStatus {
	if (lastHeard === null || lastHeard === undefined || !Number.isFinite(lastHeard)) {
		return 'inactive';
	}
	const age = now - lastHeard;
	if (age < thresholds.active_s) return 'active';
	if (age < thresholds.recent_s) return 'recent';
	if (age < thresholds.late_s) return 'late';
	return 'inactive';
}

/** Orden para listas: los más frescos primero. */
export function statusRank(status: NodeStatus): number {
	return STATUSES.indexOf(status);
}

/** Batería: 101 (o más) = alimentación externa (12.2.1). */
export function isPowered(battery: number | null | undefined, powered?: boolean): boolean {
	return Boolean(powered) || (battery !== null && battery !== undefined && battery > 100);
}

export type BatteryLevel = 'powered' | 'unknown' | 'critical' | 'low' | 'medium' | 'high';

export function batteryLevel(battery: number | null | undefined, powered?: boolean): BatteryLevel {
	if (isPowered(battery, powered)) return 'powered';
	if (battery === null || battery === undefined) return 'unknown';
	if (battery < 15) return 'critical';
	if (battery < 35) return 'low';
	if (battery < 70) return 'medium';
	return 'high';
}

/** Calidad del enlace por SNR (16.5): ≥ 5 dB buena, 0 a 5 regular, < 0 mala. */
export type SnrClass = 'good' | 'fair' | 'poor' | 'unknown';

export function snrClass(snr: number | null | undefined): SnrClass {
	if (snr === null || snr === undefined || !Number.isFinite(snr)) return 'unknown';
	if (snr >= 5) return 'good';
	if (snr >= 0) return 'fair';
	return 'poor';
}

/** Barras de señal (0-4) combinando SNR y RSSI de la última recepción. */
export function signalBars(snr: number | null | undefined, rssi?: number | null): number {
	if (snr === null || snr === undefined) {
		if (rssi === null || rssi === undefined) return 0;
		if (rssi >= -90) return 4;
		if (rssi >= -105) return 3;
		if (rssi >= -115) return 2;
		return 1;
	}
	if (snr >= 7) return 4;
	if (snr >= 2) return 3;
	if (snr >= -5) return 2;
	return 1;
}

/** Roles de infraestructura (12.2.1); `CLIENT_BASE` no es infraestructura (ADR 0009). */
export const INFRA_ROLES = new Set(['ROUTER', 'ROUTER_LATE', 'REPEATER', 'ROUTER_CLIENT']);
