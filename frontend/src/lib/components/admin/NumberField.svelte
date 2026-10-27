<!-- Campo numérico: vacío = null (para parámetros opcionales). -->
<script lang="ts">
	import type { HTMLInputAttributes } from 'svelte/elements';
	import Field from './Field.svelte';

	interface Props extends Omit<HTMLInputAttributes, 'value' | 'type' | 'class'> {
		label: string;
		hint?: string;
		error?: string | null;
		value: number | null | undefined;
		unit?: string;
		hideLabel?: boolean;
	}

	let {
		label,
		hint,
		error = null,
		value = $bindable(null),
		unit,
		hideLabel = false,
		required = false,
		...rest
	}: Props = $props();
</script>

<Field {label} {hint} {error} {hideLabel} required={Boolean(required)}>
	{#snippet control({ id, describedby, invalid })}
		<span class="wrap">
			<input
				{id}
				type="number"
				inputmode="decimal"
				class="adm-input"
				bind:value
				aria-describedby={describedby}
				aria-invalid={invalid || undefined}
				{required}
				{...rest}
			/>
			{#if unit}<span class="unit" aria-hidden="true">{unit}</span>{/if}
		</span>
	{/snippet}
</Field>

<style>
	.wrap {
		position: relative;
		display: block;
	}

	.unit {
		position: absolute;
		right: 12px;
		top: 50%;
		transform: translateY(-50%);
		color: var(--text-2);
		font-size: 0.8125rem;
		pointer-events: none;
	}

	.wrap:has(.unit) :global(.adm-input) {
		padding-right: 52px;
	}
</style>
