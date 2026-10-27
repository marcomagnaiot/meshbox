<script lang="ts">
	// En producción la rama se elimina y el catálogo no entra en el build.
	const catalog = import.meta.env.DEV ? import('./Catalog.svelte') : null;
</script>

{#if catalog}
	{#await catalog then mod}
		<mod.default />
	{/await}
{/if}
