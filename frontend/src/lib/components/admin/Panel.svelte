<!-- Tarjeta de una parte de la sección: título (h2), descripción, acciones y contenido. -->
<script lang="ts">
	import type { Snippet } from 'svelte';

	interface Props {
		title?: string;
		description?: string;
		actions?: Snippet;
		children: Snippet;
		/** Sin relleno interno (tablas a todo el ancho). */
		flush?: boolean;
		tone?: 'default' | 'danger';
	}

	let { title, description, actions, children, flush = false, tone = 'default' }: Props = $props();
	const uid = $props.id();
</script>

<section
	class="panel"
	class:flush
	class:danger={tone === 'danger'}
	aria-labelledby={title ? `p-${uid}` : undefined}
>
	{#if title || actions}
		<header class="head">
			<div class="titles">
				{#if title}<h2 id="p-{uid}">{title}</h2>{/if}
				{#if description}<p>{description}</p>{/if}
			</div>
			{#if actions}<div class="actions">{@render actions()}</div>{/if}
		</header>
	{/if}
	<div class="body">{@render children()}</div>
</section>

<style>
	.panel {
		border: 1px solid var(--line);
		border-radius: var(--r-md);
		background: var(--surface-1);
		min-width: 0;
	}

	.panel.danger {
		border-color: color-mix(in oklch, var(--danger) 45%, var(--line));
	}

	.head {
		display: flex;
		flex-wrap: wrap;
		align-items: flex-start;
		justify-content: space-between;
		gap: 8px 16px;
		padding: 16px 16px 0;
	}

	.titles {
		min-width: 0;
		flex: 1 1 260px;
	}

	h2 {
		margin: 0;
		font-size: 1rem;
		font-weight: 650;
	}

	.titles p {
		margin: 4px 0 0;
		font-size: 0.8125rem;
		color: var(--text-2);
		line-height: 1.45;
	}

	.actions {
		display: flex;
		flex-wrap: wrap;
		gap: 8px;
	}

	.body {
		padding: 16px;
	}

	.flush .body {
		padding: 12px 0 0;
	}
</style>
