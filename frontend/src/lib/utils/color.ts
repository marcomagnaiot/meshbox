// Colores: los tokens están en OKLCH (16.2) pero MapLibre y el lienzo de los íconos necesitan
// sRGB. Conversión OKLCH → OKLab → sRGB lineal → sRGB (Björn Ottosson).

export type Rgb = [number, number, number];

const clamp01 = (x: number) => Math.min(1, Math.max(0, x));
const toGamma = (c: number) => (c <= 0.0031308 ? 12.92 * c : 1.055 * c ** (1 / 2.4) - 0.055);
const toLinear = (c: number) => (c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4);

/** `L` en 0-1, `C` croma, `h` en grados → sRGB 0-255 (recortado a la gama). */
export function oklchToRgb(L: number, C: number, h: number): Rgb {
	const hr = (h * Math.PI) / 180;
	const a = C * Math.cos(hr);
	const b = C * Math.sin(hr);
	const l = (L + 0.3963377774 * a + 0.2158037573 * b) ** 3;
	const m = (L - 0.1055613458 * a - 0.0638541728 * b) ** 3;
	const s = (L - 0.0894841775 * a - 1.291485548 * b) ** 3;
	const r = 4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s;
	const g = -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s;
	const bl = -0.0041960863 * l - 0.7034186147 * m + 1.707614701 * s;
	return [r, g, bl].map((c) => Math.round(clamp01(toGamma(c)) * 255)) as Rgb;
}

/** sRGB 0-255 → OKLCH: `L` en 0-1, `C` croma, `h` en grados (la inversa de `oklchToRgb`). */
export function rgbToOklch([r, g, b]: Rgb): { L: number; C: number; h: number } {
	const [R, G, B] = [r, g, b].map((x) => toLinear(x / 255));
	const l = Math.cbrt(0.4122214708 * R + 0.5363325363 * G + 0.0514459929 * B);
	const m = Math.cbrt(0.2119034982 * R + 0.6806995451 * G + 0.1073969566 * B);
	const s = Math.cbrt(0.0883024619 * R + 0.2817188376 * G + 0.6299787005 * B);
	const L = 0.2104542553 * l + 0.793617785 * m - 0.0040720468 * s;
	const a = 1.9779984951 * l - 2.428592205 * m + 0.4505937099 * s;
	const bb = 0.0259040371 * l + 0.7827717662 * m - 0.808675766 * s;
	const h = ((Math.atan2(bb, a) * 180) / Math.PI + 360) % 360;
	return { L, C: Math.hypot(a, bb), h };
}

export function rgbToHex([r, g, b]: Rgb): string {
	return '#' + [r, g, b].map((x) => x.toString(16).padStart(2, '0')).join('');
}

export function hexToRgb(hex: string): Rgb | null {
	const m = /^#?([0-9a-f]{3}|[0-9a-f]{6})$/i.exec(hex.trim());
	if (!m) return null;
	let h = m[1];
	if (h.length === 3) h = [...h].map((c) => c + c).join('');
	return [0, 2, 4].map((i) => parseInt(h.slice(i, i + 2), 16)) as Rgb;
}

/** Interpreta `oklch(78% 0.17 150)` o `oklch(0.78 0.17 150 / 0.5)`. */
export function parseOklch(value: string): { rgb: Rgb; alpha: number } | null {
	const m =
		/oklch\(\s*([\d.]+)(%?)\s+([\d.]+)\s+([\d.]+)(?:deg)?\s*(?:\/\s*([\d.]+)(%?))?\s*\)/i.exec(
			value
		);
	if (!m) return null;
	const L = m[2] ? Number(m[1]) / 100 : Number(m[1]);
	const alpha = m[5] === undefined ? 1 : m[6] ? Number(m[5]) / 100 : Number(m[5]);
	return { rgb: oklchToRgb(L, Number(m[3]), Number(m[4])), alpha };
}

/** Color CSS (hex u oklch) → `rgba(...)` que entienden MapLibre y canvas en cualquier navegador. */
export function toRgba(value: string, fallback = '#888888'): string {
	const ok = parseOklch(value);
	if (ok) return `rgba(${ok.rgb.join(',')},${ok.alpha})`;
	const rgb = hexToRgb(value);
	if (rgb) return `rgb(${rgb.join(',')})`;
	return fallback;
}

export function relativeLuminance([r, g, b]: Rgb): number {
	const [R, G, B] = [r, g, b].map((x) => toLinear(x / 255));
	return 0.2126 * R + 0.7152 * G + 0.0722 * B;
}

export function contrastRatio(a: Rgb, b: Rgb): number {
	const [hi, lo] = [relativeLuminance(a), relativeLuminance(b)].sort((x, y) => y - x);
	return (hi + 0.05) / (lo + 0.05);
}

/** Texto sobre un fondo de color (acento configurable): oscuro o blanco, el de más contraste. */
export function onColor(bg: string): string {
	const rgb = hexToRgb(bg) ?? parseOklch(bg)?.rgb;
	if (!rgb) return '#0b1118';
	const dark: Rgb = [11, 17, 24];
	const light: Rgb = [255, 255, 255];
	return contrastRatio(rgb, dark) >= contrastRatio(rgb, light) ? '#0b1118' : '#ffffff';
}

/** Lee un token CSS ya resuelto (por ejemplo `--st-active`) como color rgba. */
export function cssToken(name: string, el: Element = document.documentElement): string {
	return toRgba(getComputedStyle(el).getPropertyValue(name).trim());
}
