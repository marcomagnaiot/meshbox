<script lang="ts">
	import { m } from '$lib/paraglide/messages';
	import { site } from '$lib/stores/site.svelte';
	import { ui } from '$lib/stores/ui.svelte';
	import NodesList from '$lib/components/node/NodesList.svelte';
</script>

<svelte:head><title>{m.nodes_title()} · {site.data.name}</title></svelte:head>

<h1 class="sr-only">{m.nodes_title()}</h1>
<NodesList full chips={!ui.isMobile} />
