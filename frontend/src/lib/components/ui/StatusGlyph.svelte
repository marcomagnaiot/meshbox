<!--
  Glifo de estado: misma codificación que los íconos del mapa (16.1.10, el color nunca es la
  única señal). Relleno según frescura (lleno, tres cuartos, medio, vacío), anillo grueso para
  infraestructura y anillo fino para nodos fijos.
-->
<script lang="ts">
	import type { NodeStatus } from '$lib/api/types';

	interface Props {
		status: NodeStatus;
		infra?: boolean;
		fixed?: boolean;
		size?: number;
		/** Texto accesible; sin él el glifo es decorativo (el texto va al lado). */
		label?: string;
	}

	let { status, infra = false, fixed = false, size = 16, label }: Props = $props();

	const FRACTION: Record<NodeStatus, number> = { active: 1, recent: 0.75, late: 0.5, inactive: 0 };
	const r = 5;
	const c = 10;

	const fraction = $derived(FRACTION[status]);
	const pie = $derived.by(() => {
		if (fraction <= 0 || fraction >= 1) return '';
		const angle = fraction * 2 * Math.PI;
		const x = c + r * Math.sin(angle);
		const y = c - r * Math.cos(angle);
		return `M${c} ${c}L${c} ${c - r}A${r} ${r} 0 ${fraction > 0.5 ? 1 : 0} 1 ${x.toFixed(3)} ${y.toFixed(3)}Z`;
	});
</script>

<svg
	class="glyph"
	width={size}
	height={size}
	viewBox="0 0 20 20"
	role={label ? 'img' : undefined}
	aria-label={label}
	aria-hidden={label ? undefined : 'true'}
	style="--c: var(--st-{status})"
>
	{#if fixed}
		<circle
			cx={c}
			cy={c}
			r={infra ? 9.2 : 8.4}
			fill="none"
			stroke="var(--text-1)"
			stroke-width="1"
		/>
	{/if}
	{#if infra}
		<circle cx={c} cy={c} r="7.6" fill="none" stroke="var(--st-infra)" stroke-width="2" />
	{/if}
	<circle cx={c} cy={c} r={r + 0.9} fill="var(--map-outline)" />
	{#if fraction >= 1}
		<circle cx={c} cy={c} {r} fill="var(--c)" />
	{:else if pie}
		<path d={pie} fill="var(--c)" />
	{/if}
	<circle cx={c} cy={c} r={r - 0.6} fill="none" stroke="var(--c)" stroke-width="1.3" />
</svg>

<style>
	.glyph {
		flex: none;
		display: inline-block;
		vertical-align: middle;
	}
</style>
