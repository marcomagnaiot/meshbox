// Doble confirmación de los cambios peligrosos de la placa (ADR 0015): el primer intento va sin
// confirmar; si el servidor responde 409 danger_confirmation_required, se abre el diálogo con
// los campos y, al confirmar, se repite con confirm_danger.
import { dangerFields } from '$lib/admin/radio';

export class DangerGate {
	open = $state(false);
	fields = $state<string[]>([]);
	#retry: (() => Promise<unknown>) | null = null;
	#done: ((result: unknown) => void) | null = null;

	/** Corre `first`; si hace falta confirmar, guarda `confirmed` para el diálogo. */
	async run<T>(
		first: () => Promise<T>,
		confirmed: () => Promise<T>,
		done: (result: T) => void
	): Promise<void> {
		try {
			done(await first());
		} catch (err) {
			const fields = dangerFields(err);
			if (fields === null) throw err;
			this.fields = fields;
			this.#retry = confirmed;
			this.#done = done as (result: unknown) => void;
			this.open = true;
		}
	}

	confirm = async (): Promise<unknown> => {
		if (!this.#retry) return null;
		const result = await this.#retry();
		this.#done?.(result);
		return result;
	};
}
