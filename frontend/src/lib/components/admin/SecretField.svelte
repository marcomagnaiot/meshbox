<!--
  Secreto de solo escritura (13.4): nunca se muestra el guardado. Vacío = sin cambios; el
  servidor también acepta "********" con ese sentido. Botón para ver lo que se escribe.
-->
<script lang="ts">
	import Eye from '@lucide/svelte/icons/eye';
	import EyeOff from '@lucide/svelte/icons/eye-off';
	import type { HTMLInputAttributes } from 'svelte/elements';
	import { m } from '$lib/paraglide/messages';
	import Field from './Field.svelte';

	interface Props extends Omit<HTMLInputAttributes, 'value' | 'type' | 'class'> {
		label: string;
		hint?: string;
		error?: string | null;
		value: string | null | undefined;
		/** Ya hay uno guardado en el servidor. */
		isSet?: boolean;
		hideLabel?: boolean;
	}

	let {
		label,
		hint,
		error = null,
		value = $bindable(''),
		isSet = false,
		hideLabel = false,
		required = false,
		...rest
	}: Props = $props();
	let show = $state(false);
	const help = $derived(
		[isSet ? `${m.adm_secret_set()}. ${m.adm_secret_keep()}` : '', hint ?? '']
			.filter(Boolean)
			.join(' ')
	);
</script>

<Field {label} hint={help || undefined} {error} {hideLabel} required={Boolean(required) && !isSet}>
	{#snippet control({ id, describedby, invalid })}
		<span class="wrap">
			{#if show}
				<input
					{id}
					type="text"
					class="adm-input mono"
					bind:value
					autocomplete="off"
					spellcheck="false"
					placeholder={isSet ? '••••••••' : ''}
					aria-describedby={describedby}
					aria-invalid={invalid || undefined}
					required={Boolean(required) && !isSet}
					{...rest}
				/>
			{:else}
				<input
					{id}
					type="password"
					class="adm-input mono"
					bind:value
					autocomplete="new-password"
					spellcheck="false"
					placeholder={isSet ? '••••••••' : ''}
					aria-describedby={describedby}
					aria-invalid={invalid || undefined}
					required={Boolean(required) && !isSet}
					{...rest}
				/>
			{/if}
			<button
				type="button"
				class="eye"
				aria-pressed={show}
				aria-label={show ? m.admin_password_hide() : m.admin_password_show()}
				onclick={() => (show = !show)}
			>
				{#if show}<EyeOff size={18} aria-hidden="true" />{:else}<Eye
						size={18}
						aria-hidden="true"
					/>{/if}
			</button>
		</span>
	{/snippet}
</Field>

<style>
	.wrap {
		position: relative;
		display: block;
	}

	.wrap :global(.adm-input) {
		padding-right: 48px;
	}

	.eye {
		position: absolute;
		top: 0;
		right: 0;
		width: 44px;
		height: 44px;
		display: grid;
		place-items: center;
		border: 0;
		border-radius: var(--r-sm);
		background: transparent;
		color: var(--text-2);
	}

	.eye:hover {
		color: var(--text-1);
	}
</style>
