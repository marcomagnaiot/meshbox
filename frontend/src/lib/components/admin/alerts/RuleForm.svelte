<!--
  Regla de alerta (19.1). Los parámetros de cada tipo se dibujan desde el JSON Schema que el
  backend publica en /alerts/rules/schema (los mismos modelos de pydantic que validan en el
  servidor) y se validan igual antes de enviar (18.3); los 422 marcan el campo exacto.
-->
<script lang="ts">
	import { untrack } from 'svelte';
	import * as adminApi from '$lib/admin/api';
	import { problemFields, problemText } from '$lib/admin/errors';
	import { notifyChannelLabel, ruleKindLabel } from '$lib/admin/labels';
	import { clean, validate, withDefaults } from '$lib/admin/schema';
	import type { AlertRule, JsonSchema, NotifyChannel, RuleKind } from '$lib/admin/types';
	import { METRICS } from '$lib/components/node/metrics';
	import { m } from '$lib/paraglide/messages';
	import Button from '$lib/components/ui/Button.svelte';
	import Toggle from '$lib/components/ui/Toggle.svelte';
	import CheckGroup from '../CheckGroup.svelte';
	import NumberField from '../NumberField.svelte';
	import SchemaForm from '../SchemaForm.svelte';
	import SelectField from '../SelectField.svelte';
	import TextField from '../TextField.svelte';

	interface Props {
		existing: AlertRule | null;
		/** Esquemas de parámetros por tipo (GET /alerts/rules/schema). */
		schemas: Record<RuleKind, JsonSchema>;
		nodes: { value: string; label: string }[];
		connectors: string[];
		onsaved: () => void;
		oncancel: () => void;
	}

	let { existing, schemas, nodes, connectors, onsaved, oncancel }: Props = $props();

	const SCHEMAS = untrack(() => schemas);
	const KINDS = Object.keys(SCHEMAS) as RuleKind[];
	/** Valores iniciales razonables por tipo (pydantic no exporta default_factory). */
	const STARTER: Partial<Record<RuleKind, Record<string, unknown>>> = {
		keyword: { patterns: ['\\bSOS\\b'] }
	};

	const init = untrack(() => existing);
	let name = $state(init?.name ?? '');
	let kind = $state<RuleKind>(init?.kind ?? 'keyword');
	let severity = $state<'info' | 'warning' | 'critical'>(init?.severity ?? 'warning');
	let cooldownMin = $state<number | null>(init ? Math.round(init.cooldown_s / 60) : 15);
	let channels = $state<NotifyChannel[]>(init?.channels ?? ['webpush']);
	let isPublic = $state(init?.is_public ?? false);
	let enabled = $state(init?.enabled ?? true);
	let params = $state<Record<string, unknown>>(
		withDefaults(SCHEMAS[init?.kind ?? 'keyword'], init?.params ?? STARTER[init?.kind ?? 'keyword'])
	);
	let errors = $state<Record<string, string>>({});
	let formError = $state<string | null>(null);
	let saving = $state(false);

	const schema = $derived(SCHEMAS[kind]);

	function changeKind(k: RuleKind): void {
		kind = k;
		params = withDefaults(SCHEMAS[k], STARTER[k]);
		errors = {};
	}

	const PARAM_LABELS: Record<string, () => string> = {
		patterns: m.adm_rp_patterns,
		regex: m.adm_rp_regex,
		case_sensitive: m.adm_rp_case,
		include_bell: m.adm_rp_bell,
		channels: m.adm_rp_radio_channels,
		scope: m.adm_rp_scope,
		mode: m.adm_rp_scope_mode,
		nodes: m.adm_rp_nodes,
		kind: m.adm_rp_tkind,
		metric: m.adm_rp_metric,
		op: m.adm_rp_op,
		value: m.adm_rp_value,
		duration_s: m.adm_rp_duration,
		hours: m.adm_rp_hours,
		connector: m.adm_rp_connector,
		minutes: m.adm_rp_minutes,
		cpu_pct: m.adm_rp_cpu,
		ram_pct: m.adm_rp_ram,
		temp_c: m.adm_rp_temp,
		disk_pct: m.adm_rp_disk,
		writer_queue: m.adm_rp_queue,
		rss_mb: m.adm_rp_rss
	};
	const PARAM_HINTS: Record<string, () => string> = {
		patterns: m.adm_rp_patterns_hint,
		channels: m.adm_rp_radio_channels_hint,
		include_bell: m.adm_rp_bell_hint,
		duration_s: m.adm_rp_duration_hint,
		connector: m.adm_rp_connector_hint,
		nodes: m.adm_rp_nodes_hint
	};

	function optionsFor(
		path: string,
		values: unknown[]
	): { value: string; label: string }[] | undefined {
		const key = path.split('.').pop() ?? '';
		if (key === 'mode') {
			const L: Record<string, string> = {
				nodes: m.adm_rp_mode_nodes(),
				fixed: m.adm_rp_mode_fixed(),
				infra: m.adm_rp_mode_infra(),
				all: m.adm_rp_mode_all()
			};
			return values.map((v) => ({ value: String(v), label: L[String(v)] ?? String(v) }));
		}
		if (key === 'kind' && kind === 'telemetry_threshold') {
			const L: Record<string, string> = {
				device: m.adm_rp_tk_device(),
				environment: m.adm_rp_tk_environment(),
				power: m.adm_rp_tk_power()
			};
			return values.map((v) => ({ value: String(v), label: L[String(v)] ?? String(v) }));
		}
		if (key === 'op') {
			const L: Record<string, string> = {
				'<': m.adm_rp_op_lt(),
				'<=': m.adm_rp_op_le(),
				'>': m.adm_rp_op_gt(),
				'>=': m.adm_rp_op_ge()
			};
			return values.map((v) => ({ value: String(v), label: L[String(v)] ?? String(v) }));
		}
		if (key === 'metric' && kind === 'telemetry_threshold') {
			const tk = String(params.kind ?? 'device');
			if (tk === 'power') {
				return [
					'ch1_voltage',
					'ch1_current',
					'ch2_voltage',
					'ch2_current',
					'ch3_voltage',
					'ch3_current'
				].map((k) => ({ value: k, label: k }));
			}
			return METRICS.filter((d) => d.kind === tk).map((d) => ({
				value: d.key,
				label: `${d.label()} (${d.key})`
			}));
		}
		if (key === 'connector' && kind === 'gateway_down') {
			return connectors.map((c) => ({ value: c, label: c }));
		}
		return undefined;
	}

	function suggest(path: string): { value: string; label: string }[] | undefined {
		return path.endsWith('nodes') ? nodes : undefined;
	}

	async function save(e: Event): Promise<void> {
		e.preventDefault();
		const errs: Record<string, string> = {};
		if (!name.trim()) errs.name = m.adm_required();
		if (cooldownMin === null || cooldownMin < 0 || cooldownMin > 10080)
			errs.cooldown_s = m.adm_field_invalid();
		const paramErrors = validate(schema, params);
		for (const [k, v] of Object.entries(paramErrors)) errs[`params.${k}`] = v;
		errors = errs;
		if (Object.keys(errs).length) {
			formError = m.adm_fix_fields();
			return;
		}
		saving = true;
		formError = null;
		const body = {
			name: name.trim(),
			kind,
			params: clean(schema, params),
			enabled,
			cooldown_s: Math.round((cooldownMin ?? 15) * 60),
			channels,
			severity,
			is_public: isPublic
		};
		try {
			if (existing) await adminApi.alerts.updateRule(existing.id, body);
			else await adminApi.alerts.createRule(body);
			onsaved();
		} catch (err) {
			errors = problemFields(err);
			formError = problemText(err);
		} finally {
			saving = false;
		}
	}

	// Errores de parámetros sin el prefijo `params.` para el formulario generado.
	const paramErrors = $derived(
		Object.fromEntries(
			Object.entries(errors)
				.filter(([k]) => k.startsWith('params.'))
				.map(([k, v]) => [k.slice(7), v])
		)
	);
