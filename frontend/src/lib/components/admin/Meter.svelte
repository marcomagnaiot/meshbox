<!--
  Medidor (CPU, RAM, disco, temperatura): barra con role="meter" y valor en texto. Pasado el
  umbral cambia el color y además aparece la palabra "alto" (el color nunca va solo).
-->
<script lang="ts">
	import { m } from '$lib/paraglide/messages';

	interface Props {
		label: string;
		/** Valor mostrado ("43 %", "61 °C"). */
		text: string;
		/** Proporción de la barra, 0 a 100 (null = sin dato). */
		percent: number | null;
		detail?: string;
		warnAt?: number;
		dangerAt?: number;
		/** Lo malo es quedarse abajo (batería): los umbrales se cuentan desde cero. */
		low?: boolean;
	}

	let { label, text, percent, detail, warnAt = 75, dangerAt = 90, low = false }: Props = $props();
	const past = (p: number, at: number) => (low ? p <= at : p >= at);
	const level = $derived(
		percent === null
			? 'none'
			: past(percent, dangerAt)
				? 'danger'
				: past(percent, warnAt)
					? 'warn'
					: 'ok'
	);
	const flag = $derived(
		level === 'danger'
			? low
				? m.adm_meter_very_low()
				: m.adm_meter_high()
			: low
				? m.adm_meter_low()
				: m.adm_meter_elevated()
	);
	const pct = $derived(percent === null ? 0 : Math.max(0, Math.min(100, percent)));
</script>

<div class="meter {level}">
	<div class="top">
		<span class="label">{label}</span>
		<span class="value"
			>{text}{#if level === 'danger' || level === 'warn'}<span class="flag">{flag}</span>{/if}</span
		>
	</div>
	{#if percent === null}
		<!-- Sin dato (sin sensor de temperatura): el texto ya lo dice, la barra es decorativa. -->
		<div class="track" aria-hidden="true"></div>
	{:else}
		<div
			class="track"
			role="meter"
			aria-label={label}
			aria-valuemin={0}
			aria-valuemax={100}
			aria-valuenow={Math.round(pct)}
			aria-valuetext={text}
		>
			<span class="fill" style="width: {pct}%"></span>
		</div>
	{/if}
	{#if detail}<p class="detail">{detail}</p>{/if}
</div>

<style>
	.meter {
		display: flex;
		flex-direction: column;
		gap: 6px;
		min-width: 0;
	}

	.top {
		display: flex;
		justify-content: space-between;
		align-items: baseline;
		gap: 8px;
	}

	.label {
		font-size: 0.8125rem;
		color: var(--text-2);
	}

	.value {
		font-size: 1.125rem;
		font-weight: 650;
		font-variant-numeric: tabular-nums;
	}

	.flag {
		margin-left: 6px;
		padding: 1px 6px;
		border-radius: 999px;
		font-size: 0.6875rem;
		font-weight: 700;
		text-transform: uppercase;
		vertical-align: middle;
		background: var(--warning-soft);
	}

	.danger .flag {
		background: var(--danger-soft);
	}

	.track {
		height: 8px;
		border-radius: 999px;
		background: var(--fill-2);
		overflow: hidden;
	}

	.fill {
		display: block;
		height: 100%;
		border-radius: inherit;
		background: var(--accent);
	}

	.warn .fill {
		background: var(--warning);
	}

	.danger .fill {
		background: var(--danger);
	}

	.detail {
		margin: 0;
		font-size: 0.75rem;
		color: var(--text-2);
	}
</style>
