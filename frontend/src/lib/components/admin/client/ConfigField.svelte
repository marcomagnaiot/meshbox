<!--
  Un campo de la configuración de la placa según su descriptor (tipo del protobuf): interruptor,
  lista de opciones, texto, número u objeto anidado. Las claves guardadas llegan enmascaradas y
  no cambian si no se escribe una nueva; listas y bytes se muestran sin editar.
-->
<script lang="ts">
	import { fieldLabel, MASK, type ConfigField } from '$lib/admin/radio';
	import { m } from '$lib/paraglide/messages';
	import Toggle from '$lib/components/ui/Toggle.svelte';
	import NumberField from '$lib/components/admin/NumberField.svelte';
	import SecretField from '$lib/components/admin/SecretField.svelte';
	import SelectField from '$lib/components/admin/SelectField.svelte';
	import TextField from '$lib/components/admin/TextField.svelte';
	import Self from './ConfigField.svelte';

	interface Props {
		field: ConfigField;
		/** Ruta del campo en el borrador (`map_report_settings.publish_interval_secs`). */
		path: string;
		get: (path: string) => unknown;
		set: (path: string, value: unknown) => void;
		disabled?: boolean;
	}

	let { field, path, get, set, disabled = false }: Props = $props();

	const label = $derived(fieldLabel(field.name));
	const hint = $derived(field.danger ? m.adm_cli_field_danger({ name: field.name }) : field.name);
	const locked = $derived(disabled || field.readonly);

	function secretInput(v: string | null | undefined): void {
		const text = (v ?? '').trim();
		if (!text) return set(path, MASK);
		const n = Number.parseInt(text, 10);
		set(path, field.type === 'int' ? (Number.isFinite(n) ? n : MASK) : text);
	}

	function readonlyText(v: unknown): string {
		if (Array.isArray(v)) return v.length ? v.join(', ') : '—';
		if (v === null || v === undefined || v === '') return '—';
		return String(v);
	}
</script>

{#if field.type === 'object'}
	<fieldset class="adm-fieldset">
		<legend>{label}</legend>
		{#if field.fields?.length && !field.readonly}
			<div class="adm-stack">
				{#each field.fields as sub (sub.name)}
					<Self field={sub} path="{path}.{sub.name}" {get} {set} disabled={locked} />
				{/each}
			</div>
		{:else}
			<p class="adm-muted">{m.adm_cli_not_editable()}</p>
		{/if}
	</fieldset>
{:else if field.type === 'bool'}
	<Toggle
		{label}
		{hint}
		disabled={locked}
		bind:checked={() => Boolean(get(path)), (v) => set(path, v)}
	/>
{:else if field.type === 'enum' && field.options}
	<SelectField
		{label}
		{hint}
		options={field.options.map((o) => ({ value: o, label: o }))}
		disabled={locked}
		bind:value={() => String(get(path) ?? ''), (v) => set(path, v)}
	/>
{:else if field.secret && (field.type === 'string' || field.type === 'int')}
	<!-- Clave de texto o numérica (PIN de Bluetooth): llega enmascarada, se reemplaza entera. -->
	<SecretField
		{label}
		{hint}
		isSet={field.value === MASK}
		disabled={locked}
		autocomplete="off"
		inputmode={field.type === 'int' ? 'numeric' : undefined}
		bind:value={() => (get(path) === MASK ? '' : String(get(path) ?? '')), secretInput}
	/>
{:else if field.type === 'string'}
	<TextField
		{label}
		{hint}
		maxlength={field.max_length}
		disabled={locked}
		bind:value={() => String(get(path) ?? ''), (v) => set(path, v ?? '')}
	/>
{:else if field.type === 'int' || field.type === 'float'}
	<NumberField
		{label}
		{hint}
		min={field.min}
		max={field.max}
		step={field.type === 'int' ? 1 : 'any'}
		disabled={locked}
		bind:value={() => (get(path) as number | null | undefined) ?? null, (v) => set(path, v)}
	/>
{:else}
	<div class="ro">
		<span class="ro-label">{label}</span>
		<span class="adm-mono">{readonlyText(get(path))}</span>
		<span class="adm-muted">{m.adm_cli_not_editable()}</span>
	</div>
{/if}

<style>
	.ro {
		display: flex;
		flex-direction: column;
		gap: 2px;
		font-size: 0.875rem;
		overflow-wrap: anywhere;
	}

	.ro-label {
		font-weight: 600;
	}

	.ro .adm-muted {
		font-size: 0.75rem;
	}
</style>
