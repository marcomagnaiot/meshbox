<!--
  Confirmación de una acción destructiva o que corta la conexión (18.3). Ejecuta la acción
  dentro del diálogo: si falla, muestra el error y queda abierto; opcionalmente pide escribir
  una palabra (borrar historial, restaurar, desconectar).
-->
<script lang="ts">
	import { AlertDialog } from 'bits-ui';
	import type { Snippet } from 'svelte';
	import { problemText } from '$lib/admin/errors';
	import { m } from '$lib/paraglide/messages';
	import LoaderCircle from '@lucide/svelte/icons/loader-circle';

	interface Props {
		open: boolean;
		title: string;
		description: string;
		confirmLabel: string;
		danger?: boolean;
		/** Palabra a escribir para habilitar la confirmación. */
		requireText?: string;
		action: () => Promise<unknown>;
		onsuccess?: (result: unknown) => void;
		children?: Snippet;
	}

	let {
		open = $bindable(false),
		title,
		description,
		confirmLabel,
		danger = false,
		requireText,
		action,
		onsuccess,
		children
	}: Props = $props();

	let typed = $state('');
	let busy = $state(false);
	let error = $state<string | null>(null);
	const uid = $props.id();
	const ready = $derived(!requireText || typed.trim() === requireText);

	$effect(() => {
		if (open) {
			typed = '';
			error = null;
		}
	});

	async function run(e: Event): Promise<void> {
		e.preventDefault();
		if (!ready || busy) return;
		busy = true;
		error = null;
		try {
			const result = await action();
			open = false;
			onsuccess?.(result);
		} catch (err) {
			error = problemText(err);
		} finally {
			busy = false;
		}
	}
</script>

<AlertDialog.Root bind:open>
	<AlertDialog.Portal>
		<AlertDialog.Overlay class="modal-overlay" />
		<AlertDialog.Content class="confirm surface-raised">
			<form onsubmit={run}>
				<AlertDialog.Title class="confirm-title">{title}</AlertDialog.Title>
				<AlertDialog.Description class="confirm-desc">{description}</AlertDialog.Description>
				{#if children}<div class="extra">{@render children()}</div>{/if}
				{#if requireText}
					<label class="type" for="ct-{uid}">{m.adm_confirm_type({ word: requireText })}</label>
					<input
						id="ct-{uid}"
						class="adm-input mono"
						bind:value={typed}
						autocomplete="off"
						spellcheck="false"
					/>
				{/if}
				{#if error}<p class="err" role="alert">{error}</p>{/if}
				<div class="confirm-actions">
					<AlertDialog.Cancel class="confirm-btn" disabled={busy}
						>{m.adm_cancel()}</AlertDialog.Cancel
					>
					<button
						type="submit"
						class="confirm-btn {danger ? 'danger' : 'primary'}"
						disabled={!ready || busy}
						aria-busy={busy || undefined}
					>
						{#if busy}<LoaderCircle size={16} class="animate-spin" aria-hidden="true" />{/if}
						{confirmLabel}
					</button>
				</div>
			</form>
		</AlertDialog.Content>
	</AlertDialog.Portal>
</AlertDialog.Root>

<style>
	.extra {
		margin-top: 14px;
	}

	.type {
		display: block;
		margin: 14px 0 6px;
		font-size: 0.8125rem;
		font-weight: 600;
	}

	.err {
		margin: 12px 0 0;
		padding: 8px 10px;
		border-radius: var(--r-sm);
		background: var(--danger-soft);
		font-size: 0.8125rem;
	}

	.confirm-actions {
		display: flex;
		justify-content: flex-end;
		gap: 8px;
		margin-top: 20px;
	}

	button.confirm-btn {
		display: inline-flex;
		align-items: center;
		gap: 6px;
	}

	button.confirm-btn:disabled {
		opacity: 0.55;
	}
</style>
