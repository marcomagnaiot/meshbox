<!--
  Fijar la posición de un nodo en el mapa: la placa conectada o uno administrado a distancia.
  Mapa, coordenadas (se pueden pegar de Google Maps) y altura; con HTTPS, la ubicación del
  dispositivo. `onsave` devuelve si se guardó, y entonces se cierra.
-->
<script lang="ts">
	import LocateFixed from '@lucide/svelte/icons/locate-fixed';
	import MapPin from '@lucide/svelte/icons/map-pin';
	import { untrack } from 'svelte';
	import { m } from '$lib/paraglide/messages';
	import Button from '$lib/components/ui/Button.svelte';
	import Modal from '$lib/components/ui/Modal.svelte';
	import CoordFields from '$lib/components/admin/CoordFields.svelte';
	import NumberField from '$lib/components/admin/NumberField.svelte';
	import PositionPicker from '$lib/components/admin/PositionPicker.svelte';

	interface Props {
		open: boolean;
		title: string;
		description: string;
		initial: { lat: number | null; lon: number | null; alt: number | null };
		/** Aviso debajo del formulario (cómo se comparte la posición). */
		note?: string;
		onsave: (lat: number, lon: number, alt: number) => Promise<boolean>;
	}

	let { open = $bindable(false), title, description, initial, note, onsave }: Props = $props();

	let lat = $state<number | null>(null);
	let lon = $state<number | null>(null);
	let alt = $state<number | null>(0);
	let error = $state<string | null>(null);
	let saving = $state(false);
	let wasOpen = false;
	const canGeo =
		typeof window !== 'undefined' && window.isSecureContext && 'geolocation' in navigator;

	$effect.pre(() => {
		// Cada vez que se abre arranca de la posición que tiene el nodo.
		if (open && !wasOpen) {
			untrack(() => {
				lat = initial.lat;
				lon = initial.lon;
				alt = initial.alt ?? 0;
				error = null;
			});
		}
		wasOpen = open;
	});

	function useMyLocation(): void {
		error = null;
		navigator.geolocation.getCurrentPosition(
			(p) => {
				lat = Math.round(p.coords.latitude * 1e6) / 1e6;
				lon = Math.round(p.coords.longitude * 1e6) / 1e6;
				if (p.coords.altitude !== null) alt = Math.round(p.coords.altitude);
			},
			() => (error = m.adm_cli_geo_failed()),
			{ enableHighAccuracy: true, timeout: 15_000 }
		);
	}

	async function save(e: SubmitEvent): Promise<void> {
		e.preventDefault();
		const la = Number(lat);
		const lo = Number(lon);
		if (
			lat === null ||
			lon === null ||
			!Number.isFinite(la) ||
			!Number.isFinite(lo) ||
			Math.abs(la) > 90 ||
			Math.abs(lo) > 180 ||
			(la === 0 && lo === 0)
		) {
			error = m.adm_cli_fix_invalid();
			return;
		}
		saving = true;
		try {
			if (await onsave(la, lo, Math.round(Number(alt) || 0))) open = false;
		} finally {
			saving = false;
		}
	}
</script>

<Modal bind:open {title} size="lg">
	<form class="adm-stack" onsubmit={save}>
		<p class="adm-muted">{description}</p>
		{#if open}
			<PositionPicker bind:lat bind:lon label={title} />
		{/if}
		<div class="adm-grid">
			<CoordFields latLabel={m.adm_cli_lat()} lonLabel={m.adm_cli_lon()} bind:lat bind:lon />
			<NumberField label={m.adm_cli_altitude()} bind:value={alt} step={1} min={-500} max={9000} />
		</div>
		{#if canGeo}
			<div class="adm-row">
				<Button size="sm" variant="ghost" icon={LocateFixed} onclick={useMyLocation}
					>{m.adm_cli_use_my_location()}</Button
				>
			</div>
		{/if}
		{#if note}<p class="adm-note" role="note">{note}</p>{/if}
		{#if error}<p class="adm-note danger" role="alert">{error}</p>{/if}
		<div class="adm-row end">
			<Button variant="ghost" onclick={() => (open = false)}>{m.adm_cancel()}</Button>
			<Button type="submit" variant="primary" icon={MapPin} loading={saving}
				>{m.adm_cli_fix_position()}</Button
			>
		</div>
	</form>
</Modal>
