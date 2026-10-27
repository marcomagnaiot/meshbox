<!--
  Tendencia de carga a 2 y 7 días (placas con panel solar): si el mínimo del amanecer baja día
  tras día, el panel o el cargador no reponen lo que consume la placa. Cuenta los días que
  llegó a carga completa, la caída nocturna y, si hay déficit, cuántos días faltan para el
  voltaje en el que la placa se reinicia.
-->
<script lang="ts">
	import { radioApi, type BatteryTrend } from '$lib/admin/radio';
	import { ApiError } from '$lib/api/client';
	import { fmt } from '$lib/i18n/fmt.svelte';
	import { m } from '$lib/paraglide/messages';
	import Segmented from '$lib/components/ui/Segmented.svelte';
	import KeyValue from '$lib/components/admin/KeyValue.svelte';

	interface Props {
		nodeId: string;
	}

	let { nodeId }: Props = $props();

	type Days = '2' | '7';
	let days = $state<Days>('2');
	let data = $state.raw<BatteryTrend | null>(null);
	let failed = $state(false);

	$effect(() => {
		const n = Number(days);
		const ctrl = new AbortController();
		failed = false;
		radioApi
			.battery(nodeId, n, ctrl.signal)
			.then((d) => (data = d))
			.catch((err) => {
				if (err instanceof DOMException) return;
				failed = !(err instanceof ApiError && err.status === 404);
				data = null;
			});
		return () => ctrl.abort();
	});

	const mv = (v: number | null | undefined, sign = true) =>
		v === null || v === undefined
			? '—'
			: `${sign && v > 0 ? '+' : ''}${fmt.number(v * 1000, 0)} mV`;
	const volts = (v: number | null | undefined) =>
		v === null || v === undefined ? '—' : `${fmt.number(v, 3)} V`;

	const t = $derived(data?.trend ?? null);
	const days_ = $derived((data?.per_day ?? []).filter((d) => d.samples > 0));
	const drains = $derived(
		days_
			.filter((d) => d.in_trend)
			.map((d) => d.night_drain_mv_h)
			.filter((v): v is number => v !== null)
	);
	const drain = $derived(drains.length ? drains.reduce((a, b) => a + b, 0) / drains.length : null);
	const verdict = $derived.by(() => {
		if (!t) return null;
		if (t.verdict === 'recupera')
			return { tone: 'ok', label: m.adm_bat_recovers(), text: m.adm_bat_recovers_text() };
		if (t.verdict === 'estable')
			return { tone: 'warn', label: m.adm_bat_stable(), text: m.adm_bat_stable_text() };
		if (t.verdict === 'deficit')
			return {
				tone: 'danger',
				label: m.adm_bat_deficit(),
				text: m.adm_bat_deficit_text({
					mv: fmt.number(Math.abs((t.dawn_slope_v_day ?? t.evening_delta_v ?? 0) * 1000), 0),
					volts: fmt.number(t.cutoff_v, 1),
					days: fmt.number(t.days_to_cutoff ?? 0, 1)
				})
			};
		return { tone: '', label: m.adm_bat_no_data(), text: m.adm_bat_no_data_text() };
	});
</script>

<section class="trend" aria-label={m.adm_bat_trend()}>
	<div class="head">
		<h3>{m.adm_bat_trend()}</h3>
		<Segmented
			label={m.adm_bat_window()}
			size="sm"
			bind:value={days}
			options={[
				{ value: '2', label: m.adm_bat_2d() },
				{ value: '7', label: m.adm_bat_7d() }
			]}
		/>
	</div>
	{#if failed}
		<p class="adm-muted">{m.error_generic()}</p>
	{:else if data && t && verdict}
		<p class="verdict">
			<span class="adm-badge {verdict.tone}">{verdict.label}</span>
			<span>{verdict.text}</span>
		</p>
		<KeyValue
			columns={4}
			items={[
				{
					label: m.adm_bat_dawn_slope(),
					value:
						t.dawn_slope_v_day === null ? '—' : `${mv(t.dawn_slope_v_day)} / ${m.adm_bat_day()}`
				},
				{ label: m.adm_bat_evening_delta(), value: mv(t.evening_delta_v) },
				{
					label: m.adm_bat_full_days(),
					value: m.adm_bat_full_days_value({ full: t.full_days, total: t.complete_days })
				},
				{
					label: m.adm_bat_night_drain(),
					value: drain === null ? '—' : `${fmt.number(drain, 1)} mV/h`
				}
			]}
		/>
		{#if days_.length}
			<div class="scroll">
				<table>
					<thead>
						<tr>
							<th scope="col">{m.adm_bat_col_day()}</th>
							<th scope="col">{m.adm_bat_col_dawn()}</th>
							<th scope="col">{m.adm_bat_col_charge()}</th>
							<th scope="col">{m.adm_bat_col_evening()}</th>
							<th scope="col">{m.adm_bat_col_drain()}</th>
						</tr>
					</thead>
					<tbody>
						{#each days_ as d (d.date)}
							<tr class:old={!d.in_trend}>
								<td
									>{fmt.day(Date.parse(`${d.date}T12:00:00`) / 1000)}{d.complete
										? ''
										: ` (${m.adm_bat_today()})`}</td
								>
								<td class="tabular"
									>{volts(d.dawn_v)}{d.dawn_pct !== null && d.dawn_pct <= 100
										? ` · ${d.dawn_pct} %`
										: ''}</td
								>
								<td class="tabular">{d.full ? `${fmt.number(d.charge_h, 1)} h` : m.adm_no()}</td>
								<td class="tabular">{volts(d.evening_v)}</td>
								<td class="tabular"
									>{d.night_drain_mv_h === null
										? '—'
										: `${fmt.number(d.night_drain_mv_h, 1)} mV/h`}</td
								>
							</tr>
						{/each}
					</tbody>
				</table>
			</div>
		{/if}
		{#if t.since}
			<p class="adm-muted note">{m.adm_bat_since({ date: fmt.dateTime(t.since) })}</p>
		{/if}
		<p class="adm-muted note">{m.adm_bat_note()}</p>
	{:else}
		<p class="adm-muted">{m.chart_loading()}</p>
	{/if}
</section>

<style>
	.trend {
		display: flex;
		flex-direction: column;
		gap: 10px;
		padding-top: 12px;
		border-top: 1px solid var(--line);
	}

	.head {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 8px;
		flex-wrap: wrap;
	}

	h3 {
		margin: 0;
		font-size: 0.9375rem;
	}

	.verdict {
		margin: 0;
		display: flex;
		align-items: baseline;
		gap: 8px;
		flex-wrap: wrap;
	}

	.scroll {
		overflow-x: auto;
	}

	table {
		width: 100%;
		border-collapse: collapse;
		font-size: 0.8125rem;
	}

	th,
	td {
		padding: 6px 8px;
		text-align: left;
		border-bottom: 1px solid var(--line);
		white-space: nowrap;
	}

	th {
		color: var(--text-2);
		font-weight: 600;
	}

	tr.old td {
		color: var(--text-3);
	}

	.note {
		margin: 0;
		font-size: 0.75rem;
	}
</style>
