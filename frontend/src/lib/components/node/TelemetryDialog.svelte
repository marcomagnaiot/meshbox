<!-- Gráfico completo de telemetría con rango de 1 h a 30 d (17.2). -->
<script lang="ts">
	import type { TelemetryKind, TelemetrySeries } from '$lib/api/types';
	import { publicApi } from '$lib/api/public';
	import { i18n } from '$lib/i18n/locale.svelte';
	import { m } from '$lib/paraglide/messages';
	import { clock } from '$lib/stores/clock.svelte';
	import Modal from '$lib/components/ui/Modal.svelte';
	import Segmented from '$lib/components/ui/Segmented.svelte';
	import TimeSeriesChart from '$lib/components/ui/TimeSeriesChart.svelte';
	import { metricDef, resolutionLabel, TELEMETRY_RANGES } from './metrics';

	interface Props {
		open: boolean;
		nodeId: string;
		name: string;
		hasEnv: boolean;
		initialKind?: TelemetryKind;
		initialMetric?: string;
	}

	let {
		open = $bindable(false),
		nodeId,
		name,
		hasEnv,
		initialKind = 'device',
		initialMetric = 'battery_level'
	}: Props = $props();

	// Se fijan al abrir (efecto de abajo) con el tipo y la métrica que pidió la ficha.
	let kind = $state<TelemetryKind>('device');
	let metric = $state('battery_level');
	let range = $state<string>('86400');
	let data = $state.raw<TelemetrySeries | null>(null);
	let loading = $state(false);
	let failed = $state(false);

	$effect(() => {
		if (open) {
			kind = initialKind;
			metric = initialMetric;
		}
	});

	$effect(() => {
		if (!open) return;
		const k = kind;
		const span = Number(range);
		const ctrl = new AbortController();
		loading = true;
		failed = false;
		const to = clock.exact();
		publicApi
			.telemetry(nodeId, k, to - span, to, ctrl.signal)
			.then((d) => {
				data = d;
				const keys = Object.keys(d.series);
				if (keys.length && !keys.includes(metric)) metric = keys[0];
			})
			.catch((err) => {
				if (!(err instanceof DOMException)) failed = true;
			})
			.finally(() => (loading = false));
		return () => ctrl.abort();
	});

	const kinds = $derived([
		{ value: 'device' as TelemetryKind, label: m.chart_kind_device() },
		{ value: 'environment' as TelemetryKind, label: m.chart_kind_environment(), disabled: !hasEnv },
		{ value: 'power' as TelemetryKind, label: m.chart_kind_power() }
	]);
	const metrics = $derived(
		data
			? Object.keys(data.series).map((k) => ({ value: k, label: metricDef(kind, k).label() }))
			: []
	);
	const def = $derived(metricDef(kind, metric));
	const resolution = $derived(resolutionLabel(data));
</script>

<Modal bind:open title={m.node_chart_title({ name })} size="lg">
	<div class="controls">
		<Segmented label={m.chart_kind()} options={kinds} bind:value={kind} size="sm" />
		<Segmented
			label={m.chart_range()}
			options={[...TELEMETRY_RANGES]}
			bind:value={range}
			size="sm"
		/>
	</div>
	{#if metrics.length > 1}
		<div class="controls">
			<Segmented label={m.chart_metric()} options={metrics} bind:value={metric} size="sm" />
		</div>
	{/if}
	<h3 class="title">{def.label()} <span class="res">· {resolution}</span></h3>
	<div class="chart" class:busy={loading}>
		{#if failed}
			<p class="msg">{m.error_generic()}</p>
		{:else if data}
			<TimeSeriesChart
				ts={data.ts}
				values={data.series[metric] ?? []}
				min={data.min?.[metric] ?? null}
				max={data.max?.[metric] ?? null}
				label={def.label()}
				format={(v) => def.format(v, i18n.locale)}
				yRange={def.range ?? null}
				height={260}
				zoom
			/>
		{:else}
			<p class="msg">{m.chart_loading()}</p>
		{/if}
	</div>
</Modal>

<style>
	.controls {
		display: flex;
		flex-wrap: wrap;
		gap: 8px;
		margin-bottom: 10px;
	}

	.title {
		margin: 6px 0 8px;
		font-size: 0.9375rem;
		font-weight: 650;
	}

	.res {
		font-weight: 400;
		color: var(--text-2);
		font-size: 0.8125rem;
	}

	.chart {
		min-height: 280px;
		transition: opacity var(--dur-1) var(--ease);
	}

	/* Al recargar se conserva el gráfico anterior atenuado (sin esqueleto ni salto). */
	.chart.busy {
		opacity: 0.55;
	}

	.msg {
		display: grid;
		place-items: center;
		min-height: 260px;
		margin: 0;
		color: var(--text-2);
	}
</style>
