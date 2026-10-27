// Colores de las capas del mapa resueltos desde los tokens (16.2) a rgba, que MapLibre entiende.
import { resolveToken } from '$lib/utils/css-color';

export interface MapColors {
	active: string;
	recent: string;
	late: string;
	inactive: string;
	infra: string;
	alert: string;
	outline: string;
	text: string;
	textHalo: string;
	accent: string;
	good: string;
	fair: string;
	poor: string;
	cat1: string;
	cat2: string;
	cat3: string;
	catOther: string;
	route: string;
	cluster: string;
	clusterText: string;
	background: string;
}

export function readMapColors(): MapColors {
	return {
		active: resolveToken('--st-active'),
		recent: resolveToken('--st-recent'),
		late: resolveToken('--st-late'),
		inactive: resolveToken('--st-inactive'),
		infra: resolveToken('--st-infra'),
		alert: resolveToken('--st-alert'),
		outline: resolveToken('--map-outline'),
		text: resolveToken('--text-1'),
		textHalo: resolveToken('--bg'),
		accent: resolveToken('--accent'),
		good: resolveToken('--success'),
		fair: resolveToken('--warning'),
		poor: resolveToken('--danger'),
		cat1: resolveToken('--cat-1'),
		cat2: resolveToken('--cat-2'),
		cat3: resolveToken('--cat-3'),
		catOther: resolveToken('--cat-other'),
		route: resolveToken('--route'),
		cluster: resolveToken('--surface-2'),
		clusterText: resolveToken('--text-1'),
		background: resolveToken('--bg')
	};
}

/** Categoría de color de la capa de actividad por tipo de paquete (3 colores + gris). */
export function activityCategory(portnum: string | null): 'cat1' | 'cat2' | 'cat3' | 'catOther' {
	switch (portnum) {
		case 'POSITION_APP':
			return 'cat1';
		case 'TEXT_MESSAGE_APP':
		case 'ALERT_APP':
			return 'cat2';
		case 'TELEMETRY_APP':
			return 'cat3';
		default:
			return 'catOther';
	}
}
