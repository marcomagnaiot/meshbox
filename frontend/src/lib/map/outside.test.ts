import { describe, expect, it } from 'vitest';
import { outsideTiles, resolveOutside, tileBounds, tileInside, type Bounds } from './outside';

// Extracto de ejemplo alrededor de Viedma: [oeste, sur, este, norte].
const VIEDMA: Bounds = [-63.8, -41.3, -62.4, -40.3];
const ESRI =
	'https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/X/MapServer/tile/{z}/{y}/{x}';

/** Tesela que contiene un punto. */
function tileAt(z: number, lat: number, lon: number): [number, number, number] {
	const n = 2 ** z;
	const x = Math.floor(((lon + 180) / 360) * n);
	const r = (lat * Math.PI) / 180;
	const y = Math.floor(((1 - Math.asinh(Math.tan(r)) / Math.PI) / 2) * n);
	return [z, x, y];
}

describe('tileBounds', () => {
	it('la tesela 0 es el mundo', () => {
		const [w, s, e, n] = tileBounds(0, 0, 0);
		expect([w, e]).toEqual([-180, 180]);
		expect(n).toBeCloseTo(85.0511, 3);
		expect(s).toBeCloseTo(-85.0511, 3);
	});
});

describe('tileInside', () => {
	it('dentro del extracto de cerca, fuera de lejos o en el borde', () => {
		expect(tileInside(...tileAt(12, -40.81, -63.0), VIEDMA)).toBe(true);
		expect(tileInside(...tileAt(12, -38.72, -62.27), VIEDMA)).toBe(false); // Bahía Blanca
		expect(tileInside(...tileAt(6, -40.81, -63.0), VIEDMA)).toBe(false); // más grande que el extracto
	});
});

describe('resolveOutside', () => {
	const template = outsideTiles(ESRI, VIEDMA);
	const url = (z: number, x: number, y: number) =>
		template.replace('{z}', String(z)).replace('{x}', String(x)).replace('{y}', String(y));

	it('MapLibre solo completa las llaves del protocolo; la URL real va codificada', () => {
		expect(template.startsWith('fuera://{z}/{x}/{y}?b=-63.8,-41.3,-62.4,-40.3&u=')).toBe(true);
		expect(template.split('?')[1]).not.toContain('{');
	});

	it('no pide a Esri las teselas tapadas por el extracto', () => {
		expect(resolveOutside(url(...tileAt(12, -40.81, -63.0)))).toBeNull();
	});

	it('afuera arma la URL de Esri con z, y, x', () => {
		const [z, x, y] = tileAt(12, -38.72, -62.27);
		expect(resolveOutside(url(z, x, y))).toBe(
			`https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/X/MapServer/tile/${z}/${y}/${x}`
		);
	});
});
