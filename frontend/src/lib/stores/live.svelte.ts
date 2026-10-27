// Tienda central de datos en vivo: abre el SSE, sincroniza con la foto de nodos (LiveCore) y
// expone estado reactivo para el mapa y las listas. Indicador "en vivo" / "reconectando" /
// "sin conexión".
import { publicApi } from '$lib/api/public';
import type {
	ActivityEvent,
	LiveEvent,
	LiveEventName,
	Node,
	NodeList,
	StatsSummary
} from '$lib/api/types';
import { clock } from './clock.svelte';
import { LIVE_EVENT_NAMES, LiveCore } from './live-core';

export type LiveStatus = 'connecting' | 'live' | 'reconnecting' | 'offline';

/** Lo mínimo de EventSource que se usa (permite inyectar uno falso en pruebas). */
export interface SourceLike {
	readonly readyState: number;
	onopen: ((ev: Event) => unknown) | null;
	onerror: ((ev: Event) => unknown) | null;
	addEventListener(type: string, listener: (ev: MessageEvent) => void): void;
	close(): void;
}

export interface LiveDeps {
	createSource: (url: string) => SourceLike;
	fetchSnapshot: () => Promise<NodeList>;
	fetchSummary?: () => Promise<StatsSummary>;
}

const CLOSED = 2;
const MAX_BACKOFF_MS = 30_000;
const ACTIVITY_KEEP = 40;

const defaultDeps = (): LiveDeps => ({
	createSource: (url) => new EventSource(url),
	fetchSnapshot: () => publicApi.nodes(),
	fetchSummary: () => publicApi.summary()
});

export class Live {
	readonly core = new LiveCore();
	status = $state<LiveStatus>('connecting');
	/** Sube cuando cambia la foto de nodos (agrupado cada 200 ms). */
	version = $state(0);
	summary = $state.raw<StatsSummary | null>(null);
	activity = $state.raw<ActivityEvent[]>([]);
	lastEventAt = $state(0);
	/** Hubo al menos una sincronización (hay datos que mostrar). */
	hasData = $state(false);

	#deps: LiveDeps;
	#url = '';
	#source: SourceLike | null = null;
	#attempt = 0;
	#retryTimer: ReturnType<typeof setTimeout> | null = null;
	#bumpTimer: ReturnType<typeof setTimeout> | null = null;
	#syncToken = 0;
	#started = false;

	constructor(deps?: Partial<LiveDeps>) {
		this.#deps = { ...defaultDeps(), ...deps };
		this.core.on('stats', (s) => {
			const { seq: _seq, ...summary } = s;
			this.summary = summary;
		});
		this.core.on('activity', (a) => {
			this.activity = [a, ...this.activity].slice(0, ACTIVITY_KEEP);
		});
	}

	get nodes(): Map<string, Node> {
		return this.core.nodes;
	}

	/** Lista de nodos; leerla dentro de un `$derived` la vuelve reactiva. */
	nodeList(): Node[] {
		void this.version;
		return [...this.core.nodes.values()];
	}

	node(id: string | null | undefined): Node | undefined {
		void this.version;
		return id ? this.core.nodes.get(id) : undefined;
	}

