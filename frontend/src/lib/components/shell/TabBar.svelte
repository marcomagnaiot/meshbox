<!-- Barra de pestañas glass del celular: Mapa, Nodos, Chat, Alertas, Más. -->
<script lang="ts">
	import Bell from '@lucide/svelte/icons/bell';
	import List from '@lucide/svelte/icons/list';
	import MapIcon from '@lucide/svelte/icons/map';
	import MessageCircle from '@lucide/svelte/icons/message-circle';
	import { m } from '$lib/paraglide/messages';
	import { alerts } from '$lib/stores/alerts.svelte';
	import type { PublicView } from '$lib/stores/view';
	import MoreMenu from './MoreMenu.svelte';

	interface Props {
		view: PublicView;
	}

	let { view }: Props = $props();

	const firing = $derived(alerts.list.filter((a) => a.state === 'firing').length);
	const tabs = $derived([
		{ href: '/', label: m.nav_map(), icon: MapIcon, current: view === 'home' },
		{
			href: '/nodos',
			label: m.nav_nodes(),
			icon: List,
			current: view === 'nodes' || view === 'node'
		},
		{ href: '/chat', label: m.nav_chat(), icon: MessageCircle, current: view === 'chat' },
		{ href: '/alertas', label: m.nav_alerts(), icon: Bell, current: view === 'alerts' }
	]);
</script>

<nav class="tabbar glass glass-text" aria-label={m.nav_sections()}>
	{#each tabs as tab (tab.href)}
		<a
			href={tab.href}
			class="tab"
			class:current={tab.current}
			aria-current={tab.current ? 'page' : undefined}
		>
			<span class="icon">
				<tab.icon size={22} aria-hidden="true" />
				{#if tab.href === '/alertas' && firing > 0}
					<span class="badge" aria-hidden="true">{firing}</span>
				{/if}
			</span>
			<span class="tab-label">{tab.label}</span>
			{#if tab.href === '/alertas' && firing > 0}<span class="sr-only">({m.alerts_active()})</span
				>{/if}
		</a>
	{/each}
	<MoreMenu active={view === 'stats' || view === 'about'} />
</nav>

<style>
	.tabbar {
		display: grid;
		grid-template-columns: repeat(5, 1fr);
		height: calc(var(--tabbar-h) + var(--safe-bottom));
		padding: 0 max(4px, var(--safe-right)) var(--safe-bottom) max(4px, var(--safe-left));
		border-radius: 0;
		border-left: 0;
		border-right: 0;
		border-bottom: 0;
	}

	.tabbar :global(.tab) {
		display: flex;
		flex-direction: column;
		align-items: center;
		justify-content: center;
		gap: 2px;
		min-height: 44px;
		border: 0;
		background: transparent;
		color: var(--text-2);
		text-decoration: none;
		font: inherit;
		font-size: 0.75rem;
		font-weight: 600;
		border-radius: var(--r-sm);
		margin: 6px 2px;
	}

	.tabbar :global(.tab.current),
	.tabbar :global(.tab[data-state='open']) {
		color: var(--text-1);
		background: var(--fill-1);
	}

	.tabbar :global(.tab.current .icon) {
		color: var(--accent-ink);
	}

	.icon {
		position: relative;
		display: grid;
		place-items: center;
	}

	.badge {
		position: absolute;
		top: -4px;
		right: -10px;
		min-width: 18px;
		height: 18px;
		padding: 0 5px;
		border-radius: 999px;
		background: var(--danger);
		color: var(--on-danger);
		font-size: 0.75rem;
		font-weight: 700;
		line-height: 18px;
		text-align: center;
	}
</style>
