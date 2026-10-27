<!-- Texto largo (aviso en Markdown, notas). -->
<script lang="ts">
	import type { HTMLTextareaAttributes } from 'svelte/elements';
	import Field from './Field.svelte';

	interface Props extends Omit<HTMLTextareaAttributes, 'value' | 'class'> {
		label: string;
		hint?: string;
		error?: string | null;
		value: string | null | undefined;
		mono?: boolean;
		hideLabel?: boolean;
	}

	let {
		label,
		hint,
		error = null,
		value = $bindable(''),
		mono = false,
		hideLabel = false,
		required = false,
		rows = 6,
		...rest
	}: Props = $props();
</script>

<Field {label} {hint} {error} {hideLabel} required={Boolean(required)}>
	{#snippet control({ id, describedby, invalid })}
		<textarea
			{id}
			class="adm-input"
			class:mono
			bind:value
			{rows}
			aria-describedby={describedby}
			aria-invalid={invalid || undefined}
			{required}
			{...rest}></textarea>
	{/snippet}
</Field>
