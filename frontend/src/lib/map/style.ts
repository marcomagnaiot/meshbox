// Estilos del mapa base (16.5): Protomaps oscuro y claro atenuados para que el mapa quede en
// segundo plano (menos saturación, etiquetas discretas, idioma del sitio) y la capa satelital
// de Esri. Tipografías y sprites se sirven desde el propio equipo (/tiles/fonts, /tiles/sprites).
import { layers as protomapsLayers, namedFlavor, type Flavor } from '@protomaps/basemaps';
import type { LayerSpecification, SourceSpecification, StyleSpecification } from 'maplibre-gl';
import type { BaseLayer } from '$lib/api/types';

export const ESRI_TILES =
	'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}';
/** Rutas y nombres de lugares de Esri, transparentes, para dibujar sobre la imagen satelital. */
export const ESRI_LABELS = [
	'https://server.arcgisonline.com/ArcGIS/rest/services/Reference/World_Transportation/MapServer/tile/{z}/{y}/{x}',
	'https://server.arcgisonline.com/ArcGIS/rest/services/Reference/World_Boundaries_and_Places/MapServer/tile/{z}/{y}/{x}'
];
export const BASEMAP_SOURCE = 'protomaps';
export const SATELLITE_SOURCE = 'esri';

export interface TileJson {
	tiles: string[];
	minzoom?: number;
	maxzoom?: number;
	bounds?: [number, number, number, number];
	attribution?: string;
}

// ------------------------------------------------------------------ colores

function parseHex(hex: string): [number, number, number] | null {
	const m = /^#([0-9a-f]{6})$/i.exec(hex);
	if (!m) return null;
	return [0, 2, 4].map((i) => parseInt(m[1].slice(i, i + 2), 16)) as [number, number, number];
}

function toHex(rgb: number[]): string {
	return (
		'#' +
		rgb
			.map((v) =>
				Math.round(Math.max(0, Math.min(255, v)))
					.toString(16)
					.padStart(2, '0')
			)
			.join('')
	);
}

/** Mezcla lineal en sRGB: suficiente para atenuar un mapa base. */
export function mix(a: string, b: string, t: number): string {
	const ca = parseHex(a);
	const cb = parseHex(b);
	if (!ca || !cb) return a;
	return toHex(ca.map((v, i) => v + (cb[i] - v) * t));
}

/** Quita saturación acercando el color a su gris de igual luminancia. */
export function desaturate(hex: string, amount: number): string {
	const c = parseHex(hex);
	if (!c) return hex;
	const gray = 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2];
	return toHex(c.map((v) => v + (gray - v) * amount));
}

const LABEL_KEYS = [
	'roads_label_minor',
	'roads_label_major',
	'ocean_label',
	'subplace_label',
	'city_label',
	'state_label',
	'country_label',
	'address_label'
] as const;

/** Variante atenuada del estilo de Protomaps. */
export function mutedFlavor(base: 'dark' | 'light'): Flavor {
	const source = namedFlavor(base);
	const out: Record<string, unknown> = {};
	for (const [key, value] of Object.entries(source)) {
		out[key] = typeof value === 'string' ? desaturate(value, 0.35) : value;
	}
	const f = out as unknown as Flavor;
	if (base === 'dark') {
		// Tono frío del fondo de la interfaz (--bg) para que el mapa no compita con los paneles.
		f.background = mix(f.background, '#121821', 0.6);
		f.earth = mix(f.earth, '#141a22', 0.55);
		f.water = mix(f.water, '#1a2431', 0.45);
	} else {
		f.earth = mix(f.earth, '#eef1f5', 0.35);
		f.water = mix(f.water, '#c9d6e4', 0.3);
	}
	for (const key of LABEL_KEYS) {
		const value = f[key];
		if (typeof value === 'string') f[key] = mix(value, f.earth, base === 'dark' ? 0.28 : 0.22);
	}
	if (f.pois) {
		const pois = { ...f.pois };
		for (const k of Object.keys(pois) as (keyof typeof pois)[]) pois[k] = desaturate(pois[k], 0.5);
		f.pois = pois;
	}
	return f;
}

// ------------------------------------------------------------------ estilo

export interface BaseStyleOptions {
	base: BaseLayer;
	tiles: TileJson | null;
	lang: string;
	satelliteAllowed: boolean;
	esriAttribution: string;
	background: string;
	/** Rutas y nombres de ciudades sobre el satélite (selectores del panel y del asistente). */
	labels?: boolean;
}

