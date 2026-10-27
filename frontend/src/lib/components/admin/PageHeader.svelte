<!-- Encabezado de una sección del panel: ícono, título (h1), descripción y acciones. -->
<script lang="ts">
	import type { Snippet } from 'svelte';
	import { sectionBySlug } from '$lib/admin/sections';
	import { m } from '$lib/paraglide/messages';
	import { site } from '$lib/stores/site.svelte';

	interface Props {
		slug: string;
		actions?: Snippet;
		children?: Snippet;
	}

	let { slug, actions, children }: Props = $props();
	const section = $derived(sectionBySlug(slug));
</script>

<svelte:head>
	<title>{m.adm_page_title({ section: section?.title() ?? '', site: site.data.name })}</title>
</svelte:head>

{#if section}
	<header class="head">
		<span class="icon" aria-hidden="true"><section.icon size={22} /></span>
		<div class="text">
			<h1>{section.title()}</h1>
			<p>{section.description()}</p>
			{@render children?.()}
		</div>
		{#if actions}<div class="actions">{@render actions()}</div>{/if}
	</header>
{/if}

<style>
	.head {
		display: flex;
		flex-wrap: wrap;
		align-items: flex-start;
		gap: 12px 14px;
		margin-bottom: 20px;
	}

	.icon {
		display: grid;
		place-items: center;
		width: 44px;
		height: 44px;
		border-radius: var(--r-md);
		background: var(--accent-soft);
		color: var(--accent-ink);
		flex: none;
	}

	.text {
		flex: 1 1 320px;
		min-width: 0;
	}

	h1 {
		margin: 0;
		font-size: 1.5rem;
		font-weight: 650;
		line-height: 1.2;
	}

	p {
		margin: 4px 0 0;
		color: var(--text-2);
		font-size: 0.875rem;
		line-height: 1.45;
	}

	.actions {
		display: flex;
		flex-wrap: wrap;
		gap: 8px;
	}
</style>