</script>

<form class="adm-stack" onsubmit={save} novalidate>
	<div class="adm-grid">
		<TextField label={m.adm_name()} bind:value={name} required maxlength={80} error={errors.name} />
		<SelectField
			label={m.adm_rule_kind()}
			value={kind}
			options={KINDS.map((k) => ({ value: k, label: ruleKindLabel(k) }))}
			onchange={(v) => changeKind(v as RuleKind)}
			error={errors.kind}
		/>
		<SelectField
			label={m.adm_severity()}
			bind:value={severity}
			options={[
				{ value: 'info', label: m.alerts_severity_info() },
				{ value: 'warning', label: m.alerts_severity_warning() },
				{ value: 'critical', label: m.alerts_severity_critical() }
			]}
		/>
		<NumberField
			label={m.adm_cooldown()}
			hint={m.adm_cooldown_hint()}
			bind:value={cooldownMin}
			min={0}
			max={10080}
			step={1}
			unit="min"
			error={errors.cooldown_s}
		/>
	</div>

	<fieldset class="adm-fieldset">
		<legend>{m.adm_rule_params({ kind: ruleKindLabel(kind) })}</legend>
		{#if Object.keys(schema.properties ?? {}).length === 0}
			<p class="adm-muted">{m.adm_rule_no_params()}</p>
		{:else}
			<SchemaForm
				{schema}
				bind:value={params}
				errors={paramErrors}
				labelFor={(_p, key) => PARAM_LABELS[key]?.()}
				hintFor={(_p, key) => PARAM_HINTS[key]?.()}
				{optionsFor}
				{suggest}
			/>
		{/if}
	</fieldset>

	<CheckGroup
		legend={m.adm_rule_channels()}
		hint={m.adm_rule_channels_hint()}
		bind:values={channels}
		options={(['webpush', 'telegram', 'webhook', 'mqtt'] as NotifyChannel[]).map((c) => ({
			value: c,
			label: notifyChannelLabel(c)
		}))}
		error={errors.channels}
	/>
	<Toggle label={m.adm_rule_public()} hint={m.adm_rule_public_hint()} bind:checked={isPublic} />
	<Toggle label={m.adm_rule_enabled()} bind:checked={enabled} />
	{#if formError}<p class="adm-note danger" role="alert">{formError}</p>{/if}
	<div class="adm-row end">
		<Button onclick={oncancel}>{m.adm_cancel()}</Button>
		<Button type="submit" variant="primary" loading={saving}>{m.adm_save()}</Button>
	</div>
</form>
