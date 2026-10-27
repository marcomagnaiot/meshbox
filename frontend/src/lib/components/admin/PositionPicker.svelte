<!--
  Elegir un punto exacto (posición fija de una placa): la marca queda fija en el centro y se
  mueve el mapa debajo, con la imagen satelital si el sitio la permite (se ve el techo).
  Latitud y longitud se pueden escribir o pegar; el mapa las sigue.
-->
<script lang="ts">
	import MapPin from '@lucide/svelte/icons/map-pin';
	import type { Map as MlMap } from 'maplibre-gl';
	import { onMount } from 'svelte';
	import { i18n } from '$lib/i18n/locale.svelte';
	import { buildBaseStyle, type TileJson } from '$lib/map/style';
	import { m } from '$lib/paraglide/messages';
	import { site } from '$lib/stores/site.svelte';

	interface Props {
		lat: number | null;
		lon: number | null;
		label: string;
		height?: string;
	}

	let { lat = $bindable(null), lon = $bindable(null), label, height = '320px' }: Props = $props();

	let container: HTMLDivElement | null = $state(null);
	let map: MlMap | null = null;
	let failed = $state(false);
	/** Último punto que puso el mapa: si lat/lon cambian por otro lado, el mapa va hasta ahí. */
	let fromMap: [number, number] | null = null;

	const round = (v: number) => Math.round(v * 1e6) / 1e6; // ~0,1 m

	$effect(() => {
		const a = lat;
		const b = lon;
		if (!map || a === null || b === null || !Number.isFinite(a) || !Number.isFinite(b)) return;
		if (fromMap && fromMap[0] === a && fromMap[1] === b) return;
		map.jumpTo({ center: [b, a] });
	});

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
				const satellite = site.data.layers.satellite;
				const style = buildBaseStyle({
					base: satellite ? 'satellite' : 'light',
					tiles,
					lang: i18n.locale,
					satelliteAllowed: satellite,
					esriAttribution: 'Esri, Maxar, Earthstar Geographics',
					background: '#1b2230'
				});
				const known = lat !== null && lon !== null;
				map = new ml.Map({
					container,
					style,
					center: known
						? [lon as number, lat as number]
						: [site.data.center[1], site.data.center[0]],
					zoom: known ? 17.5 : site.data.zoom,
					maxZoom: 19,
					maxPitch: 0,
					dragRotate: false,
					attributionControl: { compact: true }
				});
				map.getCanvas().setAttribute('aria-label', label);
				map.on('move', () => {
					if (!map) return;
					const c = map.getCenter();
					fromMap = [round(c.lat), round(c.lng)];
					[lat, lon] = fromMap;
				});
				// Tocar un punto lo lleva al centro (más fácil que arrastrar en el celular).
				map.on('click', (e) => map?.easeTo({ center: e.lngLat }));
			} catch (err) {
				console.warn('selector de posición:', err);
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

{#if failed}
	<p class="adm-note warn">{m.adm_map_unavailable()}</p>
{:else}
	<div class="wrap" style="height: {height}">
		<div class="map" bind:this={container}></div>
		<span class="pin" aria-hidden="true"><MapPin size={34} strokeWidth={2.4} /></span>
	</div>
{/if}

<style>
	.wrap {
		position: relative;
		width: 100%;
		border-radius: var(--r-md);
		overflow: hidden;
		border: 1px solid var(--line);
		background: var(--surface-3);
	}

	.map {
		position: absolute;
		inset: 0;
	}

	/* La punta de la marca coincide con el centro del mapa. */
	.pin {
		position: absolute;
		left: 50%;
		top: 50%;
		transform: translate(-50%, -100%);
		color: #ff3b30;
		filter: drop-shadow(0 1px 2px rgb(0 0 0 / 0.6));
		pointer-events: none;
	}
</style>
