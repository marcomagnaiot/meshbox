// Filtros y orden de nodos, compartidos por el mapa y la lista (17.1).
import type { Node, NodeStatus, Thresholds } from '$lib/api/types';
import { classify, isPowered, statusRank } from './status';
import { matches } from './text';
import { shortFromId } from './ids';

export type SortKey = 'last_heard' | 'name' | 'battery' | 'snr' | 'hops';

export interface NodeFilter {
	query: string;
	/** Estados visibles; vacío = todos los permitidos. */
	statuses: NodeStatus[];
	showInactive: boolean;
	onlyActive: boolean;
	onlyInfra: boolean;
	withPosition: boolean;
	withTelemetry: boolean;
	role: string;
}

export const EMPTY_FILTER: NodeFilter = {
	query: '',
	statuses: [],
	showInactive: false,
	onlyActive: false,
	onlyInfra: false,
	withPosition: false,
	withTelemetry: false,
	role: ''
};

export function displayName(node: Pick<Node, 'id' | 'long_name' | 'short_name'>): string {
	return node.long_name || node.short_name || node.id;
}

export function shortName(node: Pick<Node, 'id' | 'short_name'>): string {
	return node.short_name || shortFromId(node.id);
}

export function hasTelemetry(node: Node): boolean {
	return (
		node.battery !== null ||
		node.voltage !== null ||
		node.channel_utilization !== null ||
		node.env !== null
	);
}

export function hasPosition(node: Pick<Node, 'lat' | 'lon'>): boolean {
	return typeof node.lat === 'number' && typeof node.lon === 'number';
}

export function filterNodes(
	nodes: Node[],
	filter: NodeFilter,
	now: number,
	thresholds: Thresholds
): Node[] {
	return nodes.filter((n) => {
		const status = classify(n.last_heard, now, thresholds);
		if (status === 'inactive' && !filter.showInactive && !filter.statuses.includes('inactive')) {
			return false;
		}
		if (filter.onlyActive && status !== 'active') return false;
		if (filter.statuses.length && !filter.statuses.includes(status)) return false;
		if (filter.onlyInfra && !n.is_infra) return false;
		if (filter.withPosition && !hasPosition(n)) return false;
		if (filter.withTelemetry && !hasTelemetry(n)) return false;
		if (filter.role && n.role !== filter.role) return false;
		if (filter.query && !matches(filter.query, n.long_name, n.short_name, n.id, n.hw_model)) {
			return false;
		}
		return true;
	});
}

function nullsLast(a: number | null, b: number | null, desc: boolean): number {
	if (a === null && b === null) return 0;
	if (a === null) return 1;
	if (b === null) return -1;
	return desc ? b - a : a - b;
}

// Un solo comparador, creado al ordenar por nombre por primera vez (crearlo carga datos de ICU).
let collator: Intl.Collator | null = null;

export function sortNodes(
	nodes: Node[],
	key: SortKey,
	now: number,
	thresholds: Thresholds
): Node[] {
	const list = [...nodes];
	const byName =
		key === 'name'
			? (collator ??= new Intl.Collator(undefined, { sensitivity: 'base', numeric: true }))
			: null;
	list.sort((a, b) => {
		switch (key) {
			case 'name':
				return byName ? byName.compare(displayName(a), displayName(b)) : 0;
			case 'battery': {
				const va = isPowered(a.battery, a.powered) ? 101 : a.battery;
				const vb = isPowered(b.battery, b.powered) ? 101 : b.battery;
				return nullsLast(va, vb, true) || b.last_heard - a.last_heard;
			}
			case 'snr':
				return nullsLast(a.snr, b.snr, true) || b.last_heard - a.last_heard;
			case 'hops':
				return nullsLast(a.hops, b.hops, false) || b.last_heard - a.last_heard;
			default: {
				const sa = statusRank(classify(a.last_heard, now, thresholds));
				const sb = statusRank(classify(b.last_heard, now, thresholds));
				return b.last_heard - a.last_heard || sa - sb;
			}
		}
	});
	return list;
}

export function countByStatus(
	nodes: Node[],
	now: number,
	thresholds: Thresholds
): Record<NodeStatus, number> {
	const out: Record<NodeStatus, number> = { active: 0, recent: 0, late: 0, inactive: 0 };
	for (const n of nodes) out[classify(n.last_heard, now, thresholds)]++;
	return out;
}
