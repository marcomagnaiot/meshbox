<!--
  Gráfico de series de tiempo con uPlot (cargado bajo demanda, fuera del paquete inicial).
  Una sola serie y un solo eje: línea de 2 px, relleno al 10 %, banda mínimo-máximo cuando
  hay agregados, cruz que sigue al puntero con el valor y la hora, y tabla equivalente.
-->
<script lang="ts">
	import type uPlotType from 'uplot';
	import { onDestroy } from 'svelte';
	import { m } from '$lib/paraglide/messages';
	import { fmt } from '$lib/i18n/fmt.svelte';
	import { prefs } from '$lib/stores/prefs.svelte';
	import { site } from '$lib/stores/site.svelte';
	import { resolveToken, withAlpha } from '$lib/utils/css-color';

	interface Props {
		ts: number[];
		values: (number | null)[];
		min?: (number | null)[] | null;
		max?: (number | null)[] | null;
		/** Nombre de la serie (título del gráfico). */
		label: string;
		format?: (v: number) => string;
		height?: number;
		yRange?: [number, number] | null;
		/** Muestra la tabla equivalente debajo (desplegable). */
		table?: boolean;
		/** Valores enteros (conteos): marcas del eje sin decimales. */
		integer?: boolean;
		/** Arrastrar sobre el gráfico acerca ese tramo; doble clic vuelve a todo. */
		zoom?: boolean;
	}

	let {
		ts,
		values,
		min = null,
		max = null,
		label,
		format = (v) => fmt.number(v, 1),
		height = 200,
		yRange = null,
		table = true,
		integer = false,
		zoom = false
	}: Props = $props();

	let container: HTMLDivElement | undefined = $state();
	let width = $state(0);
	let chart: uPlotType | null = null;
	let lib: typeof uPlotType | null = null;
	let tip = $state<{ x: number; y: number; value: string; time: string } | null>(null);
	let failed = $state(false);

	const hasData = $derived(values.some((v) => v !== null && Number.isFinite(v)));
	const span = $derived(ts.length > 1 ? ts[ts.length - 1] - ts[0] : 0);

	const summary = $derived.by(() => {
		const valid = values.filter((v): v is number => v !== null && Number.isFinite(v));
		if (!valid.length) return m.chart_no_data();
		return m.chart_summary({
			label,
			last: format(valid[valid.length - 1]),
			min: format(Math.min(...valid)),
			max: format(Math.max(...valid))
		});
	});

	/** Fecha o hora según el tramo que se ve (con zoom, el acercado). */
	function timeLabel(t: number, visible = span): string {
		return visible > 2 * 86400 ? fmt.date(t) : fmt.time(t);
	}

	let tableOpen = $state(false);

	function build(): void {
		if (!lib || !container || width <= 0) return;
		chart?.destroy();
		chart = null;
		const line = resolveToken('--chart-line');
		const grid = resolveToken('--chart-grid');
		const axis = resolveToken('--text-2');
		const band = min && max && min.length === ts.length && max.length === ts.length;
		const data: uPlotType.AlignedData = band
			? [ts, values as number[], max as number[], min as number[]]
			: [ts, values as number[]];
		const series: uPlotType.Series[] = [
			{},
			{
				label,
				stroke: line,
				width: 2,
				fill: withAlpha(line, 0.1),
				spanGaps: true,
				points: { show: ts.length < 40, size: 6, stroke: line, fill: line }
			}
		];
		if (band) {
			series.push(
				{ label: 'max', stroke: 'transparent', width: 0, points: { show: false } },
				{ label: 'min', stroke: 'transparent', width: 0, points: { show: false } }
			);
		}
		const axisFont = '12px "Inter Variable", system-ui, sans-serif';
		const opts: uPlotType.Options = {
			width,
			height,
			legend: { show: false },
			padding: [8, 8, 0, 0],
			cursor: {
				x: true,
				y: false,
				drag: zoom ? { x: true, y: false, setScale: true } : { x: false, y: false },
				points: { size: 9, fill: line, stroke: resolveToken('--surface-1'), width: 2 }
			},
			select: { show: zoom, left: 0, top: 0, width: 0, height: 0 },
			scales: {
				x: { time: true },
				y: yRange ? { range: () => yRange } : { range: (_u, lo, hi) => padRange(lo, hi) }
			},
			axes: [
				{
					stroke: axis,
					font: axisFont,
					grid: { show: false },
					ticks: { stroke: grid, width: 1, size: 4 },
					values: (u, splits) =>
						splits.map((v) => timeLabel(v, (u.scales.x.max ?? 0) - (u.scales.x.min ?? 0))),
					space: 64
				},
				{
					stroke: axis,
					font: axisFont,
					size: 52,
					grid: { stroke: grid, width: 1 },
					ticks: { show: false },
					...(integer
						? { incrs: [1, 2, 5, 10, 20, 25, 50, 100, 200, 250, 500, 1000, 2000, 5000, 10000] }
						: {}),
					values: (_u, splits) => splits.map((v) => format(v))
				}
			],
			series,
			bands: band ? [{ series: [2, 3], fill: withAlpha(line, 0.16) }] : [],
			hooks: {
				setCursor: [
					(u) => {
						const idx = u.cursor.idx;
						if (
							idx === null ||
							idx === undefined ||
							u.cursor.left === undefined ||
							u.cursor.left < 0
						) {
							tip = null;
							return;
						}
						const v = (u.data[1] as (number | null)[])[idx];
						tip =
							v === null || v === undefined
								? null
								: {
										x: u.cursor.left + u.over.offsetLeft,
										y: u.valToPos(v, 'y') + u.over.offsetTop,
										value: format(v),
										time: fmt.dateTime(u.data[0][idx])
									};
					}
				]
			}
		};
		try {
			chart = new lib(opts, data, container);
		} catch {
			failed = true;
		}
	}

	function padRange(lo: number | null, hi: number | null): [number, number] {
		if (lo === null || hi === null) return [0, 1];
		if (lo === hi) return [Math.max(0, lo - 1), hi + 1];
		const pad = (hi - lo) * 0.1;
		const out: [number, number] = [lo - pad, hi + pad];
		if (lo >= 0) out[0] = Math.max(0, out[0]);
		return integer ? [Math.floor(out[0]), Math.ceil(out[1])] : out;
	}

	$effect(() => {
		// Dependencias: datos, tamaño, tema y acento (los colores del lienzo se resuelven al crear).
		void [ts, values, min, max, width, height, integer, prefs.resolvedTheme, site.data.accent];
		if (!hasData) {
			chart?.destroy();
			chart = null;
			return;
		}
		if (!lib) {
			Promise.all([import('uplot'), import('uplot/dist/uPlot.min.css')])
				.then(([mod]) => {
					lib = mod.default;
					build();
				})
				.catch(() => (failed = true));
			return;
		}
		build();
	});

	onDestroy(() => chart?.destroy());
