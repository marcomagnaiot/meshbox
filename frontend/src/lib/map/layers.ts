// Fuentes y capas de datos (16.5): GeoJSON actualizado por eventos, feature-state para
// resaltar y ningún marcador DOM por nodo.
import type { ExpressionSpecification, LayerSpecification, Map as MlMap } from 'maplibre-gl';
import { EMPTY } from './geojson';
import type { MapColors } from './theme';

export const SRC = {
	nodes: 'm-nodes',
	uncertainty: 'm-uncertainty',
	links: 'm-links',
	track: 'm-track',
	route: 'm-route',
	activity: 'm-activity',
	waypoints: 'm-waypoints',
	spider: 'm-spider',
	selected: 'm-selected',
	me: 'm-me'
} as const;

/** Hasta este zoom se agrupan los nodos; un grupo que sigue junto se abre en abanico. */
export const CLUSTER_MAX_ZOOM = 15;
export const LABEL_MIN_ZOOM = 11;

export const LAYER = {
	uncertaintyFill: 'm-uncertainty-fill',
	uncertaintyLine: 'm-uncertainty-line',
	linksGood: 'm-links-good',
	linksFair: 'm-links-fair',
	linksPoor: 'm-links-poor',
	trackCasing: 'm-track-casing',
	trackLine: 'm-track-line',
	trackPoints: 'm-track-points',
	trackCursor: 'm-track-cursor',
	routeLine: 'm-route-line',
	routeHops: 'm-route-hops',
	activityTrail: 'm-activity-trail',
	activityPulse: 'm-activity-pulse',
	waypoints: 'm-waypoints',
	halo: 'm-nodes-halo',
	clusters: 'm-clusters',
	clusterCount: 'm-cluster-count',
	nodes: 'm-nodes-icon',
	labels: 'm-nodes-label',
	selectedHalo: 'm-selected-halo',
	selectedIcon: 'm-selected-icon',
	spiderLegs: 'm-spider-legs',
	spiderNodes: 'm-spider-nodes',
	me: 'm-me'
} as const;

export const DATA_SOURCES = new Set<string>(Object.values(SRC));
export const DATA_LAYERS = new Set<string>(Object.values(LAYER));

const FONT = ['Noto Sans Medium'];
const isPoint: ExpressionSpecification = ['==', ['geometry-type'], 'Point'];
const isLine: ExpressionSpecification = ['==', ['geometry-type'], 'LineString'];
const unclustered: ExpressionSpecification = ['!', ['has', 'point_count']];

export function addDataSources(map: MlMap): void {
	const add = (id: string, extra: Record<string, unknown> = {}) => {
		if (!map.getSource(id)) map.addSource(id, { type: 'geojson', data: EMPTY as never, ...extra });
	};
	add(SRC.nodes, {
		cluster: true,
		clusterRadius: 38,
		clusterMaxZoom: CLUSTER_MAX_ZOOM,
		clusterProperties: {
			active: ['+', ['case', ['==', ['get', 'status'], 'active'], 1, 0]]
		}
	});
	add(SRC.uncertainty);
	add(SRC.links);
	add(SRC.track);
	add(SRC.route);
	add(SRC.activity);
	add(SRC.waypoints);
	add(SRC.spider);
	add(SRC.selected);
	add(SRC.me);
}

function linkLayer(id: string, cls: string, color: string, dash?: number[]): LayerSpecification {
	return {
		id,
		type: 'line',
		source: SRC.links,
		filter: ['==', ['get', 'cls'], cls],
		layout: { 'line-cap': dash ? 'butt' : 'round' },
		paint: {
			'line-color': color,
			'line-width': ['interpolate', ['linear'], ['get', 'recency'], 0, 1, 1, 3],
			'line-opacity': ['interpolate', ['linear'], ['get', 'recency'], 0, 0.35, 1, 0.8],
			...(dash ? { 'line-dasharray': dash } : {})
		}
	} as LayerSpecification;
}

