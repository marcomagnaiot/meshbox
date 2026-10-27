<!-- Chips de filtro (16.3): se aplican al mapa y a la lista de nodos a la vez. -->
<script lang="ts">
	import CircleDashed from '@lucide/svelte/icons/circle-dashed';
	import RadioTower from '@lucide/svelte/icons/radio-tower';
	import Thermometer from '@lucide/svelte/icons/thermometer';
	import { m } from '$lib/paraglide/messages';
	import { prefs } from '$lib/stores/prefs.svelte';
	import { filters } from '$lib/stores/ui.svelte';
	import Chip from '$lib/components/ui/Chip.svelte';
	import StatusGlyph from '$lib/components/ui/StatusGlyph.svelte';

	interface Props {
		scroll?: boolean;
	}

	let { scroll = true }: Props = $props();
	const v = $derived(filters.value);
</script>

<div class="chips" class:scroll role="group" aria-label={m.filter_label()}>
	<Chip pressed={v.onlyActive} onclick={() => filters.toggle('onlyActive')}>
		{#snippet lead()}<StatusGlyph status="active" size={14} />{/snippet}
		{m.filter_active()}
	</Chip>
	<Chip pressed={v.onlyInfra} icon={RadioTower} onclick={() => filters.toggle('onlyInfra')}>
		{m.filter_infra()}
	</Chip>
	<Chip
		pressed={v.withTelemetry}
		icon={Thermometer}
		onclick={() => filters.toggle('withTelemetry')}
	>
		{m.filter_with_telemetry()}
	</Chip>
	<Chip pressed={v.showInactive} onclick={() => filters.toggle('showInactive')}>
		{#snippet lead()}<StatusGlyph status="inactive" size={14} />{/snippet}
		{m.filter_show_inactive()}
	</Chip>
	<!-- Atajo de la capa "Incertidumbre de posición" del menú de capas (misma preferencia). -->
	<Chip
		pressed={prefs.layers.uncertainty}
		icon={CircleDashed}
		onclick={() => prefs.setLayer('uncertainty', !prefs.layers.uncertainty)}
	>
		{m.filter_precision()}
	</Chip>
</div>

<style>
	.chips {
		display: flex;
		gap: 8px;
		flex-wrap: wrap;
		padding: 2px 0;
	}

	.chips.scroll {
		flex-wrap: nowrap;
		overflow-x: auto;
		scrollbar-width: none;
		padding: 4px 2px;
		-webkit-mask-image: linear-gradient(90deg, #000 92%, transparent);
		mask-image: linear-gradient(90deg, #000 92%, transparent);
	}

	.chips.scroll::-webkit-scrollbar {
		display: none;
	}
</style>
