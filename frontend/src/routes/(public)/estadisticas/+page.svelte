<!--
  Estadísticas (17.1): un solo selector de rango arriba que gobierna todo; tarjetas de
  resumen; series por hora (una por gráfico, un solo eje); paquetes por tipo y saltos como
  barras-tabla; nodos que más retransmiten con sus candidatos.
-->
<script lang="ts">
	import { publicApi } from '$lib/api/public';
	import type { StatsBreakdown, StatsRange, StatsSummary, TimeSeries } from '$lib/api/types';
	import { fmt } from '$lib/i18n/fmt.svelte';
	import { portLabel } from '$lib/i18n/labels';
	import { m } from '$lib/paraglide/messages';
	import { live } from '$lib/stores/live.svelte';
	import { site } from '$lib/stores/site.svelte';
	import { nodeHref } from '$lib/utils/ids';
	import Segmented from '$lib/components/ui/Segmented.svelte';
	import TimeSeriesChart from '$lib/components/ui/TimeSeriesChart.svelte';
	import EmptyState from '$lib/components/ui/EmptyState.svelte';
	import StatusGlyph from '$lib/components/ui/StatusGlyph.svelte';
	import BarList from '$lib/components/stats/BarList.svelte';
	import StatTile from '$lib/components/stats/StatTile.svelte';
	import ChartColumn from '@lucide/svelte/icons/chart-column';

	let range = $state<StatsRange>('24h');
	let summary = $state.raw<StatsSummary | null>(null);
	let series = $state.raw<Record<string, TimeSeries | null>>({});
	let breakdown = $state.raw<StatsBreakdown | null>(null);
	let loading = $state(false);
	let failed = $state(false);

	const current = $derived(live.summary ?? summary);
	const ranges = [
		{ value: '24h' as StatsRange, label: '24 h' },
		{ value: '7d' as StatsRange, label: '7 d' },
		{ value: '30d' as StatsRange, label: '30 d' }
	];

	$effect(() => {
		void publicApi
			.summary()
			.then((s) => (summary = s))
			.catch(() => {});
	});

	$effect(() => {
		const r = range;
		const ctrl = new AbortController();
		loading = true;
		failed = false;
		const metrics = ['active_nodes', 'packets', 'avg_channel_util', 'new_nodes'] as const;
		Promise.all([
			...metrics.map((metric) => publicApi.timeseries(metric, r, ctrl.signal).catch(() => null)),
			publicApi.breakdown(r, ctrl.signal)
		])
			.then((res) => {
				const out: Record<string, TimeSeries | null> = {};
				metrics.forEach((metric, i) => (out[metric] = res[i] as TimeSeries | null));
				series = out;
				breakdown = res[metrics.length] as StatsBreakdown;
			})
			.catch((err) => {
				if (!(err instanceof DOMException)) failed = true;
			})
			.finally(() => (loading = false));
		return () => ctrl.abort();
	});

	function numeric(ts: TimeSeries | null | undefined): (number | null)[] {
		return (ts?.values ?? []).map((v) => (typeof v === 'number' ? v : null));
	}

	const portRows = $derived(
		Object.entries(breakdown?.by_portnum ?? {}).map(([k, v]) => ({
			key: k,
			label: portLabel(k),
			value: v
		}))
	);
	const hopRows = $derived(
		Object.entries(breakdown?.by_hops ?? {})
			.map(([k, v]) => ({ key: k, hops: Number(k), value: v }))
			.sort((a, b) => a.hops - b.hops)
			.map((r) => ({
				key: r.key,
				label: r.hops === 0 ? m.stats_hops_direct() : m.stats_hops_n({ hops: r.hops }),
				value: r.value
			}))
	);
	const charts = $derived([
		{
			key: 'active_nodes',
			label: m.stats_active_nodes(),
			format: (v: number) => fmt.number(v, 0),
			integer: true
		},
		{
			key: 'packets',
			label: m.stats_packets(),
			format: (v: number) => fmt.number(v, 0),
			integer: true
		},
		{
			key: 'avg_channel_util',
			label: m.stats_channel_util(),
			format: (v: number) => fmt.percent(v, 1),
			integer: false
		},
		{
			key: 'new_nodes',
			label: m.stats_new_nodes(),
			format: (v: number) => fmt.number(v, 0),
			integer: true
		}
	]);
</script>

<svelte:head><title>{m.stats_title()} · {site.data.name}</title></svelte:head>

