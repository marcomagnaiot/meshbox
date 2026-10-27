import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { NodeList } from '$lib/api/types';
import { Live, type SourceLike } from './live.svelte';

class FakeSource implements SourceLike {
	static all: FakeSource[] = [];
	readyState = 0;
	onopen: ((ev: Event) => unknown) | null = null;
	onerror: ((ev: Event) => unknown) | null = null;
	listeners = new Map<string, ((ev: MessageEvent) => void)[]>();
	closed = false;

	constructor(public url: string) {
		FakeSource.all.push(this);
	}

	addEventListener(type: string, fn: (ev: MessageEvent) => void) {
		this.listeners.set(type, [...(this.listeners.get(type) ?? []), fn]);
	}

	close() {
		this.closed = true;
		this.readyState = 2;
	}

	open() {
		this.readyState = 1;
		this.onopen?.(new Event('open'));
	}

	emit(type: string, data: unknown) {
		for (const fn of this.listeners.get(type) ?? []) {
			fn(new MessageEvent(type, { data: JSON.stringify(data) }));
		}
	}

	fail(closed: boolean) {
		this.readyState = closed ? 2 : 0;
		this.onerror?.(new Event('error'));
	}
}

const snapshot = (seq: number, ids: string[]): NodeList => ({
	seq,
	ts: Date.now() / 1000,
	nodes: ids.map((id) => ({
		id,
		short_name: null,
		long_name: null,
		role: 'CLIENT',
		hw_model: null,
		lat: null,
		lon: null,
		alt: null,
		precision_m: null,
		battery: null,
		powered: false,
		voltage: null,
		channel_utilization: null,
		air_util_tx: null,
		uptime_s: null,
		last_heard: Date.now() / 1000,
		first_seen: 0,
		hops: null,
		snr: null,
		rssi: null,
		is_infra: false,
		is_gateway: false,
		is_fixed: false,
		env: null
	}))
});

describe('tienda en vivo: conexión y resincronización', () => {
	beforeEach(() => {
		FakeSource.all = [];
		vi.useFakeTimers();
	});

	afterEach(() => {
		vi.useRealTimers();
	});

	it('abre el stream, pide la foto al abrir y queda "en vivo"', async () => {
		const fetchSnapshot = vi.fn(async () => snapshot(5, ['!aaaa0001']));
		const live = new Live({ createSource: (u) => new FakeSource(u), fetchSnapshot });
		live.start('/api/v1/stream?activity=1');
		expect(live.status).toBe('connecting');
		const src = FakeSource.all[0];
		expect(src.url).toBe('/api/v1/stream?activity=1');
		src.open();
		// Llega mientras se pide la foto: se guarda y se aplica después (seq 6 > 5).
		src.emit('node', { seq: 6, ...snapshot(0, ['!aaaa0002']).nodes[0] });
		src.emit('node', { seq: 4, ...snapshot(0, ['!aaaa0009']).nodes[0] }); // ya incluido: se descarta
		await vi.waitFor(() => expect(live.status).toBe('live'));
		expect(fetchSnapshot).toHaveBeenCalledTimes(1);
		expect([...live.nodes.keys()].sort()).toEqual(['!aaaa0001', '!aaaa0002']);
		live.stop();
	});

	it('si se corta y el navegador reconecta, vuelve a pedir la foto', async () => {
		const fetchSnapshot = vi.fn(async () => snapshot(1, ['!aaaa0001']));
		const live = new Live({ createSource: (u) => new FakeSource(u), fetchSnapshot });
		live.start('/s');
		const src = FakeSource.all[0];
		src.open();
		await vi.waitFor(() => expect(live.status).toBe('live'));
		src.fail(false);
		expect(live.status).toBe('reconnecting');
		src.open();
		await vi.waitFor(() => expect(fetchSnapshot).toHaveBeenCalledTimes(2));
		await vi.waitFor(() => expect(live.status).toBe('live'));
		live.stop();
	});

	it('"resync" cierra el stream y abre uno nuevo', async () => {
		const live = new Live({
			createSource: (u) => new FakeSource(u),
			fetchSnapshot: async () => snapshot(1, [])
		});
		live.start('/s');
		const first = FakeSource.all[0];
		first.open();
		await vi.waitFor(() => expect(live.status).toBe('live'));
		first.emit('resync', {});
		expect(first.closed).toBe(true);
		expect(FakeSource.all).toHaveLength(2);
		live.stop();
	});

	it('si el servidor cierra (por ejemplo 429), reintenta con espera creciente', async () => {
		vi.spyOn(Math, 'random').mockReturnValue(0.5); // sin variación aleatoria: 1 s, 2 s, 4 s…
		const live = new Live({
			createSource: (u) => new FakeSource(u),
			fetchSnapshot: async () => snapshot(1, [])
		});
		live.start('/s');
		FakeSource.all[0].fail(true);
		expect(live.status).toBe('reconnecting');
		expect(FakeSource.all).toHaveLength(1);
		await vi.advanceTimersByTimeAsync(1600);
		expect(FakeSource.all).toHaveLength(2);
		FakeSource.all[1].fail(true);
		await vi.advanceTimersByTimeAsync(1600);
		expect(FakeSource.all).toHaveLength(2); // la segunda espera es más larga
		await vi.advanceTimersByTimeAsync(2000);
		expect(FakeSource.all).toHaveLength(3);
		live.stop();
	});

	it('si la foto falla, cierra y reintenta en vez de seguir sin estado', async () => {
		let calls = 0;
		const live = new Live({
			createSource: (u) => new FakeSource(u),
			fetchSnapshot: async () => {
				calls++;
				if (calls === 1) throw new Error('500');
				return snapshot(1, ['!aaaa0001']);
			}
		});
		live.start('/s');
		FakeSource.all[0].open();
		await vi.waitFor(() => expect(FakeSource.all[0].closed).toBe(true));
		await vi.advanceTimersByTimeAsync(1600);
		FakeSource.all[1].open();
		await vi.waitFor(() => expect(live.status).toBe('live'));
		expect(live.nodes.size).toBe(1);
		live.stop();
	});
});
