<!--
  Formulario generado desde un JSON Schema (18.3): reglas de alerta y ajustes de plugins.
  Cada propiedad elige su control por tipo; los objetos anidados se dibujan con el mismo
  componente. Los errores llegan por ruta (`scope.nodes`) desde la validación local o el 422.
-->
<script lang="ts">
	import Plus from '@lucide/svelte/icons/plus';
	import Trash2 from '@lucide/svelte/icons/trash-2';
	import { fieldKind, resolve, titleOf, defaults } from '$lib/admin/schema';
	import type { JsonSchema } from '$lib/admin/types';
	import { m } from '$lib/paraglide/messages';
	import Toggle from '$lib/components/ui/Toggle.svelte';
	import CheckGroup from './CheckGroup.svelte';
	import NumberField from './NumberField.svelte';
	import SchemaForm from './SchemaForm.svelte';
	import SecretField from './SecretField.svelte';
	import SelectField from './SelectField.svelte';
	import TagsField from './TagsField.svelte';
	import TextArea from './TextArea.svelte';
	import TextField from './TextField.svelte';

	type Opt = { value: string; label: string };

	interface Props {
		schema: JsonSchema;
		root?: JsonSchema;
		value: Record<string, unknown>;
		errors?: Record<string, string>;
		path?: string;
		/** Etiqueta propia (traducción) para una ruta; si no, el título del esquema. */
		labelFor?: (path: string, key: string) => string | undefined;
		hintFor?: (path: string, key: string) => string | undefined;
		/** Etiquetas de opciones de un enum. */
		optionsFor?: (path: string, values: unknown[]) => Opt[] | undefined;
		/** Sugerencias para listas de textos (ids de nodo, conectores). */
		suggest?: (path: string) => Opt[] | undefined;
		secretsSet?: (path: string) => boolean;
		/** Claves a no dibujar (las maneja el formulario contenedor). */
		skip?: string[];
		disabled?: boolean;
		/** Elementos de una lista: columnas más angostas. */
		compact?: boolean;
	}

	let {
		schema,
		root = schema,
		value = $bindable({}),
		errors = {},
		path = '',
		labelFor,
		hintFor,
		optionsFor,
		suggest,
		secretsSet,
		skip = [],
		disabled = false,
		compact = false
	}: Props = $props();

	const WIDE = new Set([
		'text',
		'multi-enum',
		'string-list',
		'number-list',
		'object',
		'object-list',
		'unknown'
	]);

	const resolved = $derived(resolve(schema, root).schema);
	const required = $derived(new Set(resolved.required ?? []));
	const entries = $derived(
		Object.entries(resolved.properties ?? {}).filter(([k]) => !skip.includes(k))
	);

	const join = (key: string) => (path ? `${path}.${key}` : key);
	const label = (key: string, prop: JsonSchema) =>
		labelFor?.(join(key), key) ?? titleOf(key, prop, root);
	const hint = (key: string, prop: JsonSchema) =>
		hintFor?.(join(key), key) ?? resolve(prop, root).schema.description;

	function enumOptions(key: string, prop: JsonSchema): Opt[] {
		const r = resolve(prop, root);
		const values = r.schema.enum ?? (r.schema.const !== undefined ? [r.schema.const] : []);
		const custom = optionsFor?.(join(key), values);
		const opts = custom ?? values.map((v) => ({ value: String(v), label: String(v) }));
		return r.nullable ? [{ value: '', label: m.adm_null() }, ...opts] : opts;
	}

	function itemEnum(key: string, prop: JsonSchema): Opt[] {
		const items = resolve(prop, root).schema.items;
		const values = items ? (resolve(items, root).schema.enum ?? []) : [];
		return (
			optionsFor?.(join(key), values) ?? values.map((v) => ({ value: String(v), label: String(v) }))
		);
	}

	function enumValue(key: string, prop: JsonSchema, raw: string): unknown {
		const r = resolve(prop, root).schema;
		if (raw === '') return null;
		return (r.enum ?? [r.const]).find((v) => String(v) === raw) ?? raw;
	}

	function numberValidator(v: string): string | null {
		return Number.isFinite(Number(v)) ? null : m.adm_field_invalid();
	}

	function asObject(v: unknown): Record<string, unknown> {
		return v && typeof v === 'object' && !Array.isArray(v) ? (v as Record<string, unknown>) : {};
	}

	function addItem(key: string, prop: JsonSchema): void {
		const items = resolve(prop, root).schema.items;
		const list = Array.isArray(value[key]) ? [...(value[key] as unknown[])] : [];
		list.push(items ? defaults(items, root) : {});
		value[key] = list;
	}

	function removeItem(key: string, i: number): void {
		const list = Array.isArray(value[key]) ? [...(value[key] as unknown[])] : [];
		list.splice(i, 1);
		value[key] = list;
	}
