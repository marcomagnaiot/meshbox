<!--
  Ficha de nodo (17.2): encabezado con estado en texto, indicadores, ambiente, gráficos mini
  de 24 h, historial de posiciones, vecinos, traceroutes y datos técnicos.
-->
<script lang="ts" module>
	let openedBefore = false;
</script>

<script lang="ts">
	import ArrowLeft from '@lucide/svelte/icons/arrow-left';
	import Crosshair from '@lucide/svelte/icons/crosshair';
	import Route from '@lucide/svelte/icons/route';
	import Share2 from '@lucide/svelte/icons/share-2';
	import SearchX from '@lucide/svelte/icons/search-x';
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import { ApiError } from '$lib/api/client';
	import { publicApi } from '$lib/api/public';
	import type {
		Link,
		NodeDetail as NodeDetailT,
		TelemetrySeries,
		Traceroute
	} from '$lib/api/types';
	import { fmt } from '$lib/i18n/fmt.svelte';
	import { i18n } from '$lib/i18n/locale.svelte';
	import { sourceLabel } from '$lib/i18n/labels';
	import { m } from '$lib/paraglide/messages';
	import { clock } from '$lib/stores/clock.svelte';
	import { live } from '$lib/stores/live.svelte';
	import { site } from '$lib/stores/site.svelte';
	import { selection, toasts } from '$lib/stores/ui.svelte';
	import { nodeHref } from '$lib/utils/ids';
	import { displayName, hasPosition, shortName } from '$lib/utils/nodes';
	import { classify } from '$lib/utils/status';
	import BatteryRing from '$lib/components/ui/BatteryRing.svelte';
	import EmptyState from '$lib/components/ui/EmptyState.svelte';
	import IconButton from '$lib/components/ui/IconButton.svelte';
	import NodeTag from '$lib/components/ui/NodeTag.svelte';
	import RoleBadge from '$lib/components/ui/RoleBadge.svelte';
	import SignalBars from '$lib/components/ui/SignalBars.svelte';
	import Skeleton from '$lib/components/ui/Skeleton.svelte';
	import Sparkline from '$lib/components/ui/Sparkline.svelte';
	import StatusBadge from '$lib/components/ui/StatusBadge.svelte';
	import { metricDef } from './metrics';
	import NodeHistory from './NodeHistory.svelte';
	import TelemetryDialog from './TelemetryDialog.svelte';

	interface Props {
		nodeId: string;
		/** Destino del botón volver/cerrar. */
		closeHref?: string;
	}

	let { nodeId, closeHref = '/' }: Props = $props();

	const uid = $props.id();
	let detail = $state.raw<NodeDetailT | null>(null);
	let notFound = $state(false);
	let device = $state.raw<TelemetrySeries | null>(null);
	let env = $state.raw<TelemetrySeries | null>(null);
	let neighbors = $state.raw<Link[] | null>(null);
	let routes = $state.raw<Traceroute[] | null>(null);
	let chartOpen = $state(false);
	let chartKind = $state<'device' | 'environment'>('device');
	let chartMetric = $state('battery_level');
	let heading: HTMLHeadingElement | undefined = $state();

	// Lo que llega en vivo manda; la ficha completa agrega los datos técnicos.
	const liveNode = $derived(live.node(nodeId));
	const node = $derived(liveNode ? { ...(detail ?? {}), ...liveNode } : detail);
	const status = $derived(
		node ? classify(node.last_heard, clock.now, site.data.thresholds) : 'inactive'
	);
	const name = $derived(node ? displayName(node) : nodeId);

	$effect(() => {
		const id = nodeId;
		const ctrl = new AbortController();
		detail = null;
		notFound = false;
		device = env = null;
		neighbors = routes = null;
		const to = clock.exact();
		publicApi
			.node(id, ctrl.signal)
			.then((d) => (detail = d))
			.catch((err) => {
				if (err instanceof ApiError && err.status === 404) notFound = true;
			});
		publicApi
			.telemetry(id, 'device', to - 86400, to, ctrl.signal)
			.then((d) => (device = d))
			.catch(() => {});
		publicApi
			.telemetry(id, 'environment', to - 86400, to, ctrl.signal)
			.then((d) => (env = d))
			.catch(() => {});
		publicApi
			.nodeLinks(id, ctrl.signal)
			.then((l) => (neighbors = dedupeNeighbors(id, l)))
			.catch(() => (neighbors = []));
		publicApi
			.traceroutes(id, 5, ctrl.signal)
			.then((t) => (routes = t))
			.catch(() => (routes = []));
		return () => ctrl.abort();
	});

	// Telemetría en vivo: se agrega el punto a los gráficos mini.
	onMount(() =>
		live.core.on('telemetry', (ev) => {
			if (ev.id !== nodeId) return;
			const target = ev.kind === 'device' ? device : ev.kind === 'environment' ? env : null;
			if (!target) return;
			const series: Record<string, (number | null)[]> = {};
			for (const [k, list] of Object.entries(target.series))
				series[k] = [...list, ev.values[k] ?? null];
			const next = { ...target, ts: [...target.ts, ev.ts], series };
			if (ev.kind === 'device') device = next;
			else env = next;
		})
	);

	// Foco en el título al abrir una ficha desde la interfaz (lectores de pantalla y teclado);
	// no en la carga inicial de la página (enlace directo), para no marcar un foco que nadie pidió.
	$effect(() => {
		void nodeId;
		if (!openedBefore) {
			openedBefore = true;
			return;
		}
		heading?.focus({ preventScroll: true });
	});

	function dedupeNeighbors(id: string, list: Link[]): Link[] {
		const best = new Map<string, Link>();
		for (const l of list) {
			const other = l.a === id ? l.b : l.a;
			const prev = best.get(other);
			if (!prev || l.ts > prev.ts) best.set(other, l);
		}
		return [...best.values()].sort((a, b) => (b.snr ?? -99) - (a.snr ?? -99));
	}

	async function share() {
		const url = new URL(nodeHref(nodeId), location.origin).href;
		try {
			if (navigator.share) {
				await navigator.share({ title: name, url });
				return;
			}
			await navigator.clipboard.writeText(url);
			toasts.show(m.node_link_copied(), { kind: 'success' });
		} catch {
			// cancelado por el usuario
		}
	}

	function openChart(kind: 'device' | 'environment', metric: string) {
		chartKind = kind;
		chartMetric = metric;
		chartOpen = true;
	}

	function otherName(id: string): string {
		const n = live.node(id);
		return n ? displayName(n) : id;
	}

	const sparkDefs = $derived.by(() => {
		const out: { kind: 'device' | 'environment'; key: string; series: TelemetrySeries }[] = [];
		if (device?.series.battery_level?.some((v) => v !== null))
			out.push({ kind: 'device', key: 'battery_level', series: device });
		else if (device?.series.voltage?.some((v) => v !== null))
			out.push({ kind: 'device', key: 'voltage', series: device });
		if (env?.series.temperature?.some((v) => v !== null))
			out.push({ kind: 'environment', key: 'temperature', series: env });
		return out;
	});
