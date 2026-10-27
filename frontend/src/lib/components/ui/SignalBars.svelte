<!-- Barras de señal de la última recepción: la cantidad de barras, no solo el color, da el nivel. -->
<script lang="ts">
	import { m } from '$lib/paraglide/messages';
	import { fmt } from '$lib/i18n/fmt.svelte';
	import { signalBars } from '$lib/utils/status';

	interface Props {
		snr: number | null | undefined;
		rssi?: number | null;
		size?: number;
	}

	let { snr, rssi = null, size = 18 }: Props = $props();

	const bars = $derived(signalBars(snr, rssi));
	const label = $derived(
		`${m.node_signal()}: ${bars}/4 · ${m.node_snr()} ${fmt.db(snr)} · ${m.node_rssi()} ${fmt.dbm(rssi)}`
	);
</script>

<svg
	class="bars"
	width={size}
	height={size}
	viewBox="0 0 16 16"
	role="img"
	aria-label={label}
	data-bars={bars}
>
	{#each [0, 1, 2, 3] as i (i)}
		<rect
			x={1 + i * 3.8}
			y={12 - i * 3}
			width="2.6"
			height={3 + i * 3}
			rx="0.8"
			fill={i < bars ? 'currentColor' : 'var(--fill-3)'}
		/>
	{/each}
</svg>

<style>
	.bars {
		flex: none;
		color: var(--text-1);
	}

	.bars[data-bars='1'] {
		color: var(--danger);
	}

	.bars[data-bars='2'] {
		color: var(--warning);
	}

	.bars[data-bars='3'],
	.bars[data-bars='4'] {
		color: var(--success);
	}
</style>
