<!-- Pares etiqueta-valor en una grilla (<dl>). Valores vacíos se muestran como "—". -->
<script lang="ts">
	import type { KV } from './types';

	interface Props {
		items: KV[];
		columns?: number;
	}

	let { items, columns = 2 }: Props = $props();
</script>

<dl class="kv" style="--kv-cols: {columns}">
	{#each items as it, i (i)}
		<div class="pair">
			<dt>{it.label}</dt>
			<dd class:adm-mono={it.mono}>
				{#if it.content}{@render it.content()}{:else}{it.value === null ||
					it.value === undefined ||
					it.value === ''
						? '—'
						: it.value}{/if}
			</dd>
		</div>
	{/each}
</dl>

<style>
	.kv {
		display: grid;
		grid-template-columns: repeat(var(--kv-cols), minmax(0, 1fr));
		gap: 12px 20px;
		margin: 0;
	}

	@media (max-width: 640px) {
		.kv {
			grid-template-columns: minmax(0, 1fr);
		}
	}

	.pair {
		min-width: 0;
	}

	dt {
		font-size: 0.75rem;
		color: var(--text-2);
	}

	dd {
		margin: 2px 0 0;
		font-size: 0.875rem;
		font-weight: 600;
		font-variant-numeric: tabular-nums;
		overflow-wrap: anywhere;
	}
</style>
