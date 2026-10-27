<!--
  Buscar un lugar por nombre (ciudad, calle, ruta) con Nominatim de OpenStreetMap, desde el
  navegador de quien administra. Una consulta por búsqueda y nunca mientras se escribe, como pide
  la política de uso de Nominatim. Elegir un resultado lleva el mapa hasta ahí.
-->
<script lang="ts" module>
	export interface Place {
		name: string;
		lat: number;
		lon: number;
		/** [oeste, sur, este, norte] */
		bbox: [number, number, number, number] | null;
	}
</script>

<script lang="ts">
	import Search from '@lucide/svelte/icons/search';
	import { i18n } from '$lib/i18n/locale.svelte';
	import { m } from '$lib/paraglide/messages';
	import Button from '$lib/components/ui/Button.svelte';

	interface Props {
		onpick: (place: Place) => void;
	}

	let { onpick }: Props = $props();

	const ENDPOINT = 'https://nominatim.openstreetmap.org/search';

	let query = $state('');
	let results = $state.raw<Place[]>([]);
	let status = $state<'idle' | 'busy' | 'empty' | 'error'>('idle');

	async function search(): Promise<void> {
		const q = query.trim();
		if (q.length < 2 || status === 'busy') return;
		status = 'busy';
		try {
			const params = new URLSearchParams({
				format: 'jsonv2',
				limit: '5',
				'accept-language': i18n.locale,
				q
			});
			const res = await fetch(`${ENDPOINT}?${params}`, { headers: { accept: 'application/json' } });
			if (!res.ok) throw new Error(`Nominatim ${res.status}`);
			const data = (await res.json()) as {
				display_name: string;
				lat: string;
				lon: string;
				boundingbox?: string[];
			}[];
			// Nominatim da la caja como [sur, norte, oeste, este].
			results = data.map((d) => {
				const b = d.boundingbox?.map(Number);
				return {
					name: d.display_name,
					lat: Number(d.lat),
					lon: Number(d.lon),
					bbox: b && b.length === 4 && b.every(Number.isFinite) ? [b[2], b[0], b[3], b[1]] : null
				};
			});
			status = results.length ? 'idle' : 'empty';
		} catch {
			results = [];
			status = 'error';
		}
	}

	function pick(place: Place): void {
		results = [];
		status = 'idle';
		onpick(place);
	}
</script>

<div class="place-search">
	<div class="row">
		<input
			type="search"
			class="adm-input"
			placeholder={m.adm_place_search_placeholder()}
			aria-label={m.adm_place_search()}
			bind:value={query}
			onkeydown={(e) => {
				// Dentro de un formulario, Enter busca y no envía.
				if (e.key === 'Enter') {
					e.preventDefault();
					search();
				}
			}}
		/>
		<Button
			size="sm"
			icon={Search}
			onclick={search}
			disabled={status === 'busy' || query.trim().length < 2}>{m.adm_place_search_button()}</Button
		>
	</div>
	{#if results.length}
		<ul class="results">
			{#each results as r, i (i)}
				<li><button type="button" onclick={() => pick(r)}>{r.name}</button></li>
			{/each}
		</ul>
		<p class="credit">{m.adm_place_search_credit()}</p>
	{:else if status === 'empty'}
		<p class="adm-muted small">{m.adm_place_search_empty()}</p>
	{:else if status === 'error'}
		<p class="adm-note warn">{m.adm_place_search_error()}</p>
	{/if}
</div>

<style>
	.place-search {
		display: flex;
		flex-direction: column;
		gap: 6px;
	}

	.row {
		display: flex;
		gap: 8px;
		align-items: center;
	}

	.row input {
		flex: 1;
		min-width: 0;
	}

	.results {
		margin: 0;
		padding: 4px;
		list-style: none;
		border: 1px solid var(--line);
		border-radius: var(--r-md);
		background: var(--surface-2);
	}

	.results button {
		width: 100%;
		padding: 8px 10px;
		border: 0;
		border-radius: var(--r-sm);
		background: none;
		color: var(--text-1);
		font: inherit;
		font-size: 0.875rem;
		text-align: left;
		cursor: pointer;
	}

	.results button:hover,
	.results button:focus-visible {
		background: var(--fill-2);
	}

	.small,
	.credit {
		margin: 0;
		font-size: 0.75rem;
	}

	.credit {
		color: var(--text-3);
	}
</style>
