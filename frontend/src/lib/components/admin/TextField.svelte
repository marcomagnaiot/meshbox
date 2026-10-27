<!-- Campo de texto (texto, correo, URL, búsqueda) con etiqueta, ayuda y error. -->
<script lang="ts">
	import type { Snippet } from 'svelte';
	import type { HTMLInputAttributes } from 'svelte/elements';
	import Field from './Field.svelte';

	interface Props extends Omit<HTMLInputAttributes, 'value' | 'type' | 'class'> {
		label: string;
		hint?: string;
		error?: string | null;
		value: string | null | undefined;
		type?: 'text' | 'email' | 'url' | 'search' | 'tel';
		mono?: boolean;
		hideLabel?: boolean;
		/** Acción al lado del control (ver Field). */
		trailing?: Snippet;
	}

	let {
		label,
		hint,
		error = null,
		value = $bindable(''),
		type = 'text',
		mono = false,
		hideLabel = false,
		trailing,
		required = false,
		...rest
	}: Props = $props();
</script>

<Field {label} {hint} {error} {hideLabel} {trailing} required={Boolean(required)}>
	{#snippet control({ id, describedby, invalid })}
		{#if type === 'email'}
			<input
				{id}
				type="email"
				class="adm-input"
				class:mono
				bind:value
				aria-describedby={describedby}
				aria-invalid={invalid || undefined}
				{required}
				{...rest}
			/>
		{:else if type === 'url'}
			<input
				{id}
				type="url"
				class="adm-input"
				class:mono
				bind:value
				aria-describedby={describedby}
				aria-invalid={invalid || undefined}
				{required}
				{...rest}
			/>
		{:else if type === 'search'}
			<input
				{id}
				type="search"
				class="adm-input"
				class:mono
				bind:value
				aria-describedby={describedby}
				aria-invalid={invalid || undefined}
				{required}
				{...rest}
			/>
		{:else}
			<input
				{id}
				type="text"
				class="adm-input"
				class:mono
				bind:value
				aria-describedby={describedby}
				aria-invalid={invalid || undefined}
				{required}
				{...rest}
			/>
		{/if}
	{/snippet}
</Field>
