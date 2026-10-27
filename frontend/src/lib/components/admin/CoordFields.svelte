<!--
  Latitud y longitud como texto (sin flechitas): se escriben con punto o coma decimal, y pegar
  «lat, lon» copiado de Google Maps, un enlace con @lat,lon o grados, minutos y segundos en
  cualquiera de los dos campos completa ambos. Lo que cambia por otro lado (el mapa) se muestra,
  salvo en el campo que se está escribiendo.
-->
<script lang="ts">
	import { m } from '$lib/paraglide/messages';
	import { formatCoordinate, parseCoordinates, parseNumber } from '$lib/utils/coords';
	import Field from './Field.svelte';

	interface Props {
		lat: number | null;
		lon: number | null;
		latLabel: string;
		lonLabel: string;
		error?: string | null;
	}

	let {
		lat = $bindable(null),
		lon = $bindable(null),
		latLabel,
		lonLabel,
		error = null
	}: Props = $props();

	type Which = 'lat' | 'lon';
	let text = $state<Record<Which, string>>({
		lat: formatCoordinate(lat),
		lon: formatCoordinate(lon)
	});
	let bad = $state<Record<Which, boolean>>({ lat: false, lon: false });
	let editing: Which | null = null;

	$effect(() => {
		const v = lat;
		if (editing !== 'lat') text.lat = formatCoordinate(v);
	});
	$effect(() => {
		const v = lon;
		if (editing !== 'lon') text.lon = formatCoordinate(v);
	});

	function setBoth(p: { lat: number; lon: number }): void {
		lat = p.lat;
		lon = p.lon;
		text = { lat: formatCoordinate(p.lat), lon: formatCoordinate(p.lon) };
		bad = { lat: false, lon: false };
	}

	function typed(which: Which, value: string): void {
		text[which] = value;
		const v = parseNumber(value);
		const ok = v !== null && Math.abs(v) <= (which === 'lat' ? 90 : 180);
		bad[which] = value.trim() !== '' && !ok;
		if (!ok) return;
		if (which === 'lat') lat = v;
		else lon = v;
	}

	function pasted(e: ClipboardEvent): void {
		const p = parseCoordinates(e.clipboardData?.getData('text') ?? '');
		if (!p) return;
		e.preventDefault();
		setBoth(p);
	}

	function left(which: Which): void {
		editing = null;
		if (bad[which]) {
			// «lat, lon» escrito a mano en un solo campo también vale.
			const p = parseCoordinates(text[which]);
			if (p) setBoth(p);
			return;
		}
		text[which] = formatCoordinate(which === 'lat' ? lat : lon);
	}
</script>

{#each [['lat', latLabel], ['lon', lonLabel]] as [which, label] (which)}
	{@const w = which as Which}
	<Field
		{label}
		hint={w === 'lat' ? m.adm_coord_hint() : undefined}
		error={bad[w] ? m.adm_coord_invalid() : w === 'lat' ? error : null}
	>
		{#snippet control({ id, describedby, invalid })}
			<input
				{id}
				type="text"
				class="adm-input mono"
				autocomplete="off"
				spellcheck="false"
				value={text[w]}
				aria-describedby={describedby}
				aria-invalid={invalid || undefined}
				onfocus={() => (editing = w)}
				oninput={(e) => typed(w, e.currentTarget.value)}
				onpaste={pasted}
				onblur={() => left(w)}
			/>
		{/snippet}
	</Field>
{/each}
