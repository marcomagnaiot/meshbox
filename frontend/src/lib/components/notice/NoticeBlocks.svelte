<!--
  Aviso de privacidad en bloques JSON (13.5): el servidor convierte el Markdown en una
  estructura con lista blanca y acá se dibuja con componentes. Prohibido {@html}.
-->
<script lang="ts">
	import type { NoticeBlock } from '$lib/api/types';
	import NoticeInline from './NoticeInline.svelte';

	interface Props {
		blocks: NoticeBlock[];
		/** Nivel del título más alto disponible (h2 por defecto). */
		headingOffset?: number;
	}

	let { blocks, headingOffset = 0 }: Props = $props();

	function level(t: string): number {
		const n = Number(t.slice(1));
		return Math.min(6, Math.max(2, n + headingOffset));
	}
</script>

<div class="notice">
	{#each blocks as block, i (i)}
		{#if block.t === 'p'}
			<p><NoticeInline items={block.c} /></p>
		{:else if block.t === 'ul'}
			<ul>
				{#each block.c as item, j (j)}
					<li><NoticeInline items={item} /></li>
				{/each}
			</ul>
		{:else if block.t === 'h2' || block.t === 'h3' || block.t === 'h4'}
			<svelte:element this={`h${level(block.t)}`} class="nh"
				><NoticeInline items={block.c} /></svelte:element
			>
		{/if}
	{/each}
</div>

<style>
	.notice {
		font-size: 0.9375rem;
		line-height: 1.55;
		color: var(--text-1);
	}

	.notice p {
		margin: 0 0 12px;
	}

	.notice ul {
		margin: 0 0 12px;
		padding-left: 20px;
	}

	.notice li {
		margin: 4px 0;
	}

	.notice :global(.nh) {
		margin: 16px 0 8px;
		font-size: 1rem;
		font-weight: 650;
	}

	.notice :global(code) {
		font-family: ui-monospace, 'Cascadia Code', Menlo, monospace;
		font-size: 0.875em;
		background: var(--fill-1);
		padding: 1px 5px;
		border-radius: 5px;
	}
</style>
