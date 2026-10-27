<!--
  Elegir centro, zoom y límites (o la caja del extracto) moviendo el mapa (18.1.4, 18.2):
  "usar esta vista" toma lo que se ve. La caja elegida se dibuja como rectángulo y los nodos
  conocidos como puntos de referencia. Los valores también se pueden escribir a mano.
-->
<script lang="ts">
	import Crosshair from '@lucide/svelte/icons/crosshair';
	import Frame from '@lucide/svelte/icons/frame';
	import X from '@lucide/svelte/icons/x';
	import type { GeoJSONSource, Map as MlMap } from 'maplibre-gl';
	import { onMount } from 'svelte';
	import { publicApi } from '$lib/api/public';
	import { i18n } from '$lib/i18n/locale.svelte';
	import { buildBaseStyle, type TileJson } from '$lib/map/style';
	import { m } from '$lib/paraglide/messages';
	import { site } from '$lib/stores/site.svelte';
	import Button from '$lib/components/ui/Button.svelte';

	interface Props {
		/** [lat, lon] */
		center: number[];
		zoom?: number | null;
		/** [oeste, sur, este, norte] */
		bounds: number[] | null;
		/** Qué se elige: centro y límites del sitio, o solo una caja (extracto). */
		mode?: 'site' | 'bbox';
		label: string;
		height?: string;
	}

	let {
		center = $bindable([0, 0]),
		zoom = $bindable(11),
		bounds = $bindable(null),
		mode = 'site',
		label,
		height = '320px'
	}: Props = $props();

	let container: HTMLDivElement | null = $state(null);
	let map: MlMap | null = null;
	let failed = $state(false);
	let ready = $state(false);

	const round = (v: number, d = 5) => Math.round(v * 10 ** d) / 10 ** d;

	function boxFeature(b: number[] | null) {
		if (!b || b.length !== 4) return { type: 'FeatureCollection', features: [] };
		const [w, s, e, n] = b;
		return {
			type: 'FeatureCollection',
			features: [
				{
					type: 'Feature',
					properties: {},
					geometry: {
						type: 'Polygon',
						coordinates: [
							[
								[w, s],
								[e, s],
								[e, n],
								[w, n],
								[w, s]
							]
						]
					}
				}
			]
		};
	}

	$effect(() => {
		const b = bounds;
		if (ready && map)
			(map.getSource('pick-box') as GeoJSONSource | undefined)?.setData(boxFeature(b) as never);
	});

	function useView(): void {
		if (!map) return;
		const c = map.getCenter();
		center = [round(c.lat), round(c.lng)];
		zoom = Math.round(map.getZoom() * 10) / 10;
	}

	function useBounds(): void {
		if (!map) return;
		const b = map.getBounds();
		bounds = [
			round(b.getWest(), 4),
			round(b.getSouth(), 4),
			round(b.getEast(), 4),
			round(b.getNorth(), 4)
		];
	}

	onMount(() => {
		let disposed = false;
		(async () => {
			try {
				const [ml, worker] = await Promise.all([
					import('maplibre-gl'),
					import('maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url'),
					import('maplibre-gl/dist/maplibre-gl.css')
				]);
				let tiles: TileJson | null = null;
				if (site.data.has_tiles) {
					const res = await fetch('/tiles/v.json').catch(() => null);
					if (res?.ok) tiles = (await res.json()) as TileJson;
				}
				if (disposed || !container) return;
				ml.setWorkerUrl(worker.default);
				const style = buildBaseStyle({
					base: tiles ? 'dark' : 'satellite',
					tiles,
					lang: i18n.locale,
					satelliteAllowed: site.data.layers.satellite,
					esriAttribution: 'Esri, Maxar, Earthstar Geographics',
					background: '#1b2230'
				});
				const lat = Number(center?.[0]) || site.data.center[0];
				const lon = Number(center?.[1]) || site.data.center[1];
				map = new ml.Map({
					container,
					style,
					center: [lon, lat],
					zoom: zoom ?? site.data.zoom,
					maxPitch: 0,
					dragRotate: false,
					attributionControl: { compact: true }
				});
				map.getCanvas().setAttribute('aria-label', label);
				map.on('load', async () => {
					if (!map) return;
					map.addSource('pick-box', { type: 'geojson', data: boxFeature(bounds) as never });
					map.addLayer({
						id: 'pick-box-fill',
						type: 'fill',
						source: 'pick-box',
						paint: { 'fill-color': '#22b8cf', 'fill-opacity': 0.12 }
					});
					map.addLayer({
						id: 'pick-box-line',
						type: 'line',
						source: 'pick-box',
						paint: { 'line-color': '#22b8cf', 'line-width': 2, 'line-dasharray': [2, 1] }
					});
					try {
						const list = await publicApi.nodes();
						const features = list.nodes
							.filter((n) => typeof n.lat === 'number' && typeof n.lon === 'number')
							.map((n) => ({
								type: 'Feature',
								properties: {},
								geometry: { type: 'Point', coordinates: [n.lon, n.lat] }
							}));
						map?.addSource('pick-nodes', {
							type: 'geojson',
							data: { type: 'FeatureCollection', features } as never
						});
						map?.addLayer({
							id: 'pick-nodes',
							type: 'circle',
							source: 'pick-nodes',
							paint: {
								'circle-radius': 4,
								'circle-color': '#56d57b',
								'circle-stroke-color': '#0f141b',
								'circle-stroke-width': 1.5
							}
						});
					} catch {
						// sin nodos de referencia
					}
					ready = true;
				});
			} catch (err) {
				console.warn('selector de mapa:', err);
				failed = true;
			}
		})();
		return () => {
			disposed = true;
			map?.remove();
			map = null;
		};
	});
</script>

<div class="picker">
	{#if failed}
		<p class="adm-note warn">{m.adm_map_unavailable()}</p>
	{:else}
		<div class="map" bind:this={container} style="height: {height}"></div>
	{/if}
	<div class="adm-row">
		{#if mode === 'site'}
			<Button size="sm" icon={Crosshair} onclick={useView} disabled={!ready}
				>{m.adm_map_use_view()}</Button
			>
		{/if}
		<Button size="sm" icon={Frame} onclick={useBounds} disabled={!ready}>
			{mode === 'site' ? m.adm_map_use_bounds() : m.adm_map_use_box()}
		</Button>
		{#if bounds && mode === 'site'}
			<Button size="sm" variant="ghost" icon={X} onclick={() => (bounds = null)}
				>{m.adm_map_clear_bounds()}</Button
			>
		{/if}
	</div>
</div>

<style>
	.picker {
		display: flex;
		flex-direction: column;
		gap: 10px;
	}

	.map {
		width: 100%;
		border-radius: var(--r-md);
		overflow: hidden;
		border: 1px solid var(--line);
		background: var(--surface-3);
	}
</style>
