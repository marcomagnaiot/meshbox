// Agrupado de cambios en el tiempo (16.5: fuentes GeoJSON como máximo cada 500 ms).

export interface Throttled<A extends unknown[]> {
	(...args: A): void;
	flush(): void;
	cancel(): void;
}

/** Llama como máximo una vez cada `ms`, con la última llamada al final del intervalo. */
export function throttle<A extends unknown[]>(fn: (...args: A) => void, ms: number): Throttled<A> {
	let last = 0;
	let timer: ReturnType<typeof setTimeout> | null = null;
	let pending: A | null = null;

	const run = () => {
		timer = null;
		last = Date.now();
		const args = pending;
		pending = null;
		if (args) fn(...args);
	};

	const throttled = ((...args: A) => {
		pending = args;
		const wait = ms - (Date.now() - last);
		if (wait <= 0 && !timer) {
			run();
		} else if (!timer) {
			timer = setTimeout(run, Math.max(0, wait));
		}
	}) as Throttled<A>;

	throttled.flush = () => {
		if (timer) clearTimeout(timer);
		if (pending) run();
		else timer = null;
	};
	throttled.cancel = () => {
		if (timer) clearTimeout(timer);
		timer = null;
		pending = null;
	};
	return throttled;
}

export function debounce<A extends unknown[]>(fn: (...args: A) => void, ms: number): Throttled<A> {
	let timer: ReturnType<typeof setTimeout> | null = null;
	let pending: A | null = null;
	const debounced = ((...args: A) => {
		pending = args;
		if (timer) clearTimeout(timer);
		timer = setTimeout(() => {
			timer = null;
			const a = pending;
			pending = null;
			if (a) fn(...a);
		}, ms);
	}) as Throttled<A>;
	debounced.flush = () => {
		if (timer) clearTimeout(timer);
		timer = null;
		const a = pending;
		pending = null;
		if (a) fn(...a);
	};
	debounced.cancel = () => {
		if (timer) clearTimeout(timer);
		timer = null;
		pending = null;
	};
	return debounced;
}
