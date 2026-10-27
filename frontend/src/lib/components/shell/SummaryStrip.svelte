<!-- Resumen de la red: conteo por estado (con forma, no solo color), último paquete y conexión. -->
<script lang="ts">
	import { fmt } from '$lib/i18n/fmt.svelte';
	import { statusLabel } from '$lib/i18n/labels';
	import { m } from '$lib/paraglide/messages';
	import { clock } from '$lib/stores/clock.svelte';
	import { live } from '$lib/stores/live.svelte';
	import { site } from '$lib/stores/site.svelte';
	import { countByStatus } from '$lib/utils/nodes';
	import { STATUSES } from '$lib/utils/status';
	import LiveIndicator from '$lib/components/ui/LiveIndicator.svelte';
	import StatusGlyph from '$lib/components/ui/StatusGlyph.svelte';

	interface Props {
		compact?: boolean;
	}

	let { compact = false }: Props = $props();

	const nodes = $derived(live.nodeList());
	const counts = $derived(countByStatus(nodes, clock.now, site.data.thresholds));
	const total = $derived(nodes.length);
	const lastPacket = $derived(live.summary?.last_packet_at ?? null);
</script>

<div class="strip" class:compact>
	<div class="top">
		<p class="title">{site.data.name}</p>
		<LiveIndicator status={live.status} {compact} onretry={() => live.restart()} />
	</div>
	<ul class="counts" aria-label={m.summary_title()}>
		{#each STATUSES as s (s)}
			<li title={statusLabel(s)}>
				<StatusGlyph status={s} size={16} />
				<span class="n tabular">{live.hasData ? counts[s] : '–'}</span>
				<span class="lbl">{statusLabel(s)}</span>
			</li>
		{/each}
		<li class="total">
			<span class="n tabular">{live.hasData ? total : '–'}</span>
			<span class="lbl">{m.summary_nodes()}</span>
		</li>
	</ul>
	{#if !compact}
		<p class="meta">
			{lastPacket
				? m.summary_last_packet({ ago: fmt.relative(lastPacket) })
				: m.summary_no_packets()}
		</p>
	{/if}
</div>

<style>
	.strip {
		display: flex;
		flex-direction: column;
		gap: 6px;
	}

	.top {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 8px;
		min-width: 0;
	}

	.title {
		margin: 0;
		font-size: 1rem;
		font-weight: 650;
		white-space: nowrap;
		overflow: hidden;
		text-overflow: ellipsis;
	}

	.counts {
		list-style: none;
		margin: 0;
		padding: 0;
		display: flex;
		flex-wrap: wrap;
		gap: 4px 12px;
		font-size: 0.8125rem;
	}

	.counts li {
		display: inline-flex;
		align-items: center;
		gap: 4px;
	}

	.n {
		font-weight: 650;
	}

	.lbl {
		color: var(--text-2);
	}

	.compact .counts .lbl {
		position: absolute;
		width: 1px;
		height: 1px;
		overflow: hidden;
		clip: rect(0 0 0 0);
		white-space: nowrap;
	}

	.compact .counts .total .lbl {
		position: static;
		width: auto;
		height: auto;
		clip: auto;
	}

	.meta {
		margin: 0;
		font-size: 0.75rem;
		color: var(--text-2);
	}
</style>
