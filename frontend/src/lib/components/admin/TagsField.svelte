<!--
  Lista de textos cortos (tópicos, correos, ids de nodo, patrones): se agregan con Enter o
  coma y se quitan con su botón. Sugerencias opcionales con <datalist>.
-->
<script lang="ts">
	import X from '@lucide/svelte/icons/x';
	import { m } from '$lib/paraglide/messages';
	import Field from './Field.svelte';

	interface Props {
		label: string;
		hint?: string;
		error?: string | null;
		values: string[];
		placeholder?: string;
		suggestions?: { value: string; label?: string }[];
		/** Devuelve un mensaje si el valor no es válido (no se agrega). */
		validate?: (value: string) => string | null;
		/** No partir por comas (patrones de expresiones regulares). */
		noComma?: boolean;
		max?: number;
		mono?: boolean;
		disabled?: boolean;
	}

	let {
		label,
		hint,
		error = null,
		values = $bindable([]),
		placeholder,
		suggestions = [],
		validate,
		noComma = false,
		max,
		mono = false,
		disabled = false
	}: Props = $props();

	let draft = $state('');
	let localError = $state<string | null>(null);
	const uid = $props.id();
	const listId = `dl-${uid}`;

	function add(raw: string): void {
		const parts = (noComma ? [raw] : raw.split(',')).map((s) => s.trim()).filter(Boolean);
		const next = [...values];
		for (const p of parts) {
			const problem = validate?.(p) ?? null;
			if (problem) {
				localError = problem;
				return;
			}
			if (max !== undefined && next.length >= max) break;
			if (!next.includes(p)) next.push(p);
		}
		values = next;
		draft = '';
		localError = null;
	}

	function onKey(e: KeyboardEvent): void {
		if (e.key === 'Enter' || (!noComma && e.key === ',')) {
			e.preventDefault();
			if (draft.trim()) add(draft);
		} else if (e.key === 'Backspace' && !draft && values.length) {
			values = values.slice(0, -1);
		}
	}

	function remove(i: number): void {
		values = values.filter((_, j) => j !== i);
	}

	const labelOf = (v: string) => suggestions.find((s) => s.value === v)?.label;
</script>

<Field {label} {hint} error={localError ?? error}>
	{#snippet control({ id, describedby, invalid })}
		<div class="tags" class:disabled>
			{#if values.length}
				<ul class="chips" aria-label={label}>
					{#each values as v, i (v)}
						<li class="chip" class:adm-mono={mono}>
							<span>{labelOf(v) ? `${labelOf(v)} (${v})` : v}</span>
							<button
								type="button"
								class="x"
								aria-label={m.adm_list_remove({ item: v })}
								{disabled}
								onclick={() => remove(i)}><X size={14} aria-hidden="true" /></button
							>
						</li>
					{/each}
				</ul>
			{/if}
			<input
				{id}
				type="text"
				class="adm-input"
				class:mono
				bind:value={draft}
				list={suggestions.length ? listId : undefined}
				placeholder={placeholder ?? m.adm_list_placeholder()}
				aria-describedby={describedby}
				aria-invalid={invalid || undefined}
				disabled={disabled || (max !== undefined && values.length >= max)}
				onkeydown={onKey}
				onblur={() => draft.trim() && add(draft)}
			/>
			{#if suggestions.length}
				<datalist id={listId}>
					{#each suggestions as s (s.value)}
						<option value={s.value}>{s.label ?? s.value}</option>
					{/each}
				</datalist>
			{/if}
		</div>
	{/snippet}
</Field>

<style>
	.tags {
		display: flex;
		flex-direction: column;
		gap: 8px;
	}

	.chips {
		display: flex;
		flex-wrap: wrap;
		gap: 6px;
		margin: 0;
		padding: 0;
		list-style: none;
	}

	.chip {
		display: inline-flex;
		align-items: center;
		gap: 2px;
		max-width: 100%;
		padding: 2px 2px 2px 10px;
		border-radius: 999px;
		background: var(--fill-2);
		font-size: 0.8125rem;
	}

	.chip span {
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}

	.x {
		display: grid;
		place-items: center;
		width: 28px;
		height: 28px;
		border: 0;
		border-radius: 50%;
		background: transparent;
		color: var(--text-2);
	}

	.x:hover {
		background: var(--fill-2);
		color: var(--text-1);
	}

	@media (pointer: coarse) {
		.x {
			width: 36px;
			height: 36px;
		}
	}
</style>
