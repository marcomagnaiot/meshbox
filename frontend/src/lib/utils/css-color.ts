// Resuelve tokens CSS (oklch, lab, colores relativos) a `rgba(...)` para lienzos y MapLibre,
// que no entienden variables ni toda la sintaxis de color moderna.
import { parseOklch, toRgba } from './color';

let probe: HTMLElement | null = null;
let ctx: CanvasRenderingContext2D | null | undefined;

function canvasContext(): CanvasRenderingContext2D | null {
	if (ctx !== undefined) return ctx;
	try {
		const canvas = document.createElement('canvas');
		canvas.width = canvas.height = 1;
		ctx = canvas.getContext('2d', { willReadFrequently: true });
	} catch {
		ctx = null;
	}
	return ctx;
}

/** Color CSS cualquiera (incluida `var(--token)`) → `rgba(r,g,b,a)`. */
export function resolveColor(value: string, fallback = 'rgba(128,128,128,1)'): string {
	if (typeof document === 'undefined') return toRgba(value, fallback);
	if (!probe) {
		probe = document.createElement('span');
		probe.style.display = 'none';
		document.body.appendChild(probe);
	}
	probe.style.color = '';
	probe.style.color = value;
	const computed = getComputedStyle(probe).color || value;
	if (/^rgba?\(/.test(computed)) return computed;
	const ok = parseOklch(computed);
	if (ok) return `rgba(${ok.rgb.join(',')},${ok.alpha})`;
	const c = canvasContext();
	if (!c) return fallback;
	c.clearRect(0, 0, 1, 1);
	c.fillStyle = '#000';
	c.fillStyle = computed;
	c.fillRect(0, 0, 1, 1);
	const [r, g, b, a] = c.getImageData(0, 0, 1, 1).data;
	return `rgba(${r},${g},${b},${+(a / 255).toFixed(3)})`;
}

export function resolveToken(name: string, fallback?: string): string {
	return resolveColor(`var(${name})`, fallback);
}

/** Misma tinta con otra opacidad. */
export function withAlpha(rgba: string, alpha: number): string {
	const m = /rgba?\(([^)]+)\)/.exec(rgba);
	if (!m) return rgba;
	const [r, g, b] = m[1].split(',').map((x) => x.trim());
	return `rgba(${r},${g},${b},${alpha})`;
}
