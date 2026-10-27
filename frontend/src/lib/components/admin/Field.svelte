<!--
  Campo de formulario del panel: etiqueta, control, ayuda y error enlazados por id
  (aria-describedby y aria-invalid los pone el control con los datos que recibe).
-->
<script lang="ts">
	import type { Snippet } from 'svelte';
	import type { ControlProps } from './types';

	interface Props {
		label: string;
		hint?: string;
		error?: string | null;
		required?: boolean;
		/** Etiqueta solo para lectores de pantalla (el contexto ya la muestra). */
		hideLabel?: boolean;
		control: Snippet<[ControlProps]>;
		/** Acción al lado del control (botón Guardar), alineada con él y no con la ayuda. */
		trailing?: Snippet;
	}

	let {
		label,
		hint,
		error = null,
		required = false,
		hideLabel = false,
		control,
		trailing
	}: Props = $props();
	const uid = $props.id();
	const id = `f-${uid}`;
	const describedby = $derived(
		[hint ? `${id}-hint` : '', error ? `${id}-err` : ''].filter(Boolean).join(' ') || undefined
	);
</script>

<div class="field" class:invalid={Boolean(error)}>
	<label for={id} class:sr-only={hideLabel}>
		{label}{#if required}<span class="req" aria-hidden="true"> *</span>{/if}
	</label>
	{#if trailing}
		<div class="with-trailing">
			{@render control({ id, describedby, invalid: Boolean(error) })}
			{@render trailing()}
		</div>
	{:else}
		{@render control({ id, describedby, invalid: Boolean(error) })}
	{/if}
	{#if hint}<p class="hint" id="{id}-hint">{hint}</p>{/if}
	{#if error}<p class="error" id="{id}-err">{error}</p>{/if}
</div>

<style>
	.field {
		display: flex;
		flex-direction: column;
		gap: 6px;
		min-width: 0;
	}

	.with-trailing {
		display: flex;
		align-items: center;
		gap: 8px;
	}

	.with-trailing > :global(:first-child) {
		flex: 1;
		min-width: 0;
	}

	label {
		font-size: 0.8125rem;
		font-weight: 600;
		color: var(--text-1);
	}

	.req {
		color: var(--danger);
	}

	.hint {
		margin: 0;
		font-size: 0.75rem;
		color: var(--text-2);
		line-height: 1.4;
	}

	.error {
		margin: 0;
		font-size: 0.75rem;
		font-weight: 600;
		color: var(--text-1);
		padding-left: 8px;
		border-left: 3px solid var(--danger);
	}
</style>
