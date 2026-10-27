<!-- Alertas públicas (17.1): lista, alerta activa destacada arriba y botón de notificaciones. -->
<script lang="ts">
	import BellOff from '@lucide/svelte/icons/bell-off';
	import { m } from '$lib/paraglide/messages';
	import { alerts } from '$lib/stores/alerts.svelte';
	import { site } from '$lib/stores/site.svelte';
	import AlertItem from '$lib/components/alerts/AlertItem.svelte';
	import PushToggle from '$lib/components/alerts/PushToggle.svelte';
	import Button from '$lib/components/ui/Button.svelte';
	import EmptyState from '$lib/components/ui/EmptyState.svelte';
	import Skeleton from '$lib/components/ui/Skeleton.svelte';

	$effect(() => {
		void alerts.load();
	});
</script>

<svelte:head><title>{m.alerts_title()} · {site.data.name}</title></svelte:head>

<div class="page-scroll page-pad">
	<h1 class="page-title">{m.alerts_title()}</h1>
	<PushToggle />
	<div class="list">
		{#if alerts.loading && !alerts.loaded}
			<Skeleton lines={4} label={m.alerts_loading()} />
		{:else if alerts.list.length === 0}
			<EmptyState icon={BellOff} title={alerts.error ? m.error_network() : m.alerts_empty()} />
		{:else}
			<ul>
				{#each alerts.list as alert (alert.id)}
					<li><AlertItem {alert} /></li>
				{/each}
			</ul>
			{#if alerts.next}
				<Button size="sm" variant="ghost" onclick={() => alerts.loadMore()}
					>{m.alerts_load_more()}</Button
				>
			{/if}
		{/if}
	</div>
</div>

<style>
	.list {
		margin-top: 16px;
	}

	ul {
		list-style: none;
		margin: 0 0 12px;
		padding: 0;
		display: flex;
		flex-direction: column;
		gap: 8px;
	}
</style>
