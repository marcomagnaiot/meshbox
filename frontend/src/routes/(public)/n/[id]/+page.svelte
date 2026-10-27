<!-- Ficha de nodo: enlace directo /n/!xxxxxxxx (centra el mapa y abre la ficha). -->
<script lang="ts">
	import { page } from '$app/state';
	import { live } from '$lib/stores/live.svelte';
	import { site } from '$lib/stores/site.svelte';
	import { ui } from '$lib/stores/ui.svelte';
	import { displayName } from '$lib/utils/nodes';
	import NodeDetail from '$lib/components/node/NodeDetail.svelte';

	const id = $derived(page.params.id ?? '');
	const node = $derived(live.node(id));
</script>

<svelte:head><title>{node ? displayName(node) : id} · {site.data.name}</title></svelte:head>

{#key id}
	{#if ui.isMobile}
		<div class="page-scroll"><NodeDetail nodeId={id} /></div>
	{:else}
		<NodeDetail nodeId={id} />
	{/if}
{/key}
