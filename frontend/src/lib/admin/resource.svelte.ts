// Carga de datos del panel: estado de carga, error RFC 9457, recarga y sondeo mientras la
// pestaña está visible. Cada pedido nuevo cancela el anterior (sin respuestas fuera de orden).
import { toasts } from '$lib/stores/ui.svelte';
import { problemText } from './errors';

export class Resource<T> {
	data = $state.raw<T | null>(null);
	error = $state.raw<unknown>(null);
	loading = $state(false);
	loadedAt = $state<number | null>(null);
	#fetcher: (signal: AbortSignal) => Promise<T>;
	#ctrl: AbortController | null = null;
	#timer: ReturnType<typeof setInterval> | null = null;

	constructor(fetcher: (signal: AbortSignal) => Promise<T>) {
		this.#fetcher = fetcher;
	}

	async load(): Promise<T | null> {
		this.#ctrl?.abort();
		const ctrl = new AbortController();
		this.#ctrl = ctrl;
		this.loading = true;
		try {
			const data = await this.#fetcher(ctrl.signal);
			if (ctrl.signal.aborted) return null;
			this.data = data;
			this.error = null;
			this.loadedAt = Date.now();
			return data;
		} catch (err) {
			if (err instanceof DOMException && err.name === 'AbortError') return null;
			if (!ctrl.signal.aborted) this.error = err;
			return null;
		} finally {
			if (this.#ctrl === ctrl) this.loading = false;
		}
	}

	/** Recarga cada `ms` mientras la pestaña está visible. Devuelve la función para detener. */
	poll(ms: number): () => void {
		this.stopPolling();
		this.#timer = setInterval(() => {
			if (typeof document === 'undefined' || document.visibilityState === 'visible') {
				void this.load();
			}
		}, ms);
		return () => this.stopPolling();
	}

	stopPolling(): void {
		if (this.#timer) clearInterval(this.#timer);
		this.#timer = null;
	}

	dispose(): void {
		this.#ctrl?.abort();
		this.stopPolling();
	}
}

/** Pendiente por clave (botones de cada fila) para deshabilitar mientras se ejecuta. */
export class Busy {
	keys = $state<Record<string, boolean>>({});

	is(key: string): boolean {
		return Boolean(this.keys[key]);
	}

	get any(): boolean {
		return Object.values(this.keys).some(Boolean);
	}

	/** Ejecuta la acción con aviso de éxito o de error. Devuelve el resultado o `undefined`. */
	async run<T>(
		key: string,
		fn: () => Promise<T>,
		opts: { success?: string; quiet?: boolean } = {}
	): Promise<T | undefined> {
		this.keys = { ...this.keys, [key]: true };
		try {
			const out = await fn();
			if (opts.success) toasts.show(opts.success, { kind: 'success' });
			return out;
		} catch (err) {
			if (!opts.quiet) toasts.show(problemText(err), { kind: 'error', timeout: 8000 });
			return undefined;
		} finally {
			const { [key]: _done, ...rest } = this.keys;
			this.keys = rest;
		}
	}
}
