<!--
  Mapa (16.5). Este componente y MapLibre se cargan en diferido y en paralelo con los datos
  (el layout pide el módulo al arrancar). Capas de datos con GeoJSON agrupado cada 500 ms,
  feature-state para resaltar y sin marcadores DOM por nodo.
-->
<script lang="ts">
	import * as maplibregl from 'maplibre-gl';
	import type {
		GeoJSONSource,
		LngLatLike,
		Map as MlMap,
		MapGeoJSONFeature,
		StyleSpecification
	} from 'maplibre-gl';
	import 'maplibre-gl/dist/maplibre-gl.css';
	// MapLibre 6 es solo ESM y busca su worker junto al módulo: con el paquete armado por Vite
	// hay que decirle dónde quedó (un chunk propio, mismo origen: lo permite `worker-src 'self'`).
	import workerUrl from 'maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url';
	import { onMount, untrack } from 'svelte';
	import { goto } from '$app/navigation';
	import type { BaseLayer } from '$lib/api/types';
	import { fmt } from '$lib/i18n/fmt.svelte';
	import { i18n } from '$lib/i18n/locale.svelte';
	import { m } from '$lib/paraglide/messages';
	import { clock } from '$lib/stores/clock.svelte';
	import { live } from '$lib/stores/live.svelte';
	import { mapData } from '$lib/stores/mapdata.svelte';
	import { prefs } from '$lib/stores/prefs.svelte';
	import { site } from '$lib/stores/site.svelte';
	import { filters, selection, toasts, ui } from '$lib/stores/ui.svelte';
	import { boundsOf, isValidLatLon } from '$lib/utils/geo';
	import { nodeHref, nodeNum } from '$lib/utils/ids';
	import { EMPTY_FILTER } from '$lib/utils/nodes';
	import { throttle } from '$lib/utils/timing';
	import { ActivityLayer } from './activity';
	import { mapController } from './controller.svelte';
	import { DragFpsMonitor } from './fps';
	import {
		fanOffsets,
		linksCollection,
		nodesCollection,
		trackCollection,
		tracerouteCollection,
		uncertaintyCollection,
		waypointsCollection,
		type Feature,
		type LineString,
		type Point
	} from './geojson';
	import { drawNodeIcon, drawWaypointIcon, ICON_PIXEL_RATIO, parseIconName } from './icons';
	import {
		addDataSources,
		CLUSTER_MAX_ZOOM,
		DATA_LAYERS,
		DATA_SOURCES,
		dataLayers,
		LAYER,
		recolorDataLayers,
		SRC
	} from './layers';
	import { buildBaseStyle, effectiveBase, wantedBase as chooseBase, type TileJson } from './style';
	import { readMapColors, type MapColors } from './theme';

	interface Props {
		/** Relleno del mapa (paneles que lo tapan), en px. */
		padding: { top: number; right: number; bottom: number; left: number };
	}

	let { padding }: Props = $props();

	let container: HTMLDivElement | undefined = $state();
	let map: MlMap | null = null;
	let loaded = $state(false);
	let error = $state(false);
	let tiles = $state<TileJson | null>(null);
	let colors: MapColors | null = null;
	let activity: ActivityLayer | null = null;
	let spiderOpen = false;
	let hoverId: number | null = null;
	let selectedNum: number | null = null;
	let lastFocused: string | null = null;
	let lastTick = 0;
	let lastPadding = '';

	const reduced = () => ui.reducedMotion;

	/**
	 * Colores de los tokens; etiquetas y anillo fino según la capa base (no según el tema de la
	 * interfaz): texto claro con halo oscuro sobre satélite y mapa oscuro, al revés sobre el claro.
	 */
	function computeColors(): MapColors {
		const c = readMapColors();
		const base = effectiveBase(wantedBase(), Boolean(tiles), site.data.layers.satellite);
		if (base === 'light') {
			c.text = 'rgba(24,31,41,1)';
			c.textHalo = 'rgba(255,255,255,0.92)';
		} else {
			c.text = 'rgba(244,246,248,1)';
			c.textHalo = 'rgba(10,14,20,0.9)';
		}
		return c;
	}

	// ------------------------------------------------------------ capa base

	function wantedBase(): BaseLayer {
		return chooseBase(prefs.base, site.data.layers.default);
	}

	function esriAttribution(): string {
		const esri = site.data.attributions.find((a) => /esri/i.test(a.name));
		return esri?.text ?? 'Imágenes © Esri, Maxar, Earthstar Geographics';
	}

	function baseStyle(): StyleSpecification {
		return buildBaseStyle({
			base: wantedBase(),
			tiles,
			lang: i18n.locale,
			satelliteAllowed: site.data.layers.satellite,
			esriAttribution: esriAttribution(),
			background: colors?.background ?? '#0f141b'
		});
	}

	async function fetchTiles(): Promise<TileJson | null> {
		if (!site.data.has_tiles) return null;
		try {
			const res = await fetch('/tiles/v.json', { headers: { Accept: 'application/json' } });
			if (!res.ok) return null;
			const tj = (await res.json()) as TileJson;
			return Array.isArray(tj.tiles) && tj.tiles.length ? tj : null;
		} catch {
			return null;
		}
	}

	// ------------------------------------------------------------ datos

	function source(id: string): GeoJSONSource | undefined {
		return map?.getSource(id) as GeoJSONSource | undefined;
	}

	const updateNodes = throttle(() => {
		if (!map || !loaded) return;
		const nodes = live.nodeList();
		const byId = live.nodes;
		const fc = nodesCollection(nodes, filters.value, clock.exact(), site.data.thresholds);
		source(SRC.nodes)?.setData(fc as never);
		source(SRC.uncertainty)?.setData(
			(prefs.layers.uncertainty
				? uncertaintyCollection(fc, byId)
				: { type: 'FeatureCollection', features: [] }) as never
		);
		const visible = new Set(fc.features.map((f) => f.properties.id));
		source(SRC.links)?.setData(
			linksCollection(mapData.links.values(), byId, clock.exact(), visible) as never
		);
		updateSelected();
		if (spiderOpen) closeSpider();
	}, 500);

	/** El nodo seleccionado, aparte y por encima de los grupos (aunque los filtros lo oculten). */
	function updateSelected() {
		const node = selection.nodeId ? live.nodes.get(selection.nodeId) : undefined;
		const fc = node
			? nodesCollection(
					[node],
					{ ...EMPTY_FILTER, showInactive: true },
					clock.exact(),
					site.data.thresholds
				)
			: { type: 'FeatureCollection', features: [] };
		source(SRC.selected)?.setData(fc as never);
	}

	function updateWaypoints() {
		source(SRC.waypoints)?.setData(
			waypointsCollection(mapData.waypoints.values(), clock.exact()) as never
		);
	}

	function updateTrack() {
		source(SRC.track)?.setData(trackCollection(selection.track, selection.cursor) as never);
	}

	function updateRoute() {
		source(SRC.route)?.setData(
			tracerouteCollection(selection.traceroute, live.nodes, (v) => fmt.db(v)) as never
		);
	}

	function setVisibility(ids: string[], on: boolean) {
		if (!map) return;
		for (const id of ids)
			if (map.getLayer(id)) map.setLayoutProperty(id, 'visibility', on ? 'visible' : 'none');
	}

	function applyVisibility() {
		const f = site.data.features;
		setVisibility(
			[LAYER.linksGood, LAYER.linksFair, LAYER.linksPoor],
			prefs.layers.links && f.links
		);
		setVisibility([LAYER.activityTrail, LAYER.activityPulse], prefs.layers.activity && f.activity);
		setVisibility([LAYER.waypoints], prefs.layers.waypoints && f.waypoints);
		setVisibility([LAYER.uncertaintyFill, LAYER.uncertaintyLine], prefs.layers.uncertainty);
		if (activity) activity.enabled = prefs.layers.activity && f.activity;
	}

	// ------------------------------------------------------------ íconos

	function addMissingImage(id: string) {
		if (!map || !colors || map.hasImage(id)) return;
		const parsed = parseIconName(id);
		const img = parsed
			? drawNodeIcon(colors, parsed.status, parsed.infra, parsed.fixed)
			: id === 'waypoint-pin'
				? drawWaypointIcon(colors)
				: null;
		if (img) map.addImage(id, img, { pixelRatio: ICON_PIXEL_RATIO });
	}

	function refreshImages() {
		if (!map || !colors) return;
		for (const id of map.listImages()) {
			const parsed = parseIconName(id);
			const img = parsed
				? drawNodeIcon(colors, parsed.status, parsed.infra, parsed.fixed)
				: id === 'waypoint-pin'
					? drawWaypointIcon(colors)
					: null;
			if (img) map.updateImage(id, img);
		}
	}

	// ------------------------------------------------------------ selección

	function setFeatureState(src: string, id: number | null, state: Record<string, boolean>) {
		if (!map || id === null || Number.isNaN(id) || !map.getSource(src)) return;
		map.setFeatureState({ source: src, id }, state);
	}

	function applySelection(id: string | null) {
		const num = id ? nodeNum(id) : null;
		if (selectedNum !== null && selectedNum !== num) {
			setFeatureState(SRC.nodes, selectedNum, { selected: false });
			setFeatureState(SRC.uncertainty, selectedNum, { selected: false });
		}
		selectedNum = num;
		if (num !== null) {
			setFeatureState(SRC.nodes, num, { selected: true });
			setFeatureState(SRC.uncertainty, num, { selected: true });
		}
	}

	function focusNode(id: string) {
		const node = live.nodes.get(id);
		if (!map || !node || !isValidLatLon(node.lat, node.lon)) return;
		const center: LngLatLike = [node.lon as number, node.lat as number];
		const zoom = Math.max(map.getZoom(), 13);
		// El relleno va en la misma animación: centrar deja el nodo a la vista entre los paneles.
		if (reduced()) map.jumpTo({ center, zoom, padding });
		else map.flyTo({ center, zoom, padding, duration: 900, essential: false });
	}

	// ------------------------------------------------------------ abanico

	async function openSpider(clusterId: number, center: [number, number]) {
		const src = source(SRC.nodes);
		if (!map || !src) return;
		const leaves = (await src.getClusterLeaves(clusterId, 60, 0)) as unknown as Feature<
			Point,
			Record<string, unknown>
		>[];
		const c = map.project(center);
		const offsets = fanOffsets(leaves.length);
		const features: Feature<Point | LineString, Record<string, unknown>>[] = [];
		leaves.forEach((leaf, i) => {
			const ll = map!.unproject([c.x + offsets[i][0], c.y + offsets[i][1]]);
			const pos: [number, number] = [ll.lng, ll.lat];
			features.push({
				type: 'Feature',
				geometry: { type: 'LineString', coordinates: [center, pos] },
				properties: {}
			});
			features.push({
				type: 'Feature',
				geometry: { type: 'Point', coordinates: pos },
				properties: { ...leaf.properties }
			});
		});
		source(SRC.spider)?.setData({ type: 'FeatureCollection', features } as never);
		spiderOpen = true;
	}

	function closeSpider() {
		if (!spiderOpen) return;
		spiderOpen = false;
		source(SRC.spider)?.setData({ type: 'FeatureCollection', features: [] } as never);
	}

	// ------------------------------------------------------------ interacción

	function pickFeature(
		point: { x: number; y: number },
		tolerance: number
	): MapGeoJSONFeature | undefined {
		if (!map) return undefined;
		const box: [[number, number], [number, number]] = [
			[point.x - tolerance, point.y - tolerance],
			[point.x + tolerance, point.y + tolerance]
		];
		const layers = [LAYER.spiderNodes, LAYER.selectedIcon, LAYER.nodes, LAYER.clusters].filter(
			(l) => map!.getLayer(l)
		);
		return map.queryRenderedFeatures(box, { layers })[0];
	}

	async function onClick(e: maplibregl.MapMouseEvent) {
		const touch = (e.originalEvent as PointerEvent)?.pointerType === 'touch';
		const f = pickFeature(e.point, touch ? 14 : 6);
		if (!f) {
			closeSpider();
			return;
		}
		if (f.layer.id === LAYER.clusters) {
			const clusterId = f.properties.cluster_id as number;
			const center = (f.geometry as unknown as Point).coordinates;
			const zoom = await source(SRC.nodes)?.getClusterExpansionZoom(clusterId);
			if (zoom === undefined) return;
			if (zoom > CLUSTER_MAX_ZOOM && map && map.getZoom() >= CLUSTER_MAX_ZOOM - 1) {
				await openSpider(clusterId, center);
			} else {
				closeSpider();
				map?.easeTo({
					center,
					zoom: Math.min(zoom, CLUSTER_MAX_ZOOM + 1),
					duration: reduced() ? 0 : 500
				});
			}
			return;
		}
		const id = f.properties.id as string | undefined;
		if (!id) return;
		if (id === selection.nodeId) selection.focus();
		else void goto(nodeHref(id));
	}

	function onMove(e: maplibregl.MapMouseEvent) {
		if (!map) return;
		const f = pickFeature(e.point, 4);
		map.getCanvas().style.cursor = f ? 'pointer' : '';
		const num = f && f.layer.id === LAYER.nodes && typeof f.id === 'number' ? f.id : null;
		if (num === hoverId) return;
		if (hoverId !== null) setFeatureState(SRC.nodes, hoverId, { hover: false });
		hoverId = num;
		if (num !== null) setFeatureState(SRC.nodes, num, { hover: true });
	}

	// ------------------------------------------------------------ ciclo de vida

	function setupData() {
		if (!map || !colors) return;
		addDataSources(map);
		for (const layer of dataLayers(colors)) if (!map.getLayer(layer.id)) map.addLayer(layer);
		applyVisibility();
		updateNodes();
		updateNodes.flush();
		updateWaypoints();
		updateTrack();
		updateRoute();
		applySelection(selection.nodeId);
	}

	function mergeDataIntoStyle(
		prev: StyleSpecification | undefined,
		next: StyleSpecification
	): StyleSpecification {
		if (!prev) return next;
		const sources = { ...next.sources };
		for (const [id, src] of Object.entries(prev.sources))
			if (DATA_SOURCES.has(id)) sources[id] = src;
		const layers = [...next.layers, ...prev.layers.filter((l) => DATA_LAYERS.has(l.id))];
		return { ...next, sources, layers };
	}

	function restyle() {
		if (!map || !loaded) return;
		colors = computeColors();
		activity?.setColors(colors);
		map.setStyle(baseStyle(), { diff: true, transformStyle: mergeDataIntoStyle });
		map.once('styledata', () => {
			if (!map || !colors) return;
			// Si el estilo se recargó entero (sin diff), se vuelven a agregar las capas de datos.
			if (!map.getSource(SRC.nodes)) setupData();
			recolorDataLayers(map, colors);
			refreshImages();
			applyVisibility();
			applySelection(selection.nodeId);
		});
	}

	onMount(() => {
		let disposed = false;
		const unsubs: (() => void)[] = [];
		const fps = new DragFpsMonitor(() => {
			if (prefs.solid || prefs.fpsSuggested) return;
			prefs.markFpsSuggested();
			toasts.show(m.map_fps_suggest(), {
				kind: 'info',
				timeout: 15000,
				action: { label: m.map_fps_action(), run: () => prefs.setSolid(true) }
			});
		});

		(async () => {
			await site.load();
			tiles = await fetchTiles();
			if (disposed || !container) return;
			colors = computeColors();
			const s = site.data;
			try {
				maplibregl.setWorkerUrl(workerUrl);
				map = new maplibregl.Map({
					container,
					style: baseStyle(),
					center: [s.center[1], s.center[0]],
					zoom: s.zoom,
					minZoom: 2,
					maxZoom: 19,
					maxPitch: 0,
					pitchWithRotate: false,
					touchPitch: false,
					attributionControl: false,
					renderWorldCopies: false,
					fadeDuration: 0,
					// El estilo y las capas los arma este código (con pruebas): validarlos en cada
					// addLayer cuesta cientos de ms al arrancar en un teléfono. Solo en desarrollo.
					validateStyle: import.meta.env.DEV,
					locale: {
						'Map.Title': m.map_label(),
						'AttributionControl.ToggleAttribution': m.map_toggle_attribution()
					}
				});
			} catch (err) {
				console.error('no se pudo crear el mapa', err);
				error = true;
				mapController.failed = true;
				mapController.markIdle();
				return;
			}
			if (s.bounds) {
				map.fitBounds(
					[
						[s.bounds[0], s.bounds[1]],
						[s.bounds[2], s.bounds[3]]
					],
					{ duration: 0, padding: 24 }
				);
			}
			map.setPadding(padding);
			lastPadding = JSON.stringify(padding);
			map.addControl(new maplibregl.AttributionControl({ compact: true }), 'bottom-left');
			// Acceso para depurar y para las pruebas e2e (solo lectura del estado del mapa).
			(window as unknown as { __meshboxMap?: MlMap }).__meshboxMap = map;
			const canvas = map.getCanvas();
			canvas.setAttribute('aria-label', m.map_label());
			canvas.setAttribute('aria-describedby', 'map-hint');

			activity = new ActivityLayer(map, colors, reduced);
			// Los pulsos empiezan después del primer dibujo completo: no compiten con la carga.
			let pulses = false;
			map.once('idle', () => {
				mapController.markIdle();
				setTimeout(() => (pulses = true), 2000);
			});
			unsubs.push(
				live.core.on('activity', (ev) => {
					if (pulses) activity?.push(ev, live.nodes);
				})
			);

			// MapLibre 6: `styleimagemissing` solo avisa; los íconos se generan con el resolvedor.
			map.setMissingStyleImageResolver((id) => addMissingImage(id));
			map.on('load', () => {
				loaded = true;
				setupData();
				mapController.register({
					zoomIn: () => map?.zoomIn({ duration: reduced() ? 0 : 250 }),
					zoomOut: () => map?.zoomOut({ duration: reduced() ? 0 : 250 }),
					resetNorth: () => map?.resetNorth({ duration: reduced() ? 0 : 400 }),
					locate,
					fitNodes,
					focusNode
				});
			});
			map.on('rotate', () => (mapController.bearing = map?.getBearing() ?? 0));
			map.on('click', (e) => void onClick(e));
			map.on('mousemove', onMove);
			map.on('zoomstart', closeSpider);
			map.on('dragstart', () => {
				if (!prefs.solid) fps.start();
			});
			map.on('dragend', () => fps.stop());
			map.on('error', (e) => {
				// Errores de teselas o recursos: se registran sin romper la interfaz.
				console.warn('mapa:', e.error?.message ?? e);
			});
		})();

		return () => {
			disposed = true;
			unsubs.forEach((u) => u());
			fps.stop();
			activity?.destroy();
			updateNodes.cancel();
			mapController.register(null);
			map?.remove();
			map = null;
		};
	});

	async function locate(): Promise<void> {
		if (!map || !('geolocation' in navigator)) {
			toasts.show(m.map_locate_error(), { kind: 'error' });
			return;
		}
		await new Promise<void>((resolve) => {
			navigator.geolocation.getCurrentPosition(
				(pos) => {
					const p: [number, number] = [pos.coords.longitude, pos.coords.latitude];
					source(SRC.me)?.setData({
						type: 'FeatureCollection',
						features: [
							{ type: 'Feature', geometry: { type: 'Point', coordinates: p }, properties: {} }
						]
					} as never);
					if (reduced()) map?.jumpTo({ center: p, zoom: Math.max(map.getZoom(), 14) });
					else map?.flyTo({ center: p, zoom: Math.max(map.getZoom(), 14) });
					resolve();
				},
				() => {
					toasts.show(m.map_locate_error(), { kind: 'error' });
					resolve();
				},
				{ enableHighAccuracy: true, timeout: 10_000, maximumAge: 60_000 }
			);
		});
	}

	function fitNodes() {
		if (!map) return;
		const pts = live
			.nodeList()
			.filter((n) => isValidLatLon(n.lat, n.lon))
			.map((n) => [n.lon, n.lat] as [number, number]);
		const b = boundsOf(pts);
		if (b) map.fitBounds(b, { padding: 48, maxZoom: 14, duration: reduced() ? 0 : 600 });
	}

	// ------------------------------------------------------------ efectos

	$effect(() => {
		void [
			live.version,
			filters.value,
			clock.now,
			site.data.thresholds,
			mapData.links,
			prefs.layers.uncertainty
		];
		if (loaded) updateNodes();
	});

	$effect(() => {
		void mapData.waypoints;
		if (loaded) untrack(updateWaypoints);
	});

	$effect(() => {
		void [selection.track, selection.cursor];
		if (loaded) untrack(updateTrack);
	});

	$effect(() => {
		void [selection.traceroute, live.version];
		if (loaded) untrack(updateRoute);
	});

	$effect(() => {
		const id = selection.nodeId;
		const tick = selection.focusTick;
		void live.hasData;
		if (!loaded) return;
		untrack(() => {
			applySelection(id);
			updateSelected();
			// Centrar al abrir la ficha (o al pedirlo de nuevo), cuando ya se conoce la posición.
			if (id && live.nodes.has(id) && (id !== lastFocused || tick !== lastTick)) {
				lastFocused = id;
				lastTick = tick;
				focusNode(id);
			}
			if (!id) lastFocused = null;
		});
	});

	$effect(() => {
		void [
			prefs.layers.links,
			prefs.layers.activity,
			prefs.layers.waypoints,
			prefs.layers.uncertainty,
			site.data.features
		];
		if (loaded) untrack(applyVisibility);
	});

	$effect(() => {
		// Capa base: elección del visitante o la del sitio, extracto disponible e idioma de las
		// etiquetas. El tema no elige la capa, pero cambia los colores de lo que va encima.
		void [
			prefs.base,
			prefs.resolvedTheme,
			site.data.layers,
			site.data.has_tiles,
			i18n.locale,
			site.data.accent
		];
		if (loaded) untrack(restyle);
	});

	$effect(() => {
		const p = padding;
		const key = JSON.stringify(p);
		if (!map || !loaded || key === lastPadding) return;
		lastPadding = key;
		// Una animación en curso (centrar un nodo) ya lleva el relleno nuevo; si no, se anima acá.
		if (map.isMoving()) map.once('moveend', () => map?.setPadding(padding));
		else map.easeTo({ padding: p, duration: reduced() ? 0 : 300 });
	});

	$effect(() => {
		void i18n.locale;
		map?.getCanvas().setAttribute('aria-label', m.map_label());
	});
