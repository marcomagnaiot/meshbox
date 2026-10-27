// Detección de rendimiento (16.1.9): si al arrastrar el mapa se miden menos de 40 cuadros/s
// sostenidos durante 3 s, se sugiere el modo sólido una sola vez.

export const FPS_THRESHOLD = 40;
export const SUSTAINED_S = 3;

/** Evalúa ventanas de 1 s: devuelve true cuando hay `SUSTAINED_S` ventanas lentas seguidas. */
export class FpsJudge {
	#slow = 0;

	/** Agrega una ventana de un segundo con `frames` cuadros dibujados. */
	addWindow(frames: number, seconds = 1): boolean {
		const fps = frames / seconds;
		this.#slow = fps < FPS_THRESHOLD ? this.#slow + 1 : 0;
		return this.#slow >= SUSTAINED_S;
	}

	reset(): void {
		this.#slow = 0;
	}
}

/** Cuenta cuadros con requestAnimationFrame mientras dura el arrastre. */
export class DragFpsMonitor {
	#judge = new FpsJudge();
	#frames = 0;
	#windowStart = 0;
	#raf = 0;
	#active = false;
	#onSlow: () => void;
	#fired = false;

	constructor(onSlow: () => void) {
		this.#onSlow = onSlow;
	}

	start(): void {
		if (this.#active || this.#fired) return;
		this.#active = true;
		this.#frames = 0;
		this.#windowStart = performance.now();
		this.#raf = requestAnimationFrame(this.#tick);
	}

	stop(): void {
		this.#active = false;
		cancelAnimationFrame(this.#raf);
		// Las ventanas lentas deben ser seguidas y durante el arrastre: soltar reinicia la cuenta.
		this.#judge.reset();
	}

	#tick = (now: number) => {
		if (!this.#active) return;
		this.#frames++;
		const elapsed = now - this.#windowStart;
		if (elapsed >= 1000) {
			if (this.#judge.addWindow(this.#frames, elapsed / 1000)) {
				this.#fired = true;
				this.stop();
				this.#onSlow();
				return;
			}
			this.#frames = 0;
			this.#windowStart = now;
		}
		this.#raf = requestAnimationFrame(this.#tick);
	};
}
