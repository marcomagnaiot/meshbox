// Núcleo de datos en vivo (sección 12.3), sin dependencias del navegador para probarlo:
//
// 1. Al abrirse el stream se empieza a guardar lo que llega (`beginSync`).
// 2. Se pide la foto `GET /api/v1/nodes`, que trae `seq`.
// 3. Se aplica la foto y después los eventos guardados con `seq` mayor (`applySnapshot`).
// 4. Si el stream se corta o llega `resync`, se repite desde 1.
//
// El estado de nodos vive acá; mensajes, alertas, enlaces y demás se reparten a quien escuche
// (cada tienda deduplica por su clave y vuelve a pedir su lista al resincronizar).
import type {
	LiveEvent,
	LiveEventMap,
	LiveEventName,
	Node,
	NodeList,
	StatsSummary
} from '$lib/api/types';

type Listener<K extends LiveEventName> = (data: LiveEventMap[K]) => void;
type SyncListener = () => void;

/** Eventos que modifican la foto de nodos: se descartan si su `seq` ya está incluido. */
const NODE_EVENTS = new Set<LiveEventName>(['node', 'node_remove', 'position', 'telemetry']);
/** La actividad guardada durante la sincronización se descarta si es más vieja que esto. */
const STALE_ACTIVITY_S = 5;

function stripSeq<T extends { seq?: number }>(data: T): Omit<T, 'seq'> {
	const { seq: _seq, ...rest } = data;
	return rest;
}

export class LiveCore {
	readonly nodes = new Map<string, Node>();
	/** Último `seq` reflejado en `nodes`. */
	seq = 0;
	synced = false;
	summary: StatsSummary | null = null;
	#buffer: LiveEvent[] = [];
	#listeners = new Map<LiveEventName, Set<Listener<LiveEventName>>>();
	#syncListeners = new Set<SyncListener>();

	/** Empieza (o reinicia) la sincronización: lo que llegue se guarda hasta tener la foto. */
	beginSync(): void {
		this.synced = false;
		this.#buffer = [];
	}

	get buffered(): number {
		return this.#buffer.length;
	}

	/**
	 * Recibe un evento del stream. Devuelve `true` si cambió la foto de nodos.
	 * Mientras no hay foto, solo lo guarda.
	 */
	receive(event: LiveEvent): boolean {
		if (!this.synced) {
			this.#buffer.push(event);
			return false;
		}
		return this.#apply(event);
	}

	/**
	 * Aplica la foto y luego los eventos guardados posteriores a ella. Devuelve `true`
	 * (la foto siempre reemplaza el estado anterior).
	 */
	applySnapshot(snapshot: Pick<NodeList, 'seq' | 'nodes'>, nowS = Date.now() / 1000): boolean {
		this.nodes.clear();
		for (const node of snapshot.nodes) this.nodes.set(node.id, node);
		this.seq = snapshot.seq;
		const pending = this.#buffer;
		this.#buffer = [];
		this.synced = true;
		for (const event of pending) {
			if (event.name === 'activity' && nowS - event.data.ts > STALE_ACTIVITY_S) continue;
			this.#apply(event);
		}
		for (const fn of this.#syncListeners) fn();
		return true;
	}

	#apply(event: LiveEvent): boolean {
		const data = event.data as { seq?: number };
		const hasSeq = typeof data.seq === 'number';
		let changed = false;
		if (NODE_EVENTS.has(event.name) && hasSeq) {
			if ((data.seq as number) <= this.seq) return false; // ya incluido en la foto
			changed = this.#applyNodeEvent(event);
		}
		if (hasSeq && (data.seq as number) > this.seq) this.seq = data.seq as number;
		if (event.name === 'stats') this.summary = stripSeq(event.data) as StatsSummary;
		this.#emit(event);
		return changed;
	}

	#applyNodeEvent(event: LiveEvent): boolean {
		switch (event.name) {
			case 'node': {
				const node = stripSeq(event.data) as Node;
				this.nodes.set(node.id, node);
				return true;
			}
			case 'node_remove':
				return this.nodes.delete(event.data.id);
			case 'position': {
				const prev = this.nodes.get(event.data.id);
				if (!prev) return false;
				const { lat, lon, alt, precision_m } = event.data;
				this.nodes.set(prev.id, { ...prev, lat, lon, alt, precision_m });
				return true;
			}
			default:
				return false; // telemetry: el evento `node` siguiente trae los valores nuevos
		}
	}

	on<K extends LiveEventName>(name: K, fn: Listener<K>): () => void {
		let set = this.#listeners.get(name);
		if (!set) {
			set = new Set();
			this.#listeners.set(name, set);
		}
		set.add(fn as Listener<LiveEventName>);
		return () => set.delete(fn as Listener<LiveEventName>);
	}

	/** Se llama después de cada foto aplicada (primera carga y reconexiones). */
	onSync(fn: SyncListener): () => void {
		this.#syncListeners.add(fn);
		return () => this.#syncListeners.delete(fn);
	}

	#emit(event: LiveEvent): void {
		const set = this.#listeners.get(event.name);
		if (!set) return;
		for (const fn of set) {
			try {
				fn(event.data);
			} catch (err) {
				console.error('error en un oyente de', event.name, err);
			}
		}
	}
}

export const LIVE_EVENT_NAMES: readonly LiveEventName[] = [
	'node',
	'node_remove',
	'position',
	'telemetry',
	'message',
	'message_remove',
	'message_restore',
	'alert',
	'link',
	'stats',
	'waypoint',
	'activity'
];
