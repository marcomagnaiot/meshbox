<!-- Inicio: el mapa con su resumen; en el panel, la lista de nodos (alternativa accesible al mapa). -->
<script lang="ts">
	import { m } from '$lib/paraglide/messages';
	import { site } from '$lib/stores/site.svelte';
	import { ui } from '$lib/stores/ui.svelte';
	import NodesList from '$lib/components/node/NodesList.svelte';
</script>

<h1 class="sr-only">{site.data.name} · {m.nav_map()}</h1>
<NodesList chips={!ui.isMobile} />
