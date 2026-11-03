// Mensajes nuevos de las placas del Cliente Meshtastic (ADR 0022), para la barra del panel, el
// Panel y el título de la pestaña. Se consulta cada 10 s con la pestaña a la vista y cada 60 s
// en segundo plano; el servidor guarda la cuenta hasta que llega un mensaje o cambia lo leído.
import { radioApi, type Inbox, type InboxConv, type InboxMessage } from '$lib/admin/radio';
import { m } from '$lib/paraglide/messages';

const VISIBLE_MS = 10_000;
const HIDDEN_MS = 60_000;

/** Cuenta como se muestra: hasta 99 y después «99+». */
export function countLabel(n: number): string {
	return n > 99 ? '99+' : String(n);
}

/** Enlace a la conversación en el Cliente Meshtastic. */
export function inboxHref(x: { cid: string; conv: string }): string {
	return `/admin/cliente?placa=${encodeURIComponent(x.cid)}&conv=${encodeURIComponent(x.conv)}`;
}

/** «# Canal» o el nombre del nodo de un directo. */
export function convLabel(x: InboxConv): string {
	if (x.dm) return x.name || x.peer || '?';
	return `# ${x.name || m.adm_cli_channel_n({ n: x.channel_index ?? 0 })}`;
}

export function senderLabel(x: InboxMessage): string {
	return x.from_short || x.from_name || x.from || '?';
}

class InboxStore {
	data = $state.raw<Inbox | null>(null);
	#users = 0;
	#timer: ReturnType<typeof setTimeout> | null = null;
	#busy = false;
	#again = false;

	get unread(): number {
		return this.data?.unread ?? 0;
	}

	/** Empieza a consultar (lo llama el layout del panel); devuelve cómo pararlo. */
	start(): () => void {
		this.#users += 1;
		if (this.#users === 1) {
			document.addEventListener('visibilitychange', this.#onVisibility);
			void this.refresh();
		}
		return () => {
			this.#users -= 1;
			if (this.#users > 0) return;
			document.removeEventListener('visibilitychange', this.#onVisibility);
			this.#stopTimer();
			this.data = null;
		};
	}

	/** Consulta ya. Si hay una consulta en curso, se repite al terminar (lo leído recién). */
	async refresh(): Promise<void> {
		if (this.#busy) {
			this.#again = true;
			return;
		}
		this.#busy = true;
		this.#stopTimer();
		try {
			do {
				this.#again = false;
				const data = await radioApi.inbox();
				if (this.#users > 0) this.data = data;
			} while (this.#again);
		} catch {
			// sin red o con la sesión vencida: se reintenta en el próximo turno
		} finally {
			this.#busy = false;
			if (this.#users > 0) {
				const ms = document.visibilityState === 'visible' ? VISIBLE_MS : HIDDEN_MS;
				this.#timer = setTimeout(() => void this.refresh(), ms);
			}
		}
	}

	/** Todo lo que se ve queda leído, en todas las placas. */
	async markAll(): Promise<void> {
		if (!this.data?.upto) return;
		await radioApi.readAll(this.data.upto);
		await this.refresh();
	}

	#onVisibility = (): void => {
		if (document.visibilityState === 'visible') void this.refresh();
	};

	#stopTimer(): void {
		if (this.#timer) clearTimeout(this.#timer);
		this.#timer = null;
	}
}

export const inbox = new InboxStore();
