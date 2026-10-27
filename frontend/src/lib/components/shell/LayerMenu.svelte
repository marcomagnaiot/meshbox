<!-- Selector de capas: mapa base, capas de datos y leyenda (popover sólido). -->
<script lang="ts">
	import { Popover } from 'bits-ui';
	import Layers from '@lucide/svelte/icons/layers';
	import type { BaseLayer } from '$lib/api/types';
	import { wantedBase } from '$lib/map/style';
	import { m } from '$lib/paraglide/messages';
	import { prefs } from '$lib/stores/prefs.svelte';
	import { site } from '$lib/stores/site.svelte';
	import { filters } from '$lib/stores/ui.svelte';
	import Segmented from '$lib/components/ui/Segmented.svelte';
	import Toggle from '$lib/components/ui/Toggle.svelte';
	import MapLegend from './MapLegend.svelte';

	interface Props {
		side?: 'left' | 'bottom' | 'top';
	}

	let { side = 'left' }: Props = $props();

	const s = $derived(site.data);
	const current = $derived<BaseLayer>(wantedBase(prefs.base, s.layers.default));
	const options = $derived([
		{ value: 'dark' as BaseLayer, label: m.map_base_dark(), disabled: !s.has_tiles },
		{ value: 'light' as BaseLayer, label: m.map_base_light(), disabled: !s.has_tiles },
		{
			value: 'satellite' as BaseLayer,
			label: m.map_base_satellite(),
			disabled: !s.layers.satellite
		}
	]);
</script>

<Popover.Root>
	<Popover.Trigger class="btn-icon" aria-label={m.map_layers()} title={m.map_layers()}>
		<Layers size={20} aria-hidden="true" />
	</Popover.Trigger>
	<Popover.Portal>
		<!-- Al costado de la pila de controles, alineado arriba con el botón (no tapa la barra). -->
		<Popover.Content
			class="menu-surface layer-menu"
			{side}
			align={side === 'left' ? 'start' : 'center'}
			sideOffset={10}
			collisionPadding={12}
		>
			<p class="menu-heading">{m.map_base()}</p>
			<Segmented
				label={m.map_base()}
				{options}
				value={current}
				size="sm"
				onchange={(v) => prefs.setBase(v)}
			/>
			{#if !s.has_tiles}
				<p class="hint">{s.layers.satellite ? m.map_no_tiles() : m.map_no_base()}</p>
			{/if}
			<p class="menu-heading">{m.map_data_layers()}</p>
			<div class="toggles">
				{#if s.features.links}
					<Toggle
						label={m.map_layer_links()}
						checked={prefs.layers.links}
						onchange={(v) => prefs.setLayer('links', v)}
					/>
				{/if}
				{#if s.features.activity}
					<Toggle
						label={m.map_layer_activity()}
						checked={prefs.layers.activity}
						onchange={(v) => prefs.setLayer('activity', v)}
					/>
				{/if}
				{#if s.features.waypoints}
					<Toggle
						label={m.map_layer_waypoints()}
						checked={prefs.layers.waypoints}
						onchange={(v) => prefs.setLayer('waypoints', v)}
					/>
				{/if}
				<Toggle
					label={m.map_layer_uncertainty()}
					checked={prefs.layers.uncertainty}
					onchange={(v) => prefs.setLayer('uncertainty', v)}
				/>
				<Toggle
					label={m.map_layer_inactive()}
					checked={filters.value.showInactive}
					onchange={(v) => filters.set('showInactive', v)}
				/>
			</div>
			<p class="menu-heading">{m.map_legend()}</p>
			<div class="legend">
				<MapLegend activity={s.features.activity && prefs.layers.activity} />
			</div>
		</Popover.Content>
	</Popover.Portal>
</Popover.Root>

<style>
	:global(.layer-menu) {
		width: 320px;
		/* Todo el alto libre (la leyenda entra sin desplazar en PC y tableta). */
		max-height: min(var(--bits-floating-available-height, 70dvh), 720px);
	}

	.hint {
		margin: 6px 8px 0;
		font-size: 0.75rem;
		color: var(--text-2);
	}

	.toggles {
		padding: 0 8px;
	}

	.legend {
		padding: 0 8px 4px;
	}
</style>
