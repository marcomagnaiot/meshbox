<script lang="ts">
	import CircleCheck from '@lucide/svelte/icons/circle-check';
	import Info from '@lucide/svelte/icons/info';
	import Siren from '@lucide/svelte/icons/siren';
	import TriangleAlert from '@lucide/svelte/icons/triangle-alert';
	import type { Alert } from '$lib/api/types';
	import { fmt } from '$lib/i18n/fmt.svelte';
	import { severityLabel } from '$lib/i18n/labels';
	import { m } from '$lib/paraglide/messages';
	import { live } from '$lib/stores/live.svelte';
	import { isSos } from '$lib/stores/alerts.svelte';
	import { nodeHref } from '$lib/utils/ids';
	import { displayName } from '$lib/utils/nodes';

	interface Props {
		alert: Alert;
	}

	let { alert }: Props = $props();

	const node = $derived(alert.node ? live.node(alert.node) : undefined);
	const resolved = $derived(alert.state === 'resolved');
</script>

<article class="alert card" data-severity={alert.severity} class:resolved>
	<span class="icon" aria-hidden="true">
		{#if resolved}<CircleCheck size={20} />{:else if isSos(alert)}<Siren
				size={20}
			/>{:else if alert.severity === 'info'}<Info size={20} />{:else}<TriangleAlert
				size={20}
			/>{/if}
	</span>
	<div class="body">
		<p class="meta">
			<span class="state">{resolved ? m.alerts_state_resolved() : m.alerts_state_firing()}</span>
			· {severityLabel(alert.severity)} ·
			<time datetime={new Date(alert.ts * 1000).toISOString()}>{fmt.dateTime(alert.ts)}</time>
		</p>
		<h2 class="title">{alert.title}</h2>
		{#if alert.body && alert.body !== alert.title}<p class="text">{alert.body}</p>{/if}
		{#if alert.node}
			<a class="node" href={nodeHref(alert.node)}
				>{node ? displayName(node) : alert.node} · {m.alerts_view_map()}</a
			>
		{/if}
	</div>
</article>

<style>
	.alert {
		display: flex;
		gap: 12px;
		padding: 12px 14px;
		border-left: 4px solid var(--warning);
	}

	.alert[data-severity='critical'] {
		border-left-color: var(--danger);
	}

	.alert[data-severity='info'] {
		border-left-color: var(--accent);
	}

	.alert.resolved {
		border-left-color: var(--line-strong);
	}

	.icon {
		flex: none;
		color: var(--text-1);
		padding-top: 2px;
	}

	.body {
		flex: 1;
		min-width: 0;
	}

	.meta {
		margin: 0;
		font-size: 0.75rem;
		color: var(--text-2);
	}

	.state {
		font-weight: 700;
		color: var(--text-1);
	}

	.title {
		margin: 2px 0;
		font-size: 0.9375rem;
		font-weight: 700;
	}

	.text {
		margin: 0 0 4px;
		font-size: 0.875rem;
		overflow-wrap: anywhere;
	}

	.node {
		display: inline-flex;
		align-items: center;
		min-height: 36px;
		font-size: 0.8125rem;
		font-weight: 600;
	}
</style>