</script>

<figure class="ts" aria-label={label}>
	<div class="plot" bind:clientWidth={width} style="min-height: {height}px">
		{#if hasData && !failed}
			<div bind:this={container} class="canvas" role="img" aria-label={summary}></div>
			{#if tip}
				<div class="tip surface-raised" style="left: {tip.x}px; top: {tip.y}px" aria-hidden="true">
					<strong class="tabular">{tip.value}</strong>
					<span>{tip.time}</span>
				</div>
			{/if}
		{:else}
			<p class="empty">{failed ? m.error_generic() : m.chart_no_data()}</p>
		{/if}
	</div>
	{#if zoom && hasData}
		<p class="hint">{m.chart_zoom_hint()}</p>
	{/if}
	{#if table && hasData}
		<details class="table" bind:open={tableOpen}>
			<summary>{m.chart_table()}</summary>
			<div class="scroll">
				<table>
					<thead>
						<tr><th scope="col">{m.node_position_time()}</th><th scope="col">{label}</th></tr>
					</thead>
					<tbody>
						{#each tableOpen ? ts : [] as t, i (i)}
							{#if values[i] !== null}
								<tr
									><td>{fmt.dateTime(t)}</td><td class="tabular">{format(values[i] as number)}</td
									></tr
								>
							{/if}
						{/each}
					</tbody>
				</table>
			</div>
		</details>
	{/if}
</figure>

<style>
	.hint {
		margin: 4px 0 0;
		font-size: 0.75rem;
		color: var(--text-2);
	}

	.ts {
		margin: 0;
	}

	.plot {
		position: relative;
		width: 100%;
	}

	.canvas :global(.u-wrap) {
		cursor: crosshair;
	}

	.tip {
		position: absolute;
		transform: translate(-50%, calc(-100% - 12px));
		padding: 6px 10px;
		border-radius: 8px;
		pointer-events: none;
		display: flex;
		flex-direction: column;
		align-items: center;
		font-size: 0.75rem;
		white-space: nowrap;
		color: var(--text-2);
	}

	.tip strong {
		font-size: 0.875rem;
		color: var(--text-1);
	}

	.empty {
		display: grid;
		place-items: center;
		min-height: inherit;
		margin: 0;
		color: var(--text-2);
		font-size: 0.875rem;
	}

	.table {
		margin-top: 8px;
		font-size: 0.8125rem;
	}

	.table summary {
		cursor: pointer;
		color: var(--text-2);
		min-height: 32px;
		display: flex;
		align-items: center;
	}

	.scroll {
		max-height: 220px;
		overflow: auto;
	}

	table {
		width: 100%;
		border-collapse: collapse;
	}

	th,
	td {
		text-align: left;
		padding: 4px 6px;
		border-bottom: 1px solid var(--line);
	}

	th {
		color: var(--text-2);
		font-weight: 600;
		position: sticky;
		top: 0;
		background: var(--surface-2);
	}
</style>
