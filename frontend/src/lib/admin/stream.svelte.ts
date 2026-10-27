// Stream del panel (12.3): /api/v1/admin/stream con paquetes, registros, conectores, sistema,
// diagnósticos, alertas y traceroutes. EventSource reconecta solo; con la sesión vencida el
// servidor responde 401 y el estado queda en "error" (el layout lleva al inicio de sesión).
import { buildUrl, type QueryValue } from '$lib/api/client';

export type StreamStatus = 'closed' | 'connecting' | 'open' | 'error';

type Handler = (data: unknown) => void;

export class AdminStream {
	status = $state<StreamStatus>('closed');
	#es: EventSource | null = null;
	#handlers: Record<string, Handler>;

	constructor(handlers: Record<string, Handler>) {
		this.#handlers = handlers;
	}

	open(query: Record<string, QueryValue>): void {
		this.close();
		if (typeof EventSource === 'undefined') {
			this.status = 'error';
			return;
		}
		const es = new EventSource(buildUrl('/api/v1/admin/stream', query), { withCredentials: true });
		this.#es = es;
		this.status = 'connecting';
		es.onopen = () => {
			if (this.#es === es) this.status = 'open';
		};
		es.onerror = () => {
			if (this.#es !== es) return;
			this.status = es.readyState === EventSource.CLOSED ? 'error' : 'connecting';
		};
		for (const [name, fn] of Object.entries(this.#handlers)) {
			es.addEventListener(name, (ev) => {
				try {
					fn(JSON.parse((ev as MessageEvent<string>).data));
				} catch {
					// evento mal formado: se ignora
				}
			});
		}
	}

	close(): void {
		this.#es?.close();
		this.#es = null;
		this.status = 'closed';
	}
}