</script>

<article class="detail" aria-labelledby="{uid}-name">
	<header class="head">
		<IconButton icon={ArrowLeft} label={m.node_close()} size="sm" onclick={() => goto(closeHref)} />
		<div class="ident">
			<h1 id="{uid}-name" bind:this={heading} tabindex="-1">{name}</h1>
			{#if node}
				<div class="badges">
					<NodeTag id={node.id} label={shortName(node)} size="md" />
					<RoleBadge role={node.role} infra={node.is_infra} />
				</div>
			{/if}
		</div>
		<div class="tools">
			{#if node && hasPosition(node)}
				<IconButton
					icon={Crosshair}
					label={m.node_center()}
					size="sm"
					onclick={() => selection.focus()}
				/>
			{/if}
			<IconButton icon={Share2} label={m.node_share()} size="sm" onclick={share} />
		</div>
	</header>

	{#if notFound && !liveNode}
		<EmptyState icon={SearchX} title={m.node_not_found()} description={m.node_not_found_detail()} />
	{:else if !node}
		<div class="pad"><Skeleton lines={5} label={m.node_loading()} /></div>
	{:else}
		<div class="status">
			<StatusBadge
				{status}
				infra={node.is_infra}
				fixed={node.is_fixed}
				detail={m.status_heard({ ago: fmt.relative(node.last_heard, 'long') })}
			/>
			{#if !hasPosition(node)}<span class="muted">{m.node_no_position()}</span>{/if}
		</div>

		<section class="grid" aria-label={m.node_signal()}>
			<div class="card battery">
				<BatteryRing battery={node.battery} powered={node.powered} size={60} />
				<div class="kv">
					<span class="k">{m.node_battery()}</span>
					<span class="v">
						{node.battery !== null && node.battery > 100
							? m.node_powered()
							: node.battery !== null
								? `${node.battery} %`
								: '—'}
					</span>
					<span class="k">{m.node_voltage()}</span>
					<span class="v tabular"
						>{node.voltage !== null ? `${fmt.number(node.voltage, 2)} V` : '—'}</span
					>
				</div>
			</div>
			{#if node.is_gateway}
				<div class="card">
					<span class="k">{m.node_signal()}</span>
					<span class="v">{m.node_gateway()}</span>
					<span class="k">{m.node_gateway_hint()}</span>
				</div>
			{:else}
				<div class="card">
					<span class="k">{m.node_signal()}</span>
					<div class="sig">
						<SignalBars snr={node.snr} rssi={node.rssi} size={22} />
						<span class="v tabular">{fmt.db(node.snr)}</span>
					</div>
					<span class="k">{m.node_rssi()}</span>
					<span class="v tabular">{fmt.dbm(node.rssi)}</span>
				</div>
			{/if}
			<div class="card">
				<span class="k">{m.node_hops()}</span>
				<span class="v tabular"
					>{node.hops === null ? '—' : node.hops === 0 ? m.node_hops_direct() : node.hops}</span
				>
				<span class="k">{m.node_uptime()}</span>
				<span class="v tabular">{fmt.duration(node.uptime_s)}</span>
			</div>
			<div class="card">
				<span class="k">{m.node_channel_util()}</span>
				<span class="v tabular">{fmt.percent(node.channel_utilization)}</span>
				<span class="k">{m.node_air_util()}</span>
				<span class="v tabular">{fmt.percent(node.air_util_tx)}</span>
			</div>
		</section>

		{#if node.env}
			<section class="block" aria-labelledby="{uid}-env">
				<h2 id="{uid}-env" class="section-title">{m.node_environment()}</h2>
				<div class="env">
					{#if node.env.temperature !== null && node.env.temperature !== undefined}
						<div class="card">
							<span class="k">{m.node_temperature()}</span><span class="v tabular"
								>{fmt.unit(node.env.temperature, 'celsius', 1)}</span
							>
						</div>
					{/if}
					{#if node.env.humidity !== null && node.env.humidity !== undefined}
						<div class="card">
							<span class="k">{m.node_humidity()}</span><span class="v tabular"
								>{fmt.number(node.env.humidity, 0)} %</span
							>
						</div>
					{/if}
					{#if node.env.pressure !== null && node.env.pressure !== undefined}
						<div class="card">
							<span class="k">{m.node_pressure()}</span><span class="v tabular"
								>{fmt.number(node.env.pressure, 0)} hPa</span
							>
						</div>
					{/if}
					{#if node.env.lux !== null && node.env.lux !== undefined}
						<div class="card">
							<span class="k">{m.node_lux()}</span><span class="v tabular"
								>{fmt.number(node.env.lux, 0)} lx</span
							>
						</div>
					{/if}
				</div>
			</section>
		{/if}

		{#if sparkDefs.length}
			<section class="block" aria-labelledby="{uid}-tel">
				<h2 id="{uid}-tel" class="section-title">{m.node_last_24h()}</h2>
				<div class="sparks">
					{#each sparkDefs as s (s.key)}
						{@const def = metricDef(s.kind, s.key)}
						{@const vals = s.series.series[s.key] ?? []}
						{@const last = [...vals].reverse().find((v) => v !== null) ?? null}
						<button
							type="button"
							class="card spark"
							onclick={() => openChart(s.kind, s.key)}
							aria-label="{def.label()}: {m.node_open_chart()}"
						>
							<span class="k">{def.label()}</span>
							<span class="v">{last !== null ? def.format(last, i18n.locale) : '—'}</span>
							<Sparkline
								ts={s.series.ts}
								values={vals}
								min={def.range?.[0]}
								max={def.range?.[1]}
								width={140}
								height={36}
								label={m.chart_summary({
									label: def.label(),
									last: last !== null ? def.format(last, i18n.locale) : '—',
									min: def.format(
										Math.min(...vals.filter((v): v is number => v !== null)),
										i18n.locale
									),
									max: def.format(
										Math.max(...vals.filter((v): v is number => v !== null)),
										i18n.locale
									)
								})}
							/>
						</button>
					{/each}
				</div>
			</section>
		{/if}

		<NodeHistory {nodeId} />

		<section class="block" aria-labelledby="{uid}-nb">
			<h2 id="{uid}-nb" class="section-title">{m.node_neighbors()}</h2>
			{#if neighbors === null}
				<Skeleton lines={2} />
			{:else if neighbors.length === 0}
				<p class="muted">{m.node_neighbors_empty()}</p>
			{:else}
				<ul class="list">
					{#each neighbors as l (`${l.a}-${l.b}-${l.source}`)}
						{@const other = l.a === nodeId ? l.b : l.a}
						<li>
							<a href={nodeHref(other)} class="row-link">
								<SignalBars snr={l.snr} size={16} />
								<span class="grow">{otherName(other)}</span>
								<span class="muted small"
									>{fmt.db(l.snr)} · {sourceLabel(l.source)} · {fmt.relative(l.ts)}</span
								>
							</a>
						</li>
					{/each}
				</ul>
			{/if}
		</section>

		{#if routes && routes.length}
			<section class="block" aria-labelledby="{uid}-tr">
				<h2 id="{uid}-tr" class="section-title">{m.node_traceroutes()}</h2>
				<ul class="list">
					{#each routes as tr (`${tr.ts}-${tr.from}-${tr.to}`)}
						{@const shown = selection.traceroute === tr}
						<li class="route">
							<Route size={16} aria-hidden="true" />
							<span class="grow">
								{m.node_traceroute_path({
									from: otherName(tr.from),
									to: otherName(tr.to),
									hops: tr.route.length
								})}
								<span class="muted small">· {fmt.relative(tr.ts)}</span>
							</span>
							<button
								type="button"
								class="mini"
								aria-pressed={shown}
								onclick={() => (selection.traceroute = shown ? null : tr)}
							>
								{shown ? m.node_traceroute_hide() : m.node_traceroute_show()}
							</button>
						</li>
					{/each}
				</ul>
			</section>
		{/if}

		<section class="block" aria-labelledby="{uid}-tech">
			<h2 id="{uid}-tech" class="section-title">{m.node_technical()}</h2>
			<dl class="tech">
				<div>
					<dt>{m.node_id()}</dt>
					<dd class="mono">{node.id}</dd>
				</div>
				<div>
					<dt>{m.node_hardware()}</dt>
					<dd>{node.hw_model ?? m.node_unknown()}</dd>
				</div>
				<div>
					<dt>{m.node_role()}</dt>
					<dd>{node.role}</dd>
				</div>
				{#if detail?.firmware_version}<div>
						<dt>{m.node_firmware()}</dt>
						<dd>{detail.firmware_version}</dd>
					</div>{/if}
				{#if detail?.region}<div>
						<dt>{m.node_region()}</dt>
						<dd>{detail.region}</dd>
					</div>{/if}
				{#if detail?.modem_preset}<div>
						<dt>{m.node_preset()}</dt>
						<dd>{detail.modem_preset}</dd>
					</div>{/if}
				<div>
					<dt>{m.node_first_seen()}</dt>
					<dd>{fmt.dateTime(node.first_seen)}</dd>
				</div>
				{#if node.precision_m}
					<div>
						<dt>{m.node_precision()}</dt>
						<dd>± {fmt.distance(node.precision_m)}</dd>
					</div>
				{/if}
				{#if detail?.position_ts}
					<div>
						<dt>{m.node_position_time()}</dt>
						<dd>{fmt.relative(detail.position_ts, 'long')}</dd>
					</div>
				{/if}
			</dl>
		</section>
	{/if}
</article>

{#if node}
	<TelemetryDialog
		bind:open={chartOpen}
		{nodeId}
		{name}
		hasEnv={Boolean(node.env) || Boolean(env?.ts.length)}
		initialKind={chartKind}
		initialMetric={chartMetric}
	/>
{/if}

<style>
	.detail {
		display: flex;
		flex-direction: column;
		gap: 16px;
		padding: 4px 16px 24px;
	}

	.head {
		display: flex;
		align-items: flex-start;
		gap: 6px;
		margin-left: -8px;
	}

	.ident {
		flex: 1;
		min-width: 0;
		padding-top: 4px;
	}

	h1 {
		margin: 0;
		font-size: 1.25rem;
		line-height: 1.3;
		font-weight: 700;
		overflow-wrap: anywhere;
	}

	h1:focus {
		outline: none;
	}

	h1:focus-visible {
		outline: 2px solid var(--focus);
	}

	.badges {
		display: flex;
		align-items: center;
		gap: 6px;
		margin-top: 4px;
	}

	.tools {
		display: flex;
	}

	.status {
		display: flex;
		align-items: center;
		flex-wrap: wrap;
		gap: 8px;
	}

	.grid {
		display: grid;
		grid-template-columns: repeat(auto-fill, minmax(150px, 1fr));
		gap: 8px;
	}

	.card {
		display: flex;
		flex-direction: column;
		gap: 2px;
		padding: 10px 12px;
		min-width: 0;
	}

	.card.battery {
		flex-direction: row;
		align-items: center;
		gap: 12px;
		grid-column: span 1;
	}

	.kv {
		display: flex;
		flex-direction: column;
	}

	.k {
		font-size: 0.75rem;
		color: var(--text-2);
	}

	.v {
		font-size: 0.9375rem;
		font-weight: 650;
	}

	.sig {
		display: flex;
		align-items: center;
		gap: 6px;
	}

	.block {
		display: flex;
		flex-direction: column;
		gap: 8px;
	}

	.detail :global(.section-title) {
		margin: 0;
		font-size: 0.875rem;
		font-weight: 700;
		color: var(--text-1);
	}

	.env {
		display: grid;
		grid-template-columns: repeat(auto-fill, minmax(110px, 1fr));
		gap: 8px;
	}

	.sparks {
		display: grid;
		grid-template-columns: repeat(auto-fill, minmax(170px, 1fr));
		gap: 8px;
	}

	.spark {
		border: 0;
		color: inherit;
		font: inherit;
		text-align: left;
		cursor: pointer;
	}

	.spark:hover {
		background: var(--fill-2);
	}

	.list {
		list-style: none;
		margin: 0;
		padding: 0;
		display: flex;
		flex-direction: column;
		gap: 2px;
	}

	.row-link,
	.route {
		display: flex;
		align-items: center;
		gap: 10px;
		min-height: 44px;
		padding: 4px 8px;
		border-radius: var(--r-sm);
		color: var(--text-1);
		text-decoration: none;
	}

	.row-link:hover {
		background: var(--fill-1);
	}

	.grow {
		flex: 1;
		min-width: 0;
		font-size: 0.875rem;
	}

	.small {
		font-size: 0.75rem;
	}

	.muted {
		color: var(--text-2);
		margin: 0;
		font-size: 0.875rem;
	}

	.mini {
		flex: none;
		min-height: 36px;
		padding: 0 10px;
		border: 1px solid var(--line);
		border-radius: 8px;
		background: var(--fill-1);
		color: var(--text-1);
		font: inherit;
		font-size: 0.75rem;
		font-weight: 600;
	}

	.mini[aria-pressed='true'] {
		background: color-mix(in oklch, var(--route) 30%, transparent);
	}

	@media (pointer: coarse) {
		.mini {
			min-height: 44px;
		}
	}

	.tech {
		display: grid;
		grid-template-columns: repeat(auto-fill, minmax(160px, 1fr));
		gap: 8px 12px;
		margin: 0;
	}

	.tech div {
		display: flex;
		flex-direction: column;
	}

	dt {
		font-size: 0.75rem;
		color: var(--text-2);
	}

	dd {
		margin: 0;
		font-size: 0.875rem;
		overflow-wrap: anywhere;
	}

	.mono {
		font-family: ui-monospace, 'Cascadia Code', Menlo, monospace;
	}

	.pad {
		padding: 8px 0;
	}
</style>
