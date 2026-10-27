import { describe, expect, it } from 'vitest';
import type { Link, Node, Position, Traceroute } from '$lib/api/types';
import { EMPTY_FILTER } from '$lib/utils/nodes';
import {
	fanOffsets,
	iconName,
	linksCollection,
	nodeLabel,
	nodesCollection,
	trackCollection,
	tracerouteCollection,
	uncertaintyCollection
} from './geojson';

const T = { active_s: 3600, recent_s: 7200, late_s: 86400 };
const NOW = 1_800_000_000;

function node(id: string, extra: Partial<Node> = {}): Node {
	return {
		id,
		short_name: 'NODO',
		long_name: 'Nodo',
		role: 'CLIENT',
		hw_model: null,
		lat: -40.8,
		lon: -63,
		alt: null,
		precision_m: null,
		battery: null,
		powered: false,
		voltage: null,
		channel_utilization: null,
		air_util_tx: null,
		uptime_s: null,
		last_heard: NOW - 60,
		first_seen: 0,
		hops: null,
		snr: null,
		rssi: null,
		is_infra: false,
		is_gateway: false,
		is_fixed: false,
		env: null,
		...extra
	};
}

describe('capa de nodos', () => {
	it('solo nodos con posición; inactivos ocultos por defecto; ícono por estado y anillos', () => {
		const nodes = [
			node('!00000001', { is_infra: true, is_fixed: true }),
			node('!00000002', { last_heard: NOW - 3 * 3600 }),
			node('!00000003', { last_heard: NOW - 3 * 86400 }),
			node('!00000004', { lat: null, lon: null })
		];
		const fc = nodesCollection(nodes, EMPTY_FILTER, NOW, T);
		expect(fc.features.map((f) => f.properties.id)).toEqual(['!00000001', '!00000002']);
		expect(fc.features[0].properties.icon).toBe('node-active-11');
		expect(fc.features[1].properties.icon).toBe('node-late-00');
		expect(fc.features[0].id).toBe(1); // id numérico para feature-state
		const withInactive = nodesCollection(nodes, { ...EMPTY_FILTER, showInactive: true }, NOW, T);
		expect(withInactive.features).toHaveLength(3);
	});

	it('las etiquetas no usan glifos que no se publican (emojis)', () => {
		expect(nodeLabel({ id: '!0000abcd', short_name: '🚀CR', long_name: null })).toBe('CR');
		expect(nodeLabel({ id: '!0000abcd', short_name: '🚀', long_name: '🔥' })).toBe('abcd');
		expect(nodeLabel({ id: '!0000abcd', short_name: 'Ñandú', long_name: null })).toBe('Ñandú');
	});

	it('incertidumbre solo con precisión razonable', () => {
		const nodes = [node('!00000001', { precision_m: 500 }), node('!00000002', { precision_m: 0 })];
		const fc = nodesCollection(nodes, EMPTY_FILTER, NOW, T);
		const u = uncertaintyCollection(fc, new Map(nodes.map((n) => [n.id, n])));
		expect(u.features).toHaveLength(1);
		expect(u.features[0].geometry.coordinates[0].length).toBeGreaterThan(20);
	});

	it('iconName', () => {
		expect(iconName('recent', false, true)).toBe('node-recent-01');
	});
});

describe('capa de enlaces', () => {
	const a = node('!0000000a', { lat: -40.8, lon: -63 });
	const b = node('!0000000b', { lat: -40.9, lon: -63.1 });
	const byId = new Map([a, b].map((n) => [n.id, n]));
	const link = (extra: Partial<Link>): Link => ({
		a: a.id,
		b: b.id,
		snr: 6,
		source: 'direct',
		ts: NOW - 100,
		...extra
	});

	it('un enlace por par (el más reciente), con clase por SNR y recencia', () => {
		const fc = linksCollection(
			[link({ snr: -3, ts: NOW - 5000 }), link({ a: b.id, b: a.id, snr: 2, ts: NOW - 10 })],
			byId,
			NOW
		);
		expect(fc.features).toHaveLength(1);
		expect(fc.features[0].properties.cls).toBe('fair');
		expect(fc.features[0].properties.recency).toBeGreaterThan(0.99);
	});

	it('sin posición, viejo o con un extremo oculto no se dibuja', () => {
		const noPos = new Map(byId);
		noPos.set(b.id, { ...b, lat: null, lon: null });
		expect(linksCollection([link({})], noPos, NOW).features).toHaveLength(0);
		expect(linksCollection([link({ ts: NOW - 2 * 86400 })], byId, NOW).features).toHaveLength(0);
		expect(linksCollection([link({})], byId, NOW, new Set([a.id])).features).toHaveLength(0);
	});
});

describe('recorrido y traceroute', () => {
	it('línea, inicio, fin, puntos horarios y cursor de reproducción', () => {
		const pts: Position[] = [0, 600, 1200, 4000, 8000].map((dt, i) => ({
			ts: NOW + dt,
			lat: -40.8 - i * 0.01,
			lon: -63,
			alt: null,
			precision_m: null,
			speed_kmh: null
		}));
		const fc = trackCollection(pts, 2);
		const kinds = fc.features.map((f) => f.properties.kind);
		expect(kinds[0]).toBe('line');
		expect(kinds).toContain('start');
		expect(kinds).toContain('end');
		expect(kinds.filter((k) => k === 'cursor')).toHaveLength(1);
		expect(trackCollection(pts.slice(0, 1), null).features.map((f) => f.properties.kind)).toEqual([
			'start'
		]);
	});

	it('traceroute con SNR por salto y saltos sin posición omitidos', () => {
		const nodes = new Map(
			[
				node('!00000001'),
				node('!00000002', { lat: -40.9 }),
				node('!00000003', { lat: null, lon: null })
			].map((n) => [n.id, n])
		);
		const tr: Traceroute = {
			ts: NOW,
			from: '!00000001',
			to: '!00000003',
			route: ['!00000002'],
			snr_towards: [4.5, -2],
			route_back: [],
			snr_back: []
		};
		const fc = tracerouteCollection(tr, nodes, (v) => `${v} dB`);
		expect(fc.features.filter((f) => f.properties.kind === 'segment')).toHaveLength(1);
		expect(fc.features.find((f) => f.properties.kind === 'hop')?.properties.snr).toBe('4.5 dB');
		expect(tracerouteCollection(null, nodes, String).features).toHaveLength(0);
	});
});

describe('abanico de nodos superpuestos', () => {
	it('reparte los nodos alrededor del centro sin superponerlos', () => {
		const pos = fanOffsets(8);
		expect(pos).toHaveLength(8);
		const dist = Math.hypot(pos[0][0] - pos[1][0], pos[0][1] - pos[1][1]);
		expect(dist).toBeGreaterThan(20);
		expect(fanOffsets(0)).toEqual([]);
	});
});