</script>

<div class="map-root" role="region" aria-label={m.map_label()}>
	<div bind:this={container} class="map"></div>
	<p id="map-hint" class="sr-only">{m.map_hint()}</p>
	{#if !loaded && !error}
		<div class="overlay" aria-hidden="true">
			<span class="skeleton pill">{m.map_loading()}</span>
		</div>
	{/if}
	{#if error}
		<div class="overlay error" role="alert">{m.map_error()}</div>
	{/if}
</div>

<style>
	.map-root {
		position: absolute;
		inset: 0;
		z-index: var(--z-map);
		background: var(--bg);
	}

	.map {
		position: absolute;
		inset: 0;
	}

	.overlay {
		position: absolute;
		inset: 0;
		display: grid;
		place-items: center;
		pointer-events: none;
		color: var(--text-2);
	}

	.overlay.error {
		color: var(--text-1);
	}

	.pill {
		padding: 8px 14px;
		border-radius: 999px;
		font-size: 0.875rem;
		color: var(--text-2);
	}

	.map-root :global(.maplibregl-ctrl-bottom-left) {
		bottom: var(--attr-bottom, 0px);
		left: var(--attr-left, 0px);
		max-width: calc(100% - var(--attr-left, 0px) - var(--attr-right, 0px));
		transition: bottom var(--dur-2) var(--ease);
	}
</style>
