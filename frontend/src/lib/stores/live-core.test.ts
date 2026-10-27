import { describe, expect, it, vi } from 'vitest';
import type { LiveEvent, Node } from '$lib/api/types';
import { LiveCore } from './live-core';

function node(id: string, extra: Partial<Node> = {}): Node {
	return {
		id,
		short_name: id.slice(-4),
		long_name: `Nodo ${id}`,
		role: 'CLIENT',
		hw_model: null,
		lat: -40.8,
		lon: -63,
		alt: null,
		precision_m: null,
		battery: 80,
		powered: false,
		voltage: null,
		channel_utilization: null,
		air_util_tx: null,
		uptime_s: null,
		last_heard: 1000,
		first_seen: 900,
		hops: 1,
		snr: 5,
		rssi: -90,
		is_infra: false,
		is_gateway: false,
		is_fixed: false,
		env: null,
		...extra
	};
}

const ev = (name: LiveEvent['name'], data: object) => ({ name, data }) as LiveEvent;

describe('fusión de la foto y los eventos por seq (12.3)', () => {
	it('guarda los eventos hasta tener la foto y aplica solo los posteriores', () => {
		const core = new LiveCore();
		core.beginSync();
		// Llegan antes de la foto: dos ya incluidos (seq ≤ 10) y dos nuevos.
		expect(core.receive(ev('node', { seq: 9, ...node('!aaaa0001', { battery: 1 }) }))).toBe(false);
		core.receive(ev('node', { seq: 10, ...node('!aaaa0002', { battery: 2 }) }));
		core.receive(ev('node', { seq: 11, ...node('!aaaa0001', { battery: 50 }) }));
		core.receive(ev('node', { seq: 12, ...node('!aaaa0003') }));
		expect(core.buffered).toBe(4);

		core.applySnapshot({
			seq: 10,
			nodes: [node('!aaaa0001', { battery: 40 }), node('!aaaa0002', { battery: 30 })]
		});

		expect(core.buffered).toBe(0);
		expect(core.seq).toBe(12);
		expect(core.nodes.get('!aaaa0001')?.battery).toBe(50); // seq 11 > 10: se aplica
		expect(core.nodes.get('!aaaa0002')?.battery).toBe(30); // seq 10 ≤ 10: ya estaba en la foto
		expect(core.nodes.has('!aaaa0003')).toBe(true);
		expect(core.nodes.get('!aaaa0001')).not.toHaveProperty('seq');
	});

	it('después de sincronizar ignora eventos de nodos con seq ya visto', () => {
		const core = new LiveCore();
		core.beginSync();
		core.applySnapshot({ seq: 20, nodes: [node('!aaaa0001')] });
		expect(core.receive(ev('node', { seq: 20, ...node('!aaaa0001', { battery: 5 }) }))).toBe(false);
		expect(core.receive(ev('node', { seq: 21, ...node('!aaaa0001', { battery: 6 }) }))).toBe(true);
		expect(core.nodes.get('!aaaa0001')?.battery).toBe(6);
	});

	it('node_remove oculta el nodo y position actualiza la posición', () => {
		const core = new LiveCore();
		core.beginSync();
		core.applySnapshot({ seq: 1, nodes: [node('!aaaa0001'), node('!aaaa0002')] });
		core.receive(
			ev('position', {
				seq: 2,
				id: '!aaaa0001',
				lat: -41,
				lon: -62,
				alt: 5,
				precision_m: 23,
				ts: 2000
			})
		);
		expect(core.nodes.get('!aaaa0001')).toMatchObject({
			lat: -41,
			lon: -62,
			alt: 5,
			precision_m: 23
		});
		core.receive(ev('node_remove', { seq: 3, id: '!aaaa0002' }));
		expect(core.nodes.has('!aaaa0002')).toBe(false);
		// Posición de un nodo desconocido: no inventa nodos.
		expect(
			core.receive(
				ev('position', {
					seq: 4,
					id: '!ffff0000',
					lat: 1,
					lon: 1,
					alt: null,
					precision_m: null,
					ts: 1
				})
			)
		).toBe(false);
	});

	it('reconexión: la foto nueva reemplaza todo el estado anterior', () => {
		const core = new LiveCore();
		core.beginSync();
		core.applySnapshot({ seq: 5, nodes: [node('!aaaa0001'), node('!aaaa0002')] });
		core.beginSync();
		core.receive(ev('node', { seq: 7, ...node('!aaaa0003') }));
		core.applySnapshot({ seq: 6, nodes: [node('!aaaa0001')] });
		expect([...core.nodes.keys()].sort()).toEqual(['!aaaa0001', '!aaaa0003']);
	});

	it('reparte mensajes, alertas y estadísticas a quien escucha, y avisa cada sincronización', () => {
		const core = new LiveCore();
		const onMessage = vi.fn();
		const onSync = vi.fn();
		core.on('message', onMessage);
		core.onSync(onSync);
		core.beginSync();
		core.receive(
			ev('message', {
				seq: 3,
				pk: 1,
				ts: 1,
				from: '!aaaa0001',
				from_name: null,
				channel: 'LongFast',
				text: 'hola',
				reply_id: null,
				emoji: false
			})
		);
		expect(onMessage).not.toHaveBeenCalled(); // todavía sin foto
		core.applySnapshot({ seq: 2, nodes: [] });
		expect(onMessage).toHaveBeenCalledTimes(1);
		expect(onSync).toHaveBeenCalledTimes(1);
		core.receive(
			ev('stats', {
				seq: 4,
				nodes: { total: 3 },
				packets_last_hour: 9,
				channel_utilization_avg: null,
				new_nodes_24h: 0,
				last_packet_at: 10,
				ts: 11
			})
		);
		expect(core.summary?.packets_last_hour).toBe(9);
	});

	it('la actividad guardada durante la sincronización se descarta si es vieja', () => {
		const core = new LiveCore();
		const onActivity = vi.fn();
		core.on('activity', onActivity);
		core.beginSync();
		core.receive(
			ev('activity', {
				portnum: 'POSITION_APP',
				from: '!aaaa0001',
				to: '^all',
				hops: 0,
				snr: 1,
				gateway: null,
				ts: 100
			})
		);
		core.receive(
			ev('activity', {
				portnum: 'POSITION_APP',
				from: '!aaaa0001',
				to: '^all',
				hops: 0,
				snr: 1,
				gateway: null,
				ts: 198
			})
		);
		core.applySnapshot({ seq: 1, nodes: [] }, 200);
		expect(onActivity).toHaveBeenCalledTimes(1);
	});

	it('un oyente que falla no corta a los demás', () => {
		const core = new LiveCore();
		const ok = vi.fn();
		const spy = vi.spyOn(console, 'error').mockImplementation(() => {});
		core.on('alert', () => {
			throw new Error('boom');
		});
		core.on('alert', ok);
		core.beginSync();
		core.applySnapshot({ seq: 0, nodes: [] });
		core.receive(
			ev('alert', {
				seq: 1,
				id: 1,
				state: 'firing',
				severity: 'critical',
				kind: 'keyword',
				node: null,
				title: 'SOS',
				body: null,
				ts: 1
			})
		);
		expect(ok).toHaveBeenCalled();
		expect(spy).toHaveBeenCalled();
	});
});
