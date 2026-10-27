// Construcción de GeoJSON para las capas de datos (funciones puras, probadas con vitest).
import type {
	Link,
	Node,
	NodeStatus,
	Position,
	Thresholds,
	Traceroute,
	Waypoint
} from '$lib/api/types';
import { circleRing, isValidLatLon } from '$lib/utils/geo';
import { nodeNum, shortFromId } from '$lib/utils/ids';
import { filterNodes, type NodeFilter } from '$lib/utils/nodes';
import { classify, snrClass, type SnrClass } from '$lib/utils/status';
import { mapLabel } from '$lib/utils/text';

export interface Feature<G, P> {
	type: 'Feature';
	id?: number;
	geometry: G;
	properties: P;
}
export interface FeatureCollection<G = Geometry, P = Record<string, unknown>> {
	type: 'FeatureCollection';
	features: Feature<G, P>[];
}
export type Point = { type: 'Point'; coordinates: [number, number] };
export type LineString = { type: 'LineString'; coordinates: [number, number][] };
export type Polygon = { type: 'Polygon'; coordinates: [number, number][][] };
export type Geometry = Point | LineString | Polygon;

export const EMPTY: FeatureCollection = { type: 'FeatureCollection', features: [] };

export interface NodeProps {
	id: string;
	label: string;
	status: NodeStatus;
	icon: string;
	/** Más frescos arriba: symbol-sort-key mayor se dibuja encima. */
	sort: number;
}

const SORT: Record<NodeStatus, number> = { active: 4, recent: 3, late: 2, inactive: 1 };

export function iconName(status: NodeStatus, infra: boolean, fixed: boolean): string {
	return `node-${status}-${infra ? 1 : 0}${fixed ? 1 : 0}`;
}

export function nodeLabel(node: Pick<Node, 'id' | 'short_name' | 'long_name'>): string {
	return mapLabel(node.short_name, mapLabel(node.long_name?.slice(0, 4), shortFromId(node.id)));
}

/** Nodos visibles con posición, según los filtros compartidos con la lista. */
export function nodesCollection(
	nodes: Node[],
	filter: NodeFilter,
	now: number,
	thresholds: Thresholds
): FeatureCollection<Point, NodeProps> {
	const features: Feature<Point, NodeProps>[] = [];
	for (const n of filterNodes(nodes, filter, now, thresholds)) {
		if (!isValidLatLon(n.lat, n.lon)) continue;
		const status = classify(n.last_heard, now, thresholds);
		features.push({
			type: 'Feature',
			id: nodeNum(n.id),
			geometry: { type: 'Point', coordinates: [n.lon as number, n.lat as number] },
			properties: {
				id: n.id,
				label: nodeLabel(n),
				status,
				icon: iconName(status, n.is_infra, n.is_fixed),
				sort: SORT[status]
			}
		});
	}
	return { type: 'FeatureCollection', features };
}

/** Círculos de incertidumbre de posición (precision_m) de los nodos visibles. */
export function uncertaintyCollection(
	nodes: FeatureCollection<Point, NodeProps>,
	byId: Map<string, Node>
): FeatureCollection<Polygon, { id: string }> {
	const features: Feature<Polygon, { id: string }>[] = [];
	for (const f of nodes.features) {
		const node = byId.get(f.properties.id);
		const p = node?.precision_m;
		if (!node || p === null || p === undefined || !(p > 1) || p > 50_000) continue;
		const [lon, lat] = f.geometry.coordinates;
		features.push({
			type: 'Feature',
			id: f.id,
			geometry: { type: 'Polygon', coordinates: [circleRing(lat, lon, p)] },
			properties: { id: node.id }
		});
	}
	return { type: 'FeatureCollection', features };
}

export interface LinkProps {
	a: string;
	b: string;
	cls: SnrClass;
	snr: number | null;
	/** 1 = recién visto, 0 = hace 24 h o más (grosor y opacidad). */
	recency: number;
	source: Link['source'];
}

/** Enlaces entre vecinos: uno por par de nodos (el más reciente) y solo si ambos tienen posición. */
export function linksCollection(
	links: Iterable<Link>,
	byId: Map<string, Node>,
	now: number,
	visible?: Set<string>,
	maxAge = 86400
): FeatureCollection<LineString, LinkProps> {
	const best = new Map<string, Link>();
	for (const l of links) {
		if (l.a === l.b) continue;
		const key = l.a < l.b ? `${l.a}|${l.b}` : `${l.b}|${l.a}`;
		const prev = best.get(key);
		if (!prev || l.ts > prev.ts) best.set(key, l);
	}
	const features: Feature<LineString, LinkProps>[] = [];
	for (const l of best.values()) {
		if (now - l.ts > maxAge) continue;
		if (visible && !(visible.has(l.a) && visible.has(l.b))) continue;
		const a = byId.get(l.a);
		const b = byId.get(l.b);
		if (!a || !b || !isValidLatLon(a.lat, a.lon) || !isValidLatLon(b.lat, b.lon)) continue;
		features.push({
			type: 'Feature',
			geometry: {
				type: 'LineString',
				coordinates: [
					[a.lon as number, a.lat as number],
					[b.lon as number, b.lat as number]
				]
			},
			properties: {
				a: l.a,
				b: l.b,
				cls: snrClass(l.snr),
				snr: l.snr,
				recency: Math.max(0, Math.min(1, 1 - (now - l.ts) / maxAge)),
				source: l.source
			}
		});
	}
	return { type: 'FeatureCollection', features };
}

