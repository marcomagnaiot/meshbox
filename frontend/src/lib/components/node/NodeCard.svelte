<!-- Tarjeta de nodo (fila de la lista): estado con forma y texto, batería y señal. -->
<script lang="ts">
	import Plug from '@lucide/svelte/icons/plug';
	import BatteryLow from '@lucide/svelte/icons/battery-low';
	import Battery from '@lucide/svelte/icons/battery';
	import type { Node } from '$lib/api/types';
	import { fmt } from '$lib/i18n/fmt.svelte';
	import { roleLabel, statusLabel } from '$lib/i18n/labels';
	import { m } from '$lib/paraglide/messages';
	import { clock } from '$lib/stores/clock.svelte';
	import { site } from '$lib/stores/site.svelte';
	import { nodeHref } from '$lib/utils/ids';
	import { displayName, shortName } from '$lib/utils/nodes';
	import { batteryLevel, classify } from '$lib/utils/status';
	import NodeTag from '$lib/components/ui/NodeTag.svelte';
	import SignalBars from '$lib/components/ui/SignalBars.svelte';
	import StatusGlyph from '$lib/components/ui/StatusGlyph.svelte';

	interface Props {
		node: Node;
		selected?: boolean;
	}

	let { node, selected = false }: Props = $props();

	const status = $derived(classify(node.last_heard, clock.now, site.data.thresholds));
	const level = $derived(batteryLevel(node.battery, node.powered));
</script>

<a
	href={nodeHref(node.id)}
	class="card"
	class:selected
	aria-current={selected ? 'true' : undefined}
	data-node={node.id}
>
	<StatusGlyph {status} infra={node.is_infra} fixed={node.is_fixed} size={22} />
	<span class="main">
		<span class="line1">
			<span class="name">{displayName(node)}</span>
			<NodeTag id={node.id} label={shortName(node)} />
		</span>
		<span class="line2">
			{statusLabel(status)} · {fmt.relative(node.last_heard)}{#if node.is_gateway}&nbsp;· {m.node_gateway()}{:else if node.is_infra}&nbsp;·
				{roleLabel(node.role)}{/if}
		</span>
	</span>
	<span class="metrics">
		{#if level !== 'unknown'}
			<span class="bat" data-level={level} title={m.node_battery()}>
				{#if level === 'powered'}
					<Plug size={14} aria-hidden="true" /><span class="sr-only">{m.node_powered()}</span>
				{:else}
					{#if level === 'critical' || level === 'low'}<BatteryLow
							size={14}
							aria-hidden="true"
						/>{:else}<Battery size={14} aria-hidden="true" />{/if}
					<span class="tabular">{node.battery}%</span>
				{/if}
			</span>
		{/if}
		{#if node.snr !== null || node.rssi !== null}
			<SignalBars snr={node.snr} rssi={node.rssi} size={16} />
		{/if}
	</span>
</a>

<style>
	.card {
		container-type: inline-size;
		display: flex;
		align-items: center;
		gap: 12px;
		height: 100%;
		padding: 0 12px;
		border-radius: var(--r-sm);
		color: var(--text-1);
		text-decoration: none;
	}

	.card:hover {
		background: var(--fill-1);
	}

	.card.selected {
		background: var(--accent-soft);
	}

	.card:focus-visible {
		outline-offset: -2px;
	}

	.main {
		flex: 1;
		min-width: 0;
		display: flex;
		flex-direction: column;
		gap: 2px;
	}

	.line1 {
		display: flex;
		align-items: center;
		gap: 8px;
		min-width: 0;
	}

	.name {
		font-weight: 600;
		font-size: 0.875rem;
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}

	.line2 {
		font-size: 0.75rem;
		color: var(--text-2);
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}

	.metrics {
		flex: none;
		display: flex;
		align-items: center;
		gap: 8px;
		font-size: 0.75rem;
		color: var(--text-2);
	}

	.bat {
		display: inline-flex;
		align-items: center;
		gap: 3px;
	}

	.bat[data-level='critical'] {
		color: var(--danger);
	}

	.bat[data-level='low'] {
		color: var(--warning);
	}

	@container (max-width: 260px) {
		.metrics {
			display: none;
		}
	}
</style>
