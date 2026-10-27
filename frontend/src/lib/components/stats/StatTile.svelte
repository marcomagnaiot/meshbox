<!-- Tarjeta de estadística: etiqueta, valor (cifras proporcionales) y detalle opcional. -->
<script lang="ts">
	import type { Snippet } from 'svelte';

	interface Props {
		label: string;
		value: string;
		hint?: string;
		lead?: Snippet;
	}

	let { label, value, hint, lead }: Props = $props();
</script>

<div class="tile card">
	<span class="label"
		>{#if lead}{@render lead()}{/if}{label}</span
	>
	<span class="value">{value}</span>
	{#if hint}<span class="hint">{hint}</span>{/if}
</div>

<style>
	.tile {
		display: flex;
		flex-direction: column;
		gap: 2px;
		padding: 12px 14px;
		min-width: 0;
	}

	.label {
		display: inline-flex;
		align-items: center;
		gap: 6px;
		font-size: 0.75rem;
		color: var(--text-2);
	}

	.value {
		font-size: 1.5rem;
		line-height: 1.2;
		font-weight: 700;
	}

	.hint {
		font-size: 0.75rem;
		color: var(--text-2);
	}

	@container (max-width: 150px) {
		.value {
			font-size: 1.25rem;
		}
	}
</style>
