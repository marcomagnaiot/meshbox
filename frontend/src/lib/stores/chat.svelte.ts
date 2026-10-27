// Chat del canal público: páginas de `GET /api/v1/messages` (cursor `next`) más los eventos
// `message`, `message_remove` y `message_restore` del stream. Deduplica por `pk`.
import { publicApi } from '$lib/api/public';
import type { Message, MessageEvent } from '$lib/api/types';
import { live } from './live.svelte';

const PAGE = 50;

class ChatStore {
	messages = $state.raw<Map<number, Message>>(new Map());
	next = $state<string | null>(null);
	loading = $state(false);
	loadingOlder = $state(false);
	loaded = $state(false);
	error = $state<unknown>(null);
	/** Último mensaje recibido en vivo (para anunciarlo con aria-live). */
	latestLive = $state.raw<Message | null>(null);
	#bound = false;

	#bind(): void {
		if (this.#bound) return;
		this.#bound = true;
		live.core.on('message', (ev: MessageEvent) => {
			const { seq: _seq, ...msg } = ev;
			if (this.messages.has(msg.pk)) return;
			const map = new Map(this.messages);
			map.set(msg.pk, msg);
			this.messages = map;
			this.latestLive = msg;
		});
		live.core.on('message_remove', ({ pk }) => {
			if (!this.messages.has(pk)) return;
			const map = new Map(this.messages);
			map.delete(pk);
			this.messages = map;
		});
		// Un mensaje restaurado solo trae `pk`: se vuelve a pedir la primera página.
		live.core.on('message_restore', () => void this.refresh());
		// Tras una reconexión pudo haberse perdido algo: completar con la primera página.
		live.core.onSync(() => {
			if (this.loaded) void this.refresh();
		});
	}

	#merge(list: Message[]): void {
		const map = new Map(this.messages);
		for (const m of list) map.set(m.pk, m);
		this.messages = map;
	}

	async load(): Promise<void> {
		this.#bind();
		if (this.loaded || this.loading) return;
		this.loading = true;
		this.error = null;
		try {
			const page = await publicApi.messages(null, PAGE);
			this.#merge(page.messages);
			this.next = page.next ?? null;
			this.loaded = true;
		} catch (err) {
			this.error = err;
		} finally {
			this.loading = false;
		}
	}

	async refresh(): Promise<void> {
		try {
			const page = await publicApi.messages(null, PAGE);
			// Reemplaza lo reciente para reflejar moderaciones; conserva lo más viejo ya cargado.
			const oldest = page.messages.at(-1)?.ts ?? Infinity;
			const map = new Map<number, Message>();
			for (const m of this.messages.values()) if (m.ts < oldest) map.set(m.pk, m);
			for (const m of page.messages) map.set(m.pk, m);
			this.messages = map;
			if (!this.next) this.next = page.next ?? null;
		} catch {
			// se reintentará en la próxima sincronización
		}
	}

	async loadOlder(): Promise<void> {
		if (!this.next || this.loadingOlder) return;
		this.loadingOlder = true;
		try {
			const page = await publicApi.messages(this.next, PAGE);
			this.#merge(page.messages);
			this.next = page.next ?? null;
		} catch (err) {
			this.error = err;
		} finally {
			this.loadingOlder = false;
		}
	}
}

export const chat = new ChatStore();
