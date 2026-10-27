<!--
  Gráfico mini (sparkline) de una sola serie: línea de 2 px en gris de bajo énfasis y el punto
  actual en el acento (contrato de tarjeta de estadística). El resumen accesible dice último,
  mínimo y máximo; el gráfico completo y su tabla están a un toque.
-->
<script lang="ts">
	interface Props {
		ts: number[];
		values: (number | null)[];
		width?: number;
		height?: number;
		/** Rango fijo del eje (por ejemplo 0-100 para batería). */
		min?: number;
		max?: number;
		label: string;
	}

	let { ts, values, width = 120, height = 36, min, max, label }: Props = $props();

	const pad = 4;

	const points = $derived.by(() => {
		const pts: [number, number][] = [];
		const valid = values.filter((v): v is number => v !== null && Number.isFinite(v));
		if (valid.length === 0 || ts.length === 0) return { pts, lo: 0, hi: 0 };
		const lo = min ?? Math.min(...valid);
		const hi = max ?? Math.max(...valid);
		const span = hi - lo || 1;
		const t0 = ts[0];
		const tSpan = ts[ts.length - 1] - t0 || 1;
		for (let i = 0; i < ts.length; i++) {
			const v = values[i];
			if (v === null || v === undefined || !Number.isFinite(v)) continue;
			const x = pad + ((ts[i] - t0) / tSpan) * (width - pad * 2);
			const y = height - pad - ((v - lo) / span) * (height - pad * 2);
			pts.push([x, y]);
		}
		return { pts, lo, hi };
	});

	const path = $derived(
		points.pts.map(([x, y], i) => `${i ? 'L' : 'M'}${x.toFixed(1)} ${y.toFixed(1)}`).join('')
	);
	const last = $derived(points.pts.at(-1));
</script>

<svg {width} {height} viewBox="0 0 {width} {height}" role="img" aria-label={label} class="spark">
	{#if points.pts.length > 1}
		<path
			d={path}
			fill="none"
			stroke="var(--chart-muted)"
			stroke-width="2"
			stroke-linejoin="round"
			stroke-linecap="round"
		/>
	{/if}
	{#if last}
		<circle
			cx={last[0]}
			cy={last[1]}
			r="4"
			fill="var(--chart-line)"
			stroke="var(--surface-1)"
			stroke-width="2"
		/>
	{/if}
</svg>

<style>
	.spark {
		display: block;
		overflow: visible;
	}
</style>
