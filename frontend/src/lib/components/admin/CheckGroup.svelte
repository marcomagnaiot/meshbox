<!-- Varias opciones con casillas (canales de notificación, fuentes de un plugin). -->
<script lang="ts" generics="V extends string">
	interface Option {
		value: V;
		label: string;
		hint?: string;
		disabled?: boolean;
	}

	interface Props {
		legend: string;
		hint?: string;
		error?: string | null;
		values: V[];
		options: Option[];
		disabled?: boolean;
	}

	let {
		legend,
		hint,
		error = null,
		values = $bindable([]),
		options,
		disabled = false
	}: Props = $props();
	const uid = $props.id();

	function toggle(v: V, on: boolean): void {
		values = on ? [...values.filter((x) => x !== v), v] : values.filter((x) => x !== v);
	}
</script>

<fieldset
	class="group"
	aria-describedby={[hint ? `${uid}-hint` : '', error ? `${uid}-err` : '']
		.filter(Boolean)
		.join(' ') || undefined}
>
	<legend>{legend}</legend>
	<div class="opts">
		{#each options as o (o.value)}
			<label class="opt">
				<input
					type="checkbox"
					checked={values.includes(o.value)}
					disabled={disabled || o.disabled}
					onchange={(e) => toggle(o.value, e.currentTarget.checked)}
				/>
				<span>
					{o.label}
					{#if o.hint}<span class="opt-hint">{o.hint}</span>{/if}
				</span>
			</label>
		{/each}
	</div>
	{#if hint}<p class="hint" id="{uid}-hint">{hint}</p>{/if}
	{#if error}<p class="error" id="{uid}-err">{error}</p>{/if}
</fieldset>

<style>
	.group {
		margin: 0;
		padding: 0;
		border: 0;
		min-width: 0;
	}

	legend {
		padding: 0;
		margin-bottom: 6px;
		font-size: 0.8125rem;
		font-weight: 600;
	}

	.opts {
		display: flex;
		flex-wrap: wrap;
		gap: 4px 16px;
	}

	.opt {
		display: flex;
		align-items: center;
		gap: 8px;
		min-height: 40px;
		font-size: 0.875rem;
		cursor: pointer;
	}

	.opt input {
		width: 18px;
		height: 18px;
		accent-color: var(--accent);
	}

	.opt-hint {
		display: block;
		font-size: 0.75rem;
		color: var(--text-2);
	}

	.hint {
		margin: 4px 0 0;
		font-size: 0.75rem;
		color: var(--text-2);
	}

	.error {
		margin: 4px 0 0;
		font-size: 0.75rem;
		font-weight: 600;
		padding-left: 8px;
		border-left: 3px solid var(--danger);
	}
</style>
