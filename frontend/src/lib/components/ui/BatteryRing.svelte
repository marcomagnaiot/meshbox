<!-- Anillo de batería (17.2): porcentaje o "alimentado" si el nodo informa 101. -->
<script lang="ts">
	import Plug from '@lucide/svelte/icons/plug';
	import { m } from '$lib/paraglide/messages';
	import { batteryLevel } from '$lib/utils/status';

	interface Props {
		battery: number | null | undefined;
		powered?: boolean;
		size?: number;
		/** Sin texto al lado: el valor va dentro del anillo. */
		compact?: boolean;
	}

	let { battery, powered = false, size = 56, compact = false }: Props = $props();

	const level = $derived(batteryLevel(battery, powered));
	const pct = $derived(
		level === 'powered'
			? 100
			: battery === null || battery === undefined
				? 0
				: Math.max(0, Math.min(100, battery))
	);
	const stroke = 5;
	const radius = $derived(size / 2 - stroke / 2 - 1);
	const circumference = $derived(2 * Math.PI * radius);
	const color = $derived(
		level === 'powered'
			? 'var(--st-infra)'
			: level === 'critical'
				? 'var(--danger)'
				: level === 'low'
					? 'var(--warning)'
					: level === 'unknown'
						? 'var(--text-3)'
						: 'var(--success)'
	);
	const text = $derived(
		level === 'powered' ? m.node_powered() : level === 'unknown' ? '—' : `${Math.round(pct)} %`
	);
	const aria = $derived(`${m.node_battery()}: ${text}`);
</script>

<span class="battery" role="img" aria-label={aria} style="--size: {size}px">
	<svg width={size} height={size} viewBox="0 0 {size} {size}" aria-hidden="true">
		<circle
			cx={size / 2}
			cy={size / 2}
			r={radius}
			fill="none"
			stroke="var(--fill-2)"
			stroke-width={stroke}
		/>
		{#if level !== 'unknown'}
			<circle
				cx={size / 2}
				cy={size / 2}
				r={radius}
				fill="none"
				stroke={color}
				stroke-width={stroke}
				stroke-linecap="round"
				stroke-dasharray="{(circumference * pct) / 100} {circumference}"
				transform="rotate(-90 {size / 2} {size / 2})"
			/>
		{/if}
	</svg>
	<span class="center" aria-hidden="true">
		{#if level === 'powered'}
			<Plug size={Math.round(size * 0.36)} />
		{:else if compact || size >= 48}
			<span class="pct tabular">{level === 'unknown' ? '—' : Math.round(pct)}</span>
		{/if}
	</span>
	{#if !compact}
		<span class="sr-only">{text}</span>
	{/if}
</span>

<style>
	.battery {
		position: relative;
		display: inline-grid;
		place-items: center;
		width: var(--size);
		height: var(--size);
		flex: none;
	}

	.battery svg {
		position: absolute;
		inset: 0;
	}

	.center {
		position: relative;
		display: grid;
		place-items: center;
		color: var(--text-1);
	}

	.pct {
		font-size: 0.875rem;
		font-weight: 700;
	}
</style>