	start(url = '/api/v1/stream?activity=1'): void {
		if (this.#started) return;
		this.#started = true;
		this.#url = url;
		this.#open();
		if (typeof window !== 'undefined') {
			window.addEventListener('online', this.#onOnline);
			window.addEventListener('offline', this.#onOffline);
			document.addEventListener('visibilitychange', this.#onVisible);
		}
	}

	stop(): void {
		this.#started = false;
		this.#close();
		if (this.#retryTimer) clearTimeout(this.#retryTimer);
		this.#retryTimer = null;
		if (typeof window !== 'undefined') {
			window.removeEventListener('online', this.#onOnline);
			window.removeEventListener('offline', this.#onOffline);
			document.removeEventListener('visibilitychange', this.#onVisible);
		}
	}

	/** Cierra y vuelve a abrir el stream (evento `resync` o pedido del usuario). */
	restart(): void {
		this.#close();
		this.#attempt = 0;
		this.status = this.hasData ? 'reconnecting' : 'connecting';
		this.#open();
	}

	#open(): void {
		const source = this.#deps.createSource(this.#url);
		this.#source = source;
		source.onopen = () => {
			if (this.#source !== source) return;
			this.#attempt = 0;
			this.#sync(source);
		};
		source.onerror = () => {
			if (this.#source !== source) return;
			this.core.beginSync();
			const online = typeof navigator === 'undefined' || navigator.onLine !== false;
			if (source.readyState === CLOSED) {
				// El navegador no reintenta (respuesta no 200, por ejemplo 429): reintento propio.
				this.status = online ? 'reconnecting' : 'offline';
				this.#scheduleRetry();
			} else {
				this.status = online ? 'reconnecting' : 'offline';
			}
		};
		for (const name of LIVE_EVENT_NAMES) {
			source.addEventListener(name, (ev) => this.#onMessage(name, ev));
		}
		source.addEventListener('resync', () => {
			if (this.#source === source) this.restart();
		});
	}

	#close(): void {
		this.#source?.close();
		this.#source = null;
		this.core.beginSync();
	}

	#scheduleRetry(): void {
		this.#source?.close();
		this.#source = null;
		if (this.#retryTimer || !this.#started) return;
		const delay = Math.min(MAX_BACKOFF_MS, 1000 * 2 ** this.#attempt) * (0.75 + Math.random() / 2);
		this.#attempt++;
		this.#retryTimer = setTimeout(() => {
			this.#retryTimer = null;
			if (this.#started) this.#open();
		}, delay);
	}

	async #sync(source: SourceLike): Promise<void> {
		const token = ++this.#syncToken;
		this.core.beginSync();
		try {
			const snapshot = await this.#deps.fetchSnapshot();
			if (token !== this.#syncToken || this.#source !== source) return;
			clock.syncWithServer(snapshot.ts);
			this.core.applySnapshot(snapshot, clock.exact());
			this.hasData = true;
			this.status = 'live';
			this.#bump(true);
			// El resumen llega por el stream cada 30 s; al sincronizar se pide uno al momento.
			if (this.#deps.fetchSummary) {
				this.#deps
					.fetchSummary()
					.then((s) => {
						if (!this.core.summary) this.summary = s;
					})
					.catch(() => undefined);
			}
		} catch {
			if (token !== this.#syncToken || this.#source !== source) return;
			// Sin foto no se puede seguir el flujo: cerrar y reintentar con espera creciente.
			this.status =
				typeof navigator !== 'undefined' && !navigator.onLine ? 'offline' : 'reconnecting';
			this.#scheduleRetry();
		}
	}

	#onMessage(name: LiveEventName, ev: MessageEvent): void {
		let data: unknown;
		try {
			data = JSON.parse(String(ev.data));
		} catch {
			return;
		}
		this.lastEventAt = Date.now();
		const changed = this.core.receive({ name, data } as LiveEvent);
		if (changed) this.#bump();
	}

	#bump(now = false): void {
		if (now) {
			if (this.#bumpTimer) clearTimeout(this.#bumpTimer);
			this.#bumpTimer = null;
			this.version++;
			return;
		}
		if (this.#bumpTimer) return;
		this.#bumpTimer = setTimeout(() => {
			this.#bumpTimer = null;
			this.version++;
		}, 200);
	}

	#onOnline = () => {
		if (this.status !== 'live') {
			if (this.#retryTimer) clearTimeout(this.#retryTimer);
			this.#retryTimer = null;
			this.restart();
		}
	};

	#onOffline = () => {
		this.status = 'offline';
	};

	#onVisible = () => {
		if (document.visibilityState === 'visible' && this.status !== 'live' && !this.#retryTimer) {
			this.restart();
		}
	};
}

export const live = new Live();
