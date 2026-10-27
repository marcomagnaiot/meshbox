<!-- Pestañas del panel lateral (PC y tableta): Nodos, Chat, Alertas, Estadísticas. -->
<script lang="ts">
	import Bell from '@lucide/svelte/icons/bell';
	import ChartColumn from '@lucide/svelte/icons/chart-column';
	import List from '@lucide/svelte/icons/list';
	import MessageCircle from '@lucide/svelte/icons/message-circle';
	import { m } from '$lib/paraglide/messages';
	import { alerts } from '$lib/stores/alerts.svelte';
	import type { PublicView } from '$lib/stores/view';

	interface Props {
		view: PublicView;
		/** Solo íconos (celular apaisado). */
		compact?: boolean;
	}

	let { view, compact = false }: Props = $props();

	const firing = $derived(alerts.list.filter((a) => a.state === 'firing').length);
	const tabs = $derived([
		{
			href: '/nodos',
			label: m.nav_nodes(),
			icon: List,
			current: view === 'nodes' || view === 'home' || view === 'node'
		},
		{ href: '/chat', label: m.nav_chat(), icon: MessageCircle, current: view === 'chat' },
		{ href: '/alertas', label: m.nav_alerts(), icon: Bell, current: view === 'alerts' },
		{ href: '/estadisticas', label: m.nav_stats(), icon: ChartColumn, current: view === 'stats' }
	]);
</script>

<nav class="ptabs" class:compact aria-label={m.nav_sections()}>
	{#each tabs as tab (tab.href)}
		<a
			href={tab.href}
			class="ptab"
			class:current={tab.current}
			aria-current={tab.current ? 'page' : undefined}
		>
			<tab.icon size={18} aria-hidden="true" />
			<span class:sr-only={compact}>{tab.label}</span>
			{#if tab.href === '/alertas' && firing > 0}<span class="count">{firing}</span>{/if}
		</a>
	{/each}
</nav>

<style>
	.ptabs {
		display: grid;
		grid-template-columns: repeat(4, 1fr);
		gap: 2px;
		padding: 3px;
		border-radius: var(--r-sm);
		background: var(--fill-1);
	}

	.ptab {
		display: flex;
		flex-direction: column;
		align-items: center;
		justify-content: center;
		gap: 2px;
		min-height: 48px;
		border-radius: 8px;
		color: var(--text-2);
		text-decoration: none;
		font-size: 0.75rem;
		font-weight: 600;
		position: relative;
	}

	.compact .ptab {
		min-height: 40px;
	}

	.ptab:hover {
		color: var(--text-1);
	}

	.ptab.current {
		background: var(--surface-3);
		color: var(--text-1);
	}

	.count {
		position: absolute;
		top: 4px;
		right: 8px;
		min-width: 18px;
		height: 18px;
		padding: 0 5px;
		border-radius: 999px;
		background: var(--danger);
		color: var(--on-danger);
		font-size: 0.75rem;
		line-height: 18px;
		text-align: center;
	}
</style>