<div class="page-scroll page-pad stats">
	<h1 class="page-title">{m.stats_title()}</h1>
	<div class="filters">
		<Segmented label={m.stats_range()} options={ranges} bind:value={range} />
	</div>

	{#if current}
		<div class="tiles">
			<StatTile label={m.summary_nodes()} value={fmt.number(current.nodes.total ?? 0, 0)}>
				{#snippet lead()}<StatusGlyph status="active" size={14} />{/snippet}
			</StatTile>
			<StatTile label={m.status_active()} value={fmt.number(current.nodes.active ?? 0, 0)} />
			<StatTile label={m.summary_packets_hour()} value={fmt.number(current.packets_last_hour, 0)} />
			<StatTile
				label={m.summary_channel_util()}
				value={fmt.percent(current.channel_utilization_avg)}
			/>
			<StatTile label={m.summary_new_nodes()} value={fmt.number(current.new_nodes_24h, 0)} />
		</div>
	{/if}

	{#if failed}
		<EmptyState icon={ChartColumn} title={m.error_network()} />
	{:else}
		<div class="charts" class:busy={loading}>
			{#each charts as c (c.key)}
				{@const ts = series[c.key]}
				<section class="card chart" aria-labelledby="chart-{c.key}">
					<h2 id="chart-{c.key}" class="chart-title">{c.label}</h2>
					<TimeSeriesChart
						ts={ts?.ts ?? []}
						values={numeric(ts)}
						label={c.label}
						format={c.format}
						integer={c.integer}
						height={170}
					/>
				</section>
			{/each}
		</div>

		<div class="tables" class:busy={loading}>
			<section class="card block" aria-labelledby="t-port">
				<h2 id="t-port" class="chart-title">{m.stats_by_portnum()}</h2>
				{#if portRows.length}
					<BarList
						rows={portRows}
						caption={m.stats_by_portnum()}
						labelHeader={m.stats_type()}
						valueHeader={m.stats_packets_count()}
						shareHeader={m.stats_share()}
						otherLabel={m.port_other()}
					/>
				{:else}
					<p class="muted">{m.stats_empty()}</p>
				{/if}
			</section>
			<section class="card block" aria-labelledby="t-hops">
				<h2 id="t-hops" class="chart-title">{m.stats_by_hops()}</h2>
				{#if hopRows.length}
					<BarList
						rows={hopRows}
						keepOrder
						caption={m.stats_by_hops()}
						labelHeader={m.node_hops()}
						valueHeader={m.stats_packets_count()}
						shareHeader={m.stats_share()}
					/>
				{:else}
					<p class="muted">{m.stats_empty()}</p>
				{/if}
			</section>
			<section class="card block relays" aria-labelledby="t-relays">
				<h2 id="t-relays" class="chart-title">{m.stats_relays()}</h2>
				<p class="muted small">{m.stats_relays_hint()}</p>
				{#if breakdown?.relays.length}
					<table>
						<thead>
							<tr
								><th scope="col">{m.stats_relay_byte()}</th><th scope="col"
									>{m.stats_packets_count()}</th
								><th scope="col">{m.stats_node()}</th></tr
							>
						</thead>
						<tbody>
							{#each breakdown.relays as r (r.relay)}
								<tr>
									<td class="mono">{r.relay}</td>
									<td class="tabular">{fmt.number(r.count, 0)}</td>
									<td>
										{#if r.candidates.length}
											{#each r.candidates as c, i (c.id)}
												{#if i > 0},
												{/if}<a href={nodeHref(c.id)}>{c.name ?? c.id}</a>
											{/each}
										{:else}
											<span class="muted">{m.stats_relay_unknown()}</span>
										{/if}
									</td>
								</tr>
							{/each}
						</tbody>
					</table>
				{:else}
					<p class="muted">{m.stats_empty()}</p>
				{/if}
			</section>
		</div>
	{/if}
</div>

<style>
	.filters {
		margin-bottom: 12px;
	}

	.tiles {
		display: grid;
		grid-template-columns: repeat(auto-fill, minmax(140px, 1fr));
		gap: 8px;
		margin-bottom: 12px;
	}

	.charts,
	.tables {
		display: grid;
		grid-template-columns: repeat(auto-fill, minmax(min(100%, 320px), 1fr));
		gap: 10px;
		transition: opacity var(--dur-1) var(--ease);
	}

	.tables {
		margin-top: 10px;
	}

	.busy {
		opacity: 0.55;
	}

	.chart,
	.block {
		padding: 12px 14px;
		min-width: 0;
	}

	.chart-title {
		margin: 0 0 8px;
		font-size: 0.875rem;
		font-weight: 700;
	}

	.muted {
		margin: 0;
		color: var(--text-2);
		font-size: 0.875rem;
	}

	.small {
		font-size: 0.75rem;
		margin-bottom: 8px;
	}

	table {
		width: 100%;
		border-collapse: collapse;
		font-size: 0.8125rem;
	}

	th {
		text-align: left;
		font-size: 0.75rem;
		color: var(--text-2);
		font-weight: 600;
		padding: 4px 6px 4px 0;
	}

	td {
		padding: 6px 6px 6px 0;
		border-top: 1px solid var(--line);
		vertical-align: top;
	}

	.mono {
		font-family: ui-monospace, 'Cascadia Code', Menlo, monospace;
	}
</style>