const origin = () => (typeof location === 'undefined' ? '' : location.origin);
/**
 * URL absoluta para el worker de MapLibre (no resuelve rutas relativas). Sin `new URL()`: codifica
 * las llaves de la plantilla (`{z}` → `%7Bz%7D`) y MapLibre deja de reemplazarlas.
 */
export function absolute(url: string): string {
	if (/^[a-z][a-z0-9+.-]*:/i.test(url)) return url;
	const base = origin() || 'http://localhost';
	return url.startsWith('/') ? `${base}${url}` : `${base}/${url}`;
}

/**
 * Capa base pedida: la que eligió el visitante en el selector de capas o, si no eligió, la que
 * configuró el administrador en Sitio y mapa. El tema de la página no la cambia.
 */
export function wantedBase(visitor: BaseLayer | null, siteDefault: BaseLayer): BaseLayer {
	return visitor ?? siteDefault;
}

/** Capa base efectiva: sin extracto se usa el satélite (si está permitido). */
export function effectiveBase(
	wanted: BaseLayer,
	hasTiles: boolean,
	satelliteAllowed: boolean
): BaseLayer | 'none' {
	if (wanted === 'satellite') return satelliteAllowed ? 'satellite' : hasTiles ? 'dark' : 'none';
	if (hasTiles) return wanted;
	return satelliteAllowed ? 'satellite' : 'none';
}

export function buildBaseStyle(opts: BaseStyleOptions): StyleSpecification {
	const base = effectiveBase(opts.base, Boolean(opts.tiles), opts.satelliteAllowed);
	const sources: Record<string, SourceSpecification> = {};
	const layers: LayerSpecification[] = [
		{ id: 'background', type: 'background', paint: { 'background-color': opts.background } }
	];
	const style: StyleSpecification = {
		version: 8,
		glyphs: `${origin()}/tiles/fonts/{fontstack}/{range}.pbf`,
		sources,
		layers
	};

	if (base === 'satellite') {
		sources[SATELLITE_SOURCE] = {
			type: 'raster',
			tiles: [ESRI_TILES],
			tileSize: 256,
			// Esri tiene imagen hasta el zoom 17 en buena parte de Argentina (fuera de las
			// grandes ciudades); más arriba devuelve "Map data not yet available" en lugar de un
			// error. Con 17, MapLibre agranda esa tesela al acercarse más.
			maxzoom: 17,
			attribution: opts.esriAttribution
		};
		layers.push({
			id: 'satellite',
			type: 'raster',
			source: SATELLITE_SOURCE,
			// Sin fundido: cada tesela que llega se dibuja una vez (el fundido redibuja 300 ms).
			paint: {
				'raster-saturation': -0.15,
				'raster-brightness-max': 0.92,
				'raster-fade-duration': 0
			}
		});
		if (opts.labels) {
			ESRI_LABELS.forEach((url, i) => {
				sources[`esri-labels-${i}`] = {
					type: 'raster',
					tiles: [url],
					tileSize: 256,
					maxzoom: 17,
					attribution: 'Esri, HERE, Garmin, © OpenStreetMap'
				};
				layers.push({
					id: `satellite-labels-${i}`,
					type: 'raster',
					source: `esri-labels-${i}`,
					paint: { 'raster-fade-duration': 0 }
				});
			});
		}
	} else if ((base === 'dark' || base === 'light') && opts.tiles) {
		const tj = opts.tiles;
		sources[BASEMAP_SOURCE] = {
			type: 'vector',
			tiles: tj.tiles.map(absolute),
			minzoom: tj.minzoom ?? 0,
			maxzoom: tj.maxzoom ?? 14,
			...(tj.bounds ? { bounds: tj.bounds } : {}),
			attribution: tj.attribution ?? '© OpenStreetMap'
		};
		style.sprite = `${origin()}/tiles/sprites/v4/${base}`;
		const flavor = mutedFlavor(base);
		for (const layer of protomapsLayers(BASEMAP_SOURCE, flavor, { lang: opts.lang })) {
			if (layer.id === 'background') continue;
			// Puntos de interés solo de cerca y discretos: el protagonista es la red.
			if (layer.id === 'pois') {
				layers.push({
					...layer,
					minzoom: 15,
					paint: { ...(layer.paint ?? {}), 'icon-opacity': 0.55, 'text-opacity': 0.7 }
				} as LayerSpecification);
				continue;
			}
			layers.push(layer);
		}
	}
	return style;
}
