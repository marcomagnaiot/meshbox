<!--
  Lista virtualizada propia (17.1): filas de alto fijo; solo se dibujan las visibles más un
  margen. Cada fila lleva aria-setsize/aria-posinset para que el lector de pantalla conozca el
  total aunque no estén todas en el documento.
-->
<script lang="ts" generics="T">
	import type { Snippet } from 'svelte';

	interface Props {
		items: T[];
		itemHeight: number;
		key: (item: T) => string | number;
		row: Snippet<[T, number]>;
		overscan?: number;
		label: string;
		/** Contenido antes de las filas (dentro del área desplazable). */
		before?: Snippet;
		empty?: Snippet;
	}

	let { items, itemHeight, key, row, overscan = 6, label, before, empty }: Props = $props();

	let scrollTop = $state(0);
	let viewportH = $state(0);
	let beforeH = $state(0);

	const offset = $derived(Math.max(0, scrollTop - beforeH));
	const start = $derived(Math.max(0, Math.floor(offset / itemHeight) - overscan));
	const end = $derived(
		Math.min(
			items.length,
			Math.ceil((offset + Math.max(viewportH, itemHeight * 8)) / itemHeight) + overscan
		)
	);
	const slice = $derived(items.slice(start, end));
</script>

<div
	class="viewport"
	bind:clientHeight={viewportH}
	onscroll={(e) => (scrollTop = e.currentTarget.scrollTop)}
>
	{#if before}
		<div bind:clientHeight={beforeH}>{@render before()}</div>
	{/if}
	{#if items.length === 0 && empty}
		{@render empty()}
	{:else}
		<div
			role="list"
			aria-label={label}
			class="canvas"
			style="height: {items.length * itemHeight}px"
		>
			{#each slice as item, i (key(item))}
				<div
					role="listitem"
					class="row"
					aria-setsize={items.length}
					aria-posinset={start + i + 1}
					style="transform: translateY({(start + i) * itemHeight}px); height: {itemHeight}px"
				>
					{@render row(item, start + i)}
				</div>
			{/each}
		</div>
	{/if}
</div>

<style>
	.viewport {
		position: relative;
		flex: 1 1 auto;
		min-height: 0;
		overflow-y: auto;
		overscroll-behavior: contain;
		-webkit-overflow-scrolling: touch;
	}

	.canvas {
		position: relative;
	}

	.row {
		position: absolute;
		top: 0;
		left: 0;
		right: 0;
	}
</style>
