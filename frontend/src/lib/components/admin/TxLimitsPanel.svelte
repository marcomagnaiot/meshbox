<!--
  Límites de envío propios de meshbox (ADR 0018), en `[tx]` de config.toml: pausa entre envíos y
  tope por hora para mensajes, traceroute y pedidos de posición (todas las placas) y para la
  administración remota de nodos (por placa). 0 = sin límite; valen desde el próximo envío.
-->
<script lang="ts">
	import { onMount, tick } from 'svelte';
	import * as adminApi from '$lib/admin/api';
	import type { TxLimitValues } from '$lib/admin/api';
	import { problemFields, problemText } from '$lib/admin/errors';
	import { m } from '$lib/paraglide/messages';
	import { toasts } from '$lib/stores/ui.svelte';
	import Button from '$lib/components/ui/Button.svelte';
	import Skeleton from '$lib/components/ui/Skeleton.svelte';
	import NumberField from './NumberField.svelte';
	import Panel from './Panel.svelte';
	import ProblemNote from './ProblemNote.svelte';

	interface Props {
		/** Espera de transmisión vigente (segundos), al cargar y al guardar. */
		onwait?: (seconds: number) => void;
	}

	let { onwait }: Props = $props();

	const MAX = 3600;
	type Values = Record<keyof TxLimitValues, number | null>;
	const GROUPS: { legend: () => string; fields: [keyof TxLimitValues, () => string][] }[] = [
		{
			legend: m.adm_tx_limits_tx,
			fields: [
				['min_interval_s', m.adm_tx_limits_gap],
				['max_per_hour', m.adm_tx_limits_hour]
			]
		},
		{
			legend: m.adm_tx_limits_remote,
			fields: [
				['remote_min_interval_s', m.adm_tx_limits_remote_gap],
				['remote_max_per_hour', m.adm_tx_limits_remote_hour]
			]
		}
	];

	let values = $state<Values | null>(null);
	let loadError = $state<unknown>(null);
	let saving = $state(false);
	let errors = $state<Record<string, string>>({});
	let formError = $state<string | null>(null);
	let el: HTMLElement | undefined = $state();

	function pick(d: TxLimitValues): Values {
		return {
			min_interval_s: d.min_interval_s,
			max_per_hour: d.max_per_hour,
			remote_min_interval_s: d.remote_min_interval_s,
			remote_max_per_hour: d.remote_max_per_hour
		};
	}

	async function load(): Promise<void> {
		try {
			const d = await adminApi.tx.limits();
			values = pick(d);
			loadError = null;
			onwait?.(d.wait_s);
			// Llegada desde «Cambiar el límite»: el panel aparece después de cargar.
			if (location.hash === '#limites') {
				await tick();
				el?.scrollIntoView({ block: 'start' });
			}
		} catch (err) {
			loadError = err;
		}
	}

	onMount(() => {
		void load();
	});

	async function save(e: SubmitEvent): Promise<void> {
		e.preventDefault();
		if (!values) return;
		const errs: Record<string, string> = {};
		for (const [key, v] of Object.entries(values)) {
			if (v === null || !Number.isInteger(v)) errs[key] = m.adm_field_invalid();
			else if (v < 0) errs[key] = m.adm_min_value({ min: 0 });
			else if (v > MAX) errs[key] = m.adm_max_value({ max: MAX });
		}
		errors = errs;
		if (Object.keys(errs).length) {
			formError = m.adm_fix_fields();
			return;
		}
		saving = true;
		formError = null;
		try {
			const d = await adminApi.tx.setLimits(values as TxLimitValues);
			values = pick(d);
			onwait?.(d.wait_s);
			toasts.show(m.adm_tx_limits_saved(), { kind: 'success' });
		} catch (err) {
			errors = problemFields(err);
			formError = problemText(err);
		} finally {
			saving = false;
		}
	}
</script>

<div id="limites" class="anchor" bind:this={el}>
	<Panel title={m.adm_tx_limits_title()} description={m.adm_tx_limits_desc()}>
		{#if loadError && !values}
			<ProblemNote error={loadError} onretry={load} />
		{:else if !values}
			<Skeleton lines={3} label={m.loading()} />
		{:else}
			<form class="adm-stack" onsubmit={save} novalidate>
				{#each GROUPS as g (g.fields[0][0])}
					<fieldset class="adm-fieldset">
						<legend>{g.legend()}</legend>
						<div class="adm-grid">
							{#each g.fields as [key, label] (key)}
								<NumberField
									label={label()}
									bind:value={values[key]}
									min={0}
									max={MAX}
									step={1}
									unit={key.endsWith('_s') ? 's' : undefined}
									error={errors[key]}
								/>
							{/each}
						</div>
					</fieldset>
				{/each}
				{#if formError}<p class="adm-note danger" role="alert">{formError}</p>{/if}
				<div class="adm-row end">
					<Button type="submit" size="sm" variant="primary" loading={saving}>{m.adm_save()}</Button>
				</div>
			</form>
		{/if}
	</Panel>
</div>

<style>
	.anchor {
		scroll-margin-top: 72px;
	}
</style>
