<!-- Pila de controles del mapa: una sola superficie glass pequeña con botones de 44 px. -->
<script lang="ts">
	import Compass from '@lucide/svelte/icons/compass';
	import LocateFixed from '@lucide/svelte/icons/locate-fixed';
	import Minus from '@lucide/svelte/icons/minus';
	import Plus from '@lucide/svelte/icons/plus';
	import IconButton from '$lib/components/ui/IconButton.svelte';
	import { mapController } from '$lib/map/controller.svelte';
	import { m } from '$lib/paraglide/messages';
	import LayerMenu from './LayerMenu.svelte';

	interface Props {
		layerSide?: 'left' | 'bottom' | 'top';
		showZoom?: boolean;
	}

	let { layerSide = 'left', showZoom = true }: Props = $props();
	const disabled = $derived(!mapController.ready);
</script>

<div class="stack glass-sm" role="toolbar" aria-label={m.map_layers()} aria-orientation="vertical">
	<LayerMenu side={layerSide} />
	{#if showZoom}
		<IconButton icon={Plus} label={m.map_zoom_in()} onclick={mapController.zoomIn} {disabled} />
		<IconButton icon={Minus} label={m.map_zoom_out()} onclick={mapController.zoomOut} {disabled} />
	{/if}
	<IconButton
		icon={Compass}
		label={m.map_reset_north()}
		onclick={mapController.resetNorth}
		{disabled}
		iconStyle="transform: rotate({-mapController.bearing -
			45}deg); transition: transform var(--dur-1)"
	/>
	<IconButton
		icon={LocateFixed}
		label={m.map_locate()}
		onclick={() => void mapController.locate()}
		disabled={disabled || mapController.locating}
	/>
</div>

<style>
	.stack {
		display: flex;
		flex-direction: column;
		gap: 2px;
		padding: 4px;
		border-radius: var(--r-md);
	}
</style>