</script>

<div class="schema-form" class:compact>
	{#each entries as [key, prop] (key)}
		{@const kind = fieldKind(prop, root)}
		{@const r = resolve(prop, root)}
		{@const p = join(key)}
		{@const req = required.has(key)}
		<div
			class="cell"
			class:wide={WIDE.has(kind) || (kind === 'string' && (r.schema.maxLength ?? 0) >= 200)}
		>
			{#if kind === 'boolean'}
				<div class="toggle-field">
					<Toggle
						label={label(key, prop)}
						hint={hint(key, prop)}
						{disabled}
						bind:checked={() => Boolean(value[key]), (v) => (value[key] = v)}
					/>
					{#if errors[p]}<p class="error" role="alert">{errors[p]}</p>{/if}
				</div>
			{:else if kind === 'integer' || kind === 'number'}
				<NumberField
					label={label(key, prop)}
					hint={hint(key, prop)}
					error={errors[p]}
					required={req}
					{disabled}
					min={r.schema.minimum ?? r.schema.exclusiveMinimum}
					max={r.schema.maximum ?? r.schema.exclusiveMaximum}
					step={kind === 'integer' ? 1 : 'any'}
					bind:value={
						() => (typeof value[key] === 'number' ? (value[key] as number) : null),
						(v) => (value[key] = v === null || v === undefined || Number.isNaN(v) ? null : v)
					}
				/>
			{:else if kind === 'enum'}
				<SelectField
					label={label(key, prop)}
					hint={hint(key, prop)}
					error={errors[p]}
					required={req}
					{disabled}
					options={enumOptions(key, prop)}
					bind:value={
						() => (value[key] === null || value[key] === undefined ? '' : String(value[key])),
						(v) => (value[key] = enumValue(key, prop, v))
					}
				/>
			{:else if kind === 'secret'}
				<SecretField
					label={label(key, prop)}
					hint={hint(key, prop)}
					error={errors[p]}
					required={req}
					{disabled}
					isSet={secretsSet?.(p) ?? value[key] === '********'}
					maxlength={r.schema.maxLength}
					bind:value={
						() =>
							typeof value[key] === 'string' && value[key] !== '********'
								? (value[key] as string)
								: '',
						(v) => (value[key] = v)
					}
				/>
			{:else if kind === 'text'}
				<TextArea
					label={label(key, prop)}
					hint={hint(key, prop)}
					error={errors[p]}
					required={req}
					{disabled}
					maxlength={r.schema.maxLength}
					bind:value={() => (value[key] as string) ?? '', (v) => (value[key] = v)}
				/>
			{:else if kind === 'string' && optionsFor?.(p, [])?.length}
				<!-- Texto con valores conocidos (conectores, métricas): lista desplegable. -->
				<SelectField
					label={label(key, prop)}
					hint={hint(key, prop)}
					error={errors[p]}
					required={req}
					{disabled}
					options={[
						...(r.nullable || !req ? [{ value: '', label: m.adm_null() }] : []),
						...(optionsFor?.(p, []) ?? [])
					]}
					bind:value={
						() => (value[key] === null || value[key] === undefined ? '' : String(value[key])),
						(v) => (value[key] = v === '' ? (r.nullable ? null : '') : v)
					}
				/>
			{:else if kind === 'string'}
				<TextField
					label={label(key, prop)}
					hint={hint(key, prop)}
					error={errors[p]}
					required={req}
					{disabled}
					maxlength={r.schema.maxLength}
					type={r.schema.format === 'uri' || /url/i.test(key) ? 'url' : 'text'}
					bind:value={
						() => (value[key] === null || value[key] === undefined ? '' : String(value[key])),
						(v) => (value[key] = v === '' && r.nullable ? null : v)
					}
				/>
			{:else if kind === 'multi-enum'}
				<CheckGroup
					legend={label(key, prop)}
					hint={hint(key, prop)}
					error={errors[p]}
					{disabled}
					options={itemEnum(key, prop)}
					bind:values={
						() => (Array.isArray(value[key]) ? (value[key] as unknown[]).map(String) : []),
						(v) => (value[key] = v)
					}
				/>
			{:else if kind === 'string-list' || kind === 'number-list'}
				<TagsField
					label={label(key, prop)}
					hint={hint(key, prop)}
					error={errors[p] ?? Object.entries(errors).find(([e]) => e.startsWith(`${p}.`))?.[1]}
					{disabled}
					noComma={key === 'patterns'}
					mono={key === 'patterns' || key === 'nodes'}
					max={r.schema.maxItems}
					suggestions={suggest?.(p) ?? []}
					validate={kind === 'number-list' ? numberValidator : undefined}
					bind:values={
						() => (Array.isArray(value[key]) ? (value[key] as unknown[]).map(String) : []),
						(v) => (value[key] = kind === 'number-list' ? v.map(Number) : v)
					}
				/>
			{:else if kind === 'object'}
				<fieldset class="adm-fieldset">
					<legend>{label(key, prop)}</legend>
					{#if hint(key, prop)}<p class="adm-muted desc">{hint(key, prop)}</p>{/if}
					<SchemaForm
						schema={prop}
						{root}
						path={p}
						{errors}
						{labelFor}
						{hintFor}
						{optionsFor}
						{suggest}
						{secretsSet}
						{disabled}
						bind:value={() => asObject(value[key]), (v) => (value[key] = v)}
					/>
				</fieldset>
			{:else if kind === 'object-list'}
				{@const items = Array.isArray(value[key]) ? (value[key] as unknown[]) : []}
				<fieldset class="adm-fieldset">
					<legend>{label(key, prop)}</legend>
					{#if hint(key, prop)}<p class="adm-muted desc">{hint(key, prop)}</p>{/if}
					<div class="list">
						{#each items as item, i (i)}
							<div class="item">
								<SchemaForm
									compact
									schema={r.schema.items ?? {}}
									{root}
									path="{p}.{i}"
									{errors}
									{labelFor}
									{hintFor}
									{optionsFor}
									{suggest}
									{secretsSet}
									{disabled}
									bind:value={
										() => asObject(item),
										(v) => {
											const list = [...items];
											list[i] = v;
											value[key] = list;
										}
									}
								/>
								<button
									type="button"
									class="remove"
									{disabled}
									onclick={() => removeItem(key, i)}
									aria-label={m.adm_list_remove({ item: `${label(key, prop)} ${i + 1}` })}
								>
									<Trash2 size={16} aria-hidden="true" />
								</button>
							</div>
						{/each}
					</div>
					<button type="button" class="add" {disabled} onclick={() => addItem(key, prop)}>
						<Plus size={16} aria-hidden="true" />{m.adm_list_add()}
					</button>
				</fieldset>
			{/if}
		</div>
	{/each}
</div>

<style>
	/* Campos cortos en columnas; listas, textos largos y objetos ocupan la fila entera. */
	.schema-form {
		display: grid;
		grid-template-columns: repeat(auto-fill, minmax(min(100%, 240px), 1fr));
		gap: 14px 16px;
		align-items: start;
	}

	.schema-form.compact {
		grid-template-columns: repeat(auto-fit, minmax(min(100%, 150px), 1fr));
	}

	.cell {
		min-width: 0;
	}

	.cell.wide {
		grid-column: 1 / -1;
	}

	.toggle-field {
		display: flex;
		flex-direction: column;
		gap: 4px;
	}

	.error {
		margin: 0;
		font-size: 0.75rem;
		font-weight: 600;
		padding-left: 8px;
		border-left: 3px solid var(--danger);
	}

	.desc {
		margin: 0 0 10px;
	}

	.list {
		display: flex;
		flex-direction: column;
		gap: 12px;
	}

	.item {
		display: grid;
		grid-template-columns: minmax(0, 1fr) auto;
		gap: 8px;
		align-items: start;
		padding-bottom: 12px;
		border-bottom: 1px solid var(--line);
	}

	.remove,
	.add {
		display: inline-flex;
		align-items: center;
		justify-content: center;
		gap: 6px;
		min-height: 40px;
		min-width: 40px;
		padding: 0 10px;
		border: 1px solid var(--line);
		border-radius: var(--r-sm);
		background: var(--fill-1);
		color: var(--text-1);
		font: inherit;
		font-size: 0.8125rem;
		font-weight: 600;
	}

	.add {
		margin-top: 10px;
	}
</style>
