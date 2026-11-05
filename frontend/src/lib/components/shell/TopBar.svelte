<!--
  Barra superior (PC y tableta): marca, buscador, paleta de comandos, datos para conectarse a la
  red (si quien administra los cargó), Acerca y apariencia.
-->
<script lang="ts">
	import Command from '@lucide/svelte/icons/command';
	import Info from '@lucide/svelte/icons/info';
	import RadioTower from '@lucide/svelte/icons/radio-tower';
	import { i18n } from '$lib/i18n/locale.svelte';
	import { joinSummary } from '$lib/join';
	import { page } from '$app/state';
	import { m } from '$lib/paraglide/messages';
	import { site } from '$lib/stores/site.svelte';
	import { ui } from '$lib/stores/ui.svelte';
	import AppearanceMenu from './AppearanceMenu.svelte';
	import SearchBox from './SearchBox.svelte';

	interface Props {
		searchInput?: HTMLInputElement | null;
		compact?: boolean;
	}

	let { searchInput = $bindable(null), compact = false }: Props = $props();
	const join = $derived(site.data.join ? joinSummary(site.data.join, i18n.locale) : '');
</script>

<header class="topbar glass glass-text" class:compact>
	<a href="/" class="brand" aria-label={site.data.name}>
		<img src={site.data.logo_url ?? '/favicon.svg'} alt="" width="28" height="28" />
		{#if !compact}<span class="name">{site.data.name}</span>{/if}
	</a>
	<SearchBox bind:input={searchInput} />
	<button
		type="button"
		class="kbd-btn"
		onclick={() => (ui.paletteOpen = true)}
		aria-keyshortcuts="Control+K Meta+K"
		title={m.palette_open()}
	>
		<Command size={16} aria-hidden="true" />
		<span class="sr-only">{m.palette_open()}</span>
		{#if !compact}<kbd>Ctrl K</kbd>{/if}
	</button>
	<nav class="links" aria-label={m.nav_sections()}>
		{#if join}
			<a
				href="/conectarse"
				class="link join"
				title={m.join_title()}
				aria-current={page.url.pathname === '/conectarse' ? 'page' : undefined}
			>
				<RadioTower size={18} aria-hidden="true" />
				{#if compact}<span class="sr-only">{m.join_title()}: {join}</span>{:else}<span
						class="join-text"><span class="sr-only">{m.join_title()}: </span>{join}</span
					>{/if}
			</a>
		{/if}
		<a
			href="/acerca"
			class="link"
			aria-current={page.url.pathname === '/acerca' ? 'page' : undefined}
		>
			<Info size={18} aria-hidden="true" />
			{#if !compact}<span>{m.nav_about()}</span>{:else}<span class="sr-only">{m.nav_about()}</span
				>{/if}
		</a>
	</nav>
	<AppearanceMenu />
</header>

<style>
	.topbar {
		display: flex;
		align-items: center;
		gap: 10px;
		height: 60px;
		padding: 0 8px 0 12px;
		border-radius: var(--r-lg);
	}

	.brand {
		display: flex;
		align-items: center;
		gap: 10px;
		min-width: 0;
		min-height: 44px;
		color: var(--text-1);
		text-decoration: none;
		font-weight: 650;
	}

	.brand img {
		border-radius: 8px;
		flex: none;
	}

	.name {
		max-width: 220px;
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}

	.kbd-btn {
		display: inline-flex;
		align-items: center;
		gap: 6px;
		height: 44px;
		padding: 0 10px;
		border: 1px solid var(--line);
		border-radius: var(--r-sm);
		background: var(--fill-1);
		color: var(--text-2);
		font: inherit;
		font-size: 0.75rem;
	}

	.kbd-btn:hover {
		color: var(--text-1);
		background: var(--fill-2);
	}

	kbd {
		font-family: inherit;
		font-weight: 600;
	}

	.links {
		display: flex;
		min-width: 0;
		margin-left: auto;
	}

	.join {
		min-width: 0;
	}

	.join-text {
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
		font-variant-numeric: tabular-nums;
	}

	.link {
		display: inline-flex;
		align-items: center;
		gap: 6px;
		min-height: 44px;
		padding: 0 10px;
		border-radius: var(--r-sm);
		color: var(--text-1);
		text-decoration: none;
		font-size: 0.875rem;
		font-weight: 500;
	}

	.link:hover,
	.link[aria-current='page'] {
		background: var(--fill-1);
	}
</style>
