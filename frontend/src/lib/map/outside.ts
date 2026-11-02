// Mapa en línea fuera del extracto (ADR 0019). Las capas clara y oscura salen del extracto
// descargado en el equipo; fuera de esa zona, debajo, va el mapa gris de Esri. Con un protocolo
// propio, las teselas de Esri que caen enteras dentro del extracto no se piden: ahí las tapa el
// mapa del equipo, y el navegador del visitante no consulta a Esri sin necesidad.
import type { AddProtocolAction } from 'maplibre-gl';

export const OUTSIDE_PROTOCOL = 'fuera';

/** [oeste, sur, este, norte] en grados. */
export type Bounds = [number, number, number, number];

/** PNG transparente de 1×1: la respuesta para una tesela que tapa el extracto. */
const EMPTY_PNG =
	'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAAC0lEQVR4nGNgAAIAAAUAAXpeqz8AAAAASUVORK5CYII=';

/**
 * Plantilla de teselas para MapLibre: `fuera://{z}/{x}/{y}?b=…&u=…`. La URL real va codificada
 * para que MapLibre no le reemplace las llaves; las completa `load`.
 */
export function outsideTiles(url: string, bounds: Bounds): string {
	return `${OUTSIDE_PROTOCOL}://{z}/{x}/{y}?b=${bounds.join(',')}&u=${encodeURIComponent(url)}`;
}

/** Límites de una tesela en grados. */
export function tileBounds(z: number, x: number, y: number): Bounds {
	const n = 2 ** z;
	const lon = (i: number) => (i / n) * 360 - 180;
	const lat = (j: number) => (Math.atan(Math.sinh(Math.PI * (1 - (2 * j) / n))) * 180) / Math.PI;
	return [lon(x), lat(y + 1), lon(x + 1), lat(y)];
}

/** La tesela cae entera dentro de `b`. */
export function tileInside(z: number, x: number, y: number, b: Bounds): boolean {
	const [w, s, e, n] = tileBounds(z, x, y);
	return w >= b[0] && s >= b[1] && e <= b[2] && n <= b[3];
}

/** Qué pedir para una URL del protocolo: `null` si la tesela queda tapada por el extracto. */
export function resolveOutside(url: string): string | null {
	const parsed = new URL(url.replace(`${OUTSIDE_PROTOCOL}://`, 'http://tesela/'));
	const [z, x, y] = parsed.pathname.split('/').slice(1).map(Number);
	const b = (parsed.searchParams.get('b') ?? '').split(',').map(Number);
	if (b.length === 4 && b.every(Number.isFinite) && tileInside(z, x, y, b as Bounds)) return null;
	return (parsed.searchParams.get('u') ?? '')
		.replace('{z}', String(z))
		.replace('{x}', String(x))
		.replace('{y}', String(y));
}

const load: AddProtocolAction = async (params, abort) => {
	const src = resolveOutside(params.url);
	if (!src) return { data: Uint8Array.from(atob(EMPTY_PNG), (c) => c.charCodeAt(0)).buffer };
	const res = await fetch(src, { signal: abort.signal });
	if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
	return { data: await res.arrayBuffer() };
};

let registered = false;

/** Registra el protocolo en MapLibre (una vez; vale para todos los mapas de la página). */
export function registerOutside(ml: {
	addProtocol: (name: string, fn: AddProtocolAction) => void;
}): void {
	if (registered) return;
	ml.addProtocol(OUTSIDE_PROTOCOL, load);
	registered = true;
}