export interface TrackProps {
	kind: 'line' | 'hour' | 'cursor' | 'start' | 'end';
	ts?: number;
}

/** Recorrido del nodo seleccionado: línea, puntos horarios y el punto de la reproducción. */
export function trackCollection(
	positions: Position[],
	cursor: number | null
): FeatureCollection<Point | LineString, TrackProps> {
	const pts = positions.filter((p) => isValidLatLon(p.lat, p.lon));
	const features: Feature<Point | LineString, TrackProps>[] = [];
	if (pts.length >= 2) {
		features.push({
			type: 'Feature',
			geometry: { type: 'LineString', coordinates: pts.map((p) => [p.lon, p.lat]) },
			properties: { kind: 'line' }
		});
	}
	let lastHour = -1;
	pts.forEach((p, i) => {
		const hour = Math.floor(p.ts / 3600);
		const kind: TrackProps['kind'] = i === 0 ? 'start' : i === pts.length - 1 ? 'end' : 'hour';
		if (kind === 'hour' && hour === lastHour) return;
		lastHour = hour;
		features.push({
			type: 'Feature',
			geometry: { type: 'Point', coordinates: [p.lon, p.lat] },
			properties: { kind, ts: p.ts }
		});
	});
	if (cursor !== null && pts[cursor]) {
		const p = pts[cursor];
		features.push({
			type: 'Feature',
			geometry: { type: 'Point', coordinates: [p.lon, p.lat] },
			properties: { kind: 'cursor', ts: p.ts }
		});
	}
	return { type: 'FeatureCollection', features };
}

export interface RouteProps {
	kind: 'segment' | 'hop';
	snr: string;
	cls: SnrClass;
}

/** Traceroute: tramos entre saltos con posición conocida y el SNR de cada salto. */
export function tracerouteCollection(
	tr: Traceroute | null,
	byId: Map<string, Node>,
	formatSnr: (v: number) => string
): FeatureCollection<Point | LineString, RouteProps> {
	if (!tr) return { type: 'FeatureCollection', features: [] };
	const hops = [tr.from, ...tr.route, tr.to];
	const features: Feature<Point | LineString, RouteProps>[] = [];
	for (let i = 0; i < hops.length - 1; i++) {
		const a = byId.get(hops[i]);
		const b = byId.get(hops[i + 1]);
		if (!a || !b || !isValidLatLon(a.lat, a.lon) || !isValidLatLon(b.lat, b.lon)) continue;
		const snr = tr.snr_towards[i] ?? null;
		const ca: [number, number] = [a.lon as number, a.lat as number];
		const cb: [number, number] = [b.lon as number, b.lat as number];
		features.push({
			type: 'Feature',
			geometry: { type: 'LineString', coordinates: [ca, cb] },
			properties: { kind: 'segment', snr: snr === null ? '' : formatSnr(snr), cls: snrClass(snr) }
		});
		features.push({
			type: 'Feature',
			geometry: { type: 'Point', coordinates: [(ca[0] + cb[0]) / 2, (ca[1] + cb[1]) / 2] },
			properties: { kind: 'hop', snr: snr === null ? '?' : formatSnr(snr), cls: snrClass(snr) }
		});
	}
	return { type: 'FeatureCollection', features };
}

export interface WaypointProps {
	id: number;
	name: string;
}

export function waypointsCollection(
	waypoints: Iterable<Waypoint>,
	now: number
): FeatureCollection<Point, WaypointProps> {
	const features: Feature<Point, WaypointProps>[] = [];
	for (const w of waypoints) {
		if (!isValidLatLon(w.lat, w.lon)) continue;
		if (w.expire !== null && w.expire !== undefined && w.expire <= now) continue;
		features.push({
			type: 'Feature',
			id: w.id,
			geometry: { type: 'Point', coordinates: [w.lon as number, w.lat as number] },
			properties: { id: w.id, name: mapLabel(w.name, '') }
		});
	}
	return { type: 'FeatureCollection', features };
}

/** Posiciones en abanico (en píxeles) alrededor de un centro, para nodos superpuestos. */
export function fanOffsets(count: number, minRadius = 34): [number, number][] {
	if (count <= 0) return [];
	const radius = Math.max(minRadius, (count * 26) / (2 * Math.PI));
	const out: [number, number][] = [];
	for (let i = 0; i < count; i++) {
		const angle = -Math.PI / 2 + (i / count) * 2 * Math.PI;
		out.push([radius * Math.cos(angle), radius * Math.sin(angle)]);
	}
	return out;
}

export function nodeStatusCounts(
	features: Feature<Point, NodeProps>[]
): Record<NodeStatus, number> {
	const out: Record<NodeStatus, number> = { active: 0, recent: 0, late: 0, inactive: 0 };
	for (const f of features) out[f.properties.status]++;
	return out;
}
