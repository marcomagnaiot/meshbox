// Reloj compartido en segundos Unix, corregido con la hora del servidor (la foto de
// `/api/v1/nodes` trae `ts`): los estados y "hace 12 min" no dependen del reloj del equipo.

class Clock {
	/** Diferencia servidor − equipo, en segundos. */
	offset = $state(0);
	#tick = $state(Date.now() / 1000);
	#timer: ReturnType<typeof setInterval> | null = null;

	/** Ahora (segundos), se actualiza cada 15 s para refrescar estados y tiempos relativos. */
	get now(): number {
		return this.#tick + this.offset;
	}

	/** Ahora exacto, sin esperar el próximo tic (para cálculos puntuales). */
	exact(): number {
		return Date.now() / 1000 + this.offset;
	}

	syncWithServer(serverTs: number): void {
		if (!Number.isFinite(serverTs)) return;
		const local = Date.now() / 1000;
		this.offset = serverTs - local;
		this.#tick = local;
	}

	start(intervalMs = 15_000): void {
		if (this.#timer) return;
		this.#timer = setInterval(() => (this.#tick = Date.now() / 1000), intervalMs);
	}

	stop(): void {
		if (this.#timer) clearInterval(this.#timer);
		this.#timer = null;
	}
}

export const clock = new Clock();
