import { describe, expect, it } from 'vitest';
import {
	absolute,
	BASEMAP_SOURCE,
	buildBaseStyle,
	wantedBase,
	type BaseStyleOptions
} from './style';

describe('mapa fuera del extracto (ADR 0019)', () => {
	const opts: BaseStyleOptions = {
		base: 'dark',
		tiles: {
			tiles: ['/tiles/v/{z}/{x}/{y}.mvt'],
			maxzoom: 14,
			bounds: [-63.8, -41.3, -62.4, -40.3]
		},
		lang: 'es',
		satelliteAllowed: true,
		esriAttribution: 'Esri',
		background: '#000000'
	};

	it('va debajo del mapa del extracto, con fondo y nombres', () => {
		const style = buildBaseStyle(opts);
		const ids = style.layers.map((l) => l.id);
		expect(ids.slice(0, 3)).toEqual(['background', 'outside-0', 'outside-1']);
		const first = style.layers.findIndex((l) => 'source' in l && l.source === BASEMAP_SOURCE);
		expect(first).toBeGreaterThan(2);
		const src = style.sources['outside-0'] as { tiles: string[]; maxzoom: number };
		expect(src.tiles[0]).toMatch(/^fuera:\/\/\{z\}\/\{x\}\/\{y\}\?b=-63.8,-41.3,-62.4,-40.3&u=/);
		expect(decodeURIComponent(src.tiles[0])).toContain('World_Light_Gray_Base');
		expect(style.layers[1]).toMatchObject({ paint: { 'raster-brightness-min': 0.49 } });
		expect(
			decodeURIComponent((style.sources['outside-1'] as { tiles: string[] }).tiles[0])
		).toContain('World_Dark_Gray_Reference');
		expect(src.maxzoom).toBe(16);
		const light = buildBaseStyle({ ...opts, base: 'light' }).sources['outside-1'] as {
			tiles: string[];
		};
		expect(decodeURIComponent(light.tiles[0])).toContain('World_Light_Gray_Reference');
	});

	it('no está si Esri no está permitido o el extracto no dice sus límites', () => {
		for (const o of [
			{ ...opts, satelliteAllowed: false },
			{ ...opts, tiles: { ...opts.tiles!, bounds: undefined } }
		]) {
			expect(Object.keys(buildBaseStyle(o).sources)).toEqual([BASEMAP_SOURCE]);
		}
	});
});

describe('absolute', () => {
	it('conserva las llaves de la plantilla de teselas', () => {
		const url = absolute('/tiles/v/{z}/{x}/{y}.mvt?v=1792502981');
		expect(url).toMatch(/\/tiles\/v\/\{z\}\/\{x\}\/\{y\}\.mvt\?v=1792502981$/);
		expect(url).not.toContain('%7B');
	});

	it('deja igual una URL absoluta', () => {
		expect(absolute('https://tiles.example/{z}/{x}/{y}.mvt')).toBe(
			'https://tiles.example/{z}/{x}/{y}.mvt'
		);
	});

	it('agrega la barra a una ruta sin ella', () => {
		expect(absolute('tiles/v/{z}/{x}/{y}.mvt')).toMatch(/\/tiles\/v\/\{z\}\/\{x\}\/\{y\}\.mvt$/);
	});
});

describe('wantedBase', () => {
	it('sin elección del visitante usa la capa configurada en el sitio', () => {
		expect(wantedBase(null, 'light')).toBe('light');
		expect(wantedBase(null, 'dark')).toBe('dark');
		expect(wantedBase(null, 'satellite')).toBe('satellite');
	});

	it('la elección del visitante gana', () => {
		expect(wantedBase('dark', 'light')).toBe('dark');
		expect(wantedBase('satellite', 'light')).toBe('satellite');
	});
});
