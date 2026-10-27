<!-- Lista desplegable nativa (accesible y cómoda en el celular). -->
<script lang="ts" generics="V extends string | number">
	import type { Snippet } from 'svelte';
	import type { HTMLSelectAttributes } from 'svelte/elements';
	import Field from './Field.svelte';

	interface Option {
		value: V;
		label: string;
		disabled?: boolean;
	}

	interface Props extends Omit<HTMLSelectAttributes, 'value' | 'class' | 'onchange'> {
		label: string;
		hint?: string;
		error?: string | null;
		value: V;
		options: Option[];
		hideLabel?: boolean;
		/** Acción al lado del control (ver Field). */
		trailing?: Snippet;
		onchange?: (value: V) => void;
	}

	let {
		label,
		hint,
		error = null,
		value = $bindable(),
		options,
		hideLabel = false,
		trailing,
		required = false,
		onchange,
		...rest
	}: Props = $props();
</script>

<Field {label} {hint} {error} {hideLabel} {trailing} required={Boolean(required)}>
	{#snippet control({ id, describedby, invalid })}
		<select
			{id}
			class="adm-input"
			bind:value
			aria-describedby={describedby}
			aria-invalid={invalid || undefined}
			{required}
			onchange={() => onchange?.(value)}
			{...rest}
		>
			{#each options as o (o.value)}
				<option value={o.value} disabled={o.disabled}>{o.label}</option>
			{/each}
		</select>
	{/snippet}
</Field>