export function dataLayers(c: MapColors): LayerSpecification[] {
	return [
		{
			id: LAYER.uncertaintyFill,
			type: 'fill',
			source: SRC.uncertainty,
			paint: {
				'fill-color': c.accent,
				'fill-opacity': ['case', ['boolean', ['feature-state', 'selected'], false], 0.16, 0.05]
			}
		},
		{
			id: LAYER.uncertaintyLine,
			type: 'line',
			source: SRC.uncertainty,
			paint: {
				'line-color': c.accent,
				'line-width': 1,
				'line-opacity': ['case', ['boolean', ['feature-state', 'selected'], false], 0.7, 0.25]
			}
		},
		linkLayer(LAYER.linksGood, 'good', c.good),
		linkLayer(LAYER.linksFair, 'fair', c.fair, [3, 2]),
		linkLayer(LAYER.linksPoor, 'poor', c.poor, [1, 2]),
		{
			id: LAYER.trackCasing,
			type: 'line',
			source: SRC.track,
			filter: isLine,
			layout: { 'line-cap': 'round', 'line-join': 'round' },
			paint: { 'line-color': c.outline, 'line-width': 6, 'line-opacity': 0.7 }
		},
		{
			id: LAYER.trackLine,
			type: 'line',
			source: SRC.track,
			filter: isLine,
			layout: { 'line-cap': 'round', 'line-join': 'round' },
			paint: { 'line-color': c.accent, 'line-width': 3 }
		},
		{
			id: LAYER.trackPoints,
			type: 'circle',
			source: SRC.track,
			filter: ['all', isPoint, ['!=', ['get', 'kind'], 'cursor']],
			paint: {
				'circle-radius': ['match', ['get', 'kind'], 'start', 5, 'end', 5, 3.5],
				'circle-color': ['match', ['get', 'kind'], 'start', c.outline, c.accent],
				'circle-stroke-color': ['match', ['get', 'kind'], 'start', c.accent, c.outline],
				'circle-stroke-width': 2
			}
		},
		{
			id: LAYER.trackCursor,
			type: 'circle',
			source: SRC.track,
			filter: ['==', ['get', 'kind'], 'cursor'],
			paint: {
				'circle-radius': 8,
				'circle-color': c.accent,
				'circle-stroke-color': c.text,
				'circle-stroke-width': 3
			}
		},
		{
			id: LAYER.routeLine,
			type: 'line',
			source: SRC.route,
			filter: isLine,
			layout: { 'line-cap': 'round' },
			paint: { 'line-color': c.route, 'line-width': 3, 'line-opacity': 0.9 }
		},
		{
			id: LAYER.routeHops,
			type: 'symbol',
			source: SRC.route,
			filter: isPoint,
			layout: {
				'text-field': ['get', 'snr'],
				'text-font': FONT,
				'text-size': 11,
				'text-allow-overlap': true
			},
			paint: { 'text-color': c.text, 'text-halo-color': c.textHalo, 'text-halo-width': 2 }
		},
		{
			id: LAYER.activityTrail,
			type: 'line',
			source: SRC.activity,
			filter: isLine,
			layout: { 'line-cap': 'round' },
			paint: {
				'line-color': ['get', 'color'],
				'line-width': 2.5,
				'line-opacity': ['get', 'opacity']
			}
		},
		{
			id: LAYER.activityPulse,
			type: 'circle',
			source: SRC.activity,
			filter: isPoint,
			paint: {
				'circle-radius': ['get', 'radius'],
				'circle-color': 'rgba(0,0,0,0)',
				'circle-stroke-color': ['get', 'color'],
				'circle-stroke-width': 2.5,
				'circle-stroke-opacity': ['get', 'opacity']
			}
		},
		{
			id: LAYER.waypoints,
			type: 'symbol',
			source: SRC.waypoints,
			layout: {
				'icon-image': 'waypoint-pin',
				'icon-anchor': 'bottom',
				'icon-allow-overlap': true,
				'text-field': ['step', ['zoom'], '', 12, ['get', 'name']],
				'text-font': FONT,
				'text-size': 11,
				'text-offset': [0, 0.4],
				'text-anchor': 'top',
				'text-optional': true
			},
			paint: { 'text-color': c.text, 'text-halo-color': c.textHalo, 'text-halo-width': 1.5 }
		},
		{
			id: LAYER.halo,
			type: 'circle',
			source: SRC.nodes,
			filter: unclustered,
			paint: {
				'circle-radius': 17,
				'circle-color': c.accent,
				'circle-opacity': [
					'case',
					['boolean', ['feature-state', 'selected'], false],
					0.45,
					['boolean', ['feature-state', 'hover'], false],
					0.25,
					0
				],
				'circle-stroke-color': c.accent,
				'circle-stroke-width': ['case', ['boolean', ['feature-state', 'selected'], false], 2, 0]
			}
		},
		{
			id: LAYER.clusters,
			type: 'circle',
			source: SRC.nodes,
			filter: ['has', 'point_count'],
			paint: {
				'circle-color': c.cluster,
				'circle-opacity': 0.92,
				'circle-radius': ['step', ['get', 'point_count'], 15, 5, 18, 15, 22, 40, 26],
				'circle-stroke-width': 3,
				// Anillo del color "activo" si el grupo tiene algún nodo activo.
				'circle-stroke-color': ['case', ['>', ['get', 'active'], 0], c.active, c.inactive]
			}
		},
		{
			id: LAYER.clusterCount,
			type: 'symbol',
			source: SRC.nodes,
			filter: ['has', 'point_count'],
			layout: {
				'text-field': ['get', 'point_count_abbreviated'],
				'text-font': FONT,
				'text-size': 13,
				'text-allow-overlap': true
			},
			paint: { 'text-color': c.clusterText }
		},
		{
			id: LAYER.nodes,
			type: 'symbol',
			source: SRC.nodes,
			filter: unclustered,
			layout: {
				'icon-image': ['get', 'icon'],
				'icon-allow-overlap': true,
				'icon-ignore-placement': true,
				'symbol-sort-key': ['get', 'sort']
			}
		},
		{
			id: LAYER.labels,
			type: 'symbol',
			source: SRC.nodes,
			filter: unclustered,
			minzoom: LABEL_MIN_ZOOM,
			layout: {
				'text-field': ['get', 'label'],
				'text-font': FONT,
				'text-size': 11,
				'text-offset': [0, 1.25],
				'text-anchor': 'top',
				'text-optional': true,
				'symbol-sort-key': ['-', 10, ['get', 'sort']]
			},
			paint: { 'text-color': c.text, 'text-halo-color': c.textHalo, 'text-halo-width': 1.6 }
		},
		// El nodo seleccionado se dibuja aparte, encima de los grupos: siempre se ve resaltado.
		{
			id: LAYER.selectedHalo,
			type: 'circle',
			source: SRC.selected,
			paint: {
				'circle-radius': 17,
				'circle-color': c.accent,
				'circle-opacity': 0.4,
				'circle-stroke-color': c.accent,
				'circle-stroke-width': 2
			}
		},
		{
			id: LAYER.selectedIcon,
			type: 'symbol',
			source: SRC.selected,
			layout: {
				'icon-image': ['get', 'icon'],
				'icon-allow-overlap': true,
				'icon-ignore-placement': true,
				'text-field': ['get', 'label'],
				'text-font': FONT,
				'text-size': 12,
				'text-offset': [0, 1.35],
				'text-anchor': 'top',
				'text-allow-overlap': true
			},
			paint: { 'text-color': c.text, 'text-halo-color': c.textHalo, 'text-halo-width': 1.8 }
		},
		{
			id: LAYER.spiderLegs,
			type: 'line',
			source: SRC.spider,
			filter: isLine,
			paint: { 'line-color': c.text, 'line-width': 1.2, 'line-opacity': 0.6 }
		},
		{
			id: LAYER.spiderNodes,
			type: 'symbol',
			source: SRC.spider,
			filter: isPoint,
			layout: {
				'icon-image': ['get', 'icon'],
				'icon-allow-overlap': true,
				'icon-ignore-placement': true,
				'text-field': ['get', 'label'],
				'text-font': FONT,
				'text-size': 11,
				'text-offset': [0, 1.25],
				'text-anchor': 'top',
				'text-allow-overlap': true
			},
			paint: { 'text-color': c.text, 'text-halo-color': c.textHalo, 'text-halo-width': 1.6 }
		},
		{
			id: LAYER.me,
			type: 'circle',
			source: SRC.me,
			paint: {
				'circle-radius': 8,
				'circle-color': c.cat1,
				'circle-stroke-color': '#ffffff',
				'circle-stroke-width': 3
			}
		}
	] as LayerSpecification[];
}

/** Actualiza los colores de las capas de datos al cambiar el tema. */
export function recolorDataLayers(map: MlMap, c: MapColors): void {
	for (const layer of dataLayers(c)) {
		if (!map.getLayer(layer.id) || !('paint' in layer) || !layer.paint) continue;
		for (const [prop, value] of Object.entries(layer.paint)) {
			// Las propiedades salen de la propia definición de la capa: nombre y valor coinciden.
			map.setPaintProperty(layer.id, prop as Parameters<MlMap['setPaintProperty']>[1], value);
		}
	}
}
