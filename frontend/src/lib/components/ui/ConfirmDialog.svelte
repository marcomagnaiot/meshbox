<!-- Diálogo de confirmación (bits-ui AlertDialog) para acciones destructivas o que cortan la conexión (18.3). -->
<script lang="ts">
	import { AlertDialog } from 'bits-ui';
	import { m } from '$lib/paraglide/messages';

	interface Props {
		open: boolean;
		title: string;
		description: string;
		confirmLabel: string;
		danger?: boolean;
		onconfirm: () => void;
	}

	let {
		open = $bindable(false),
		title,
		description,
		confirmLabel,
		danger = false,
		onconfirm
	}: Props = $props();
</script>

<AlertDialog.Root bind:open>
	<AlertDialog.Portal>
		<AlertDialog.Overlay class="modal-overlay" />
		<AlertDialog.Content class="confirm surface-raised">
			<AlertDialog.Title class="confirm-title">{title}</AlertDialog.Title>
			<AlertDialog.Description class="confirm-desc">{description}</AlertDialog.Description>
			<div class="confirm-actions">
				<AlertDialog.Cancel class="confirm-btn">{m.back()}</AlertDialog.Cancel>
				<AlertDialog.Action
					class="confirm-btn {danger ? 'danger' : 'primary'}"
					onclick={() => {
						onconfirm();
						open = false;
					}}>{confirmLabel}</AlertDialog.Action
				>
			</div>
		</AlertDialog.Content>
	</AlertDialog.Portal>
</AlertDialog.Root>

<style>
	:global(.confirm) {
		position: fixed;
		z-index: var(--z-modals);
		left: 50%;
		top: 50%;
		transform: translate(-50%, -50%);
		width: min(440px, calc(100vw - 24px));
		padding: 20px;
		border-radius: var(--r-lg);
		background: var(--surface-1);
	}

	:global(.confirm-title) {
		margin: 0 0 8px;
		font-size: 1.125rem;
		font-weight: 650;
	}

	:global(.confirm-desc) {
		margin: 0;
		color: var(--text-2);
		font-size: 0.875rem;
	}

	.confirm-actions {
		display: flex;
		justify-content: flex-end;
		gap: 8px;
		margin-top: 20px;
	}

	:global(.confirm-btn) {
		min-height: 44px;
		padding: 0 16px;
		border-radius: var(--r-sm);
		border: 1px solid var(--line);
		background: var(--fill-1);
		color: var(--text-1);
		font: inherit;
		font-weight: 600;
	}

	:global(.confirm-btn.primary) {
		background: var(--accent);
		color: var(--on-accent);
		border-color: transparent;
	}

	:global(.confirm-btn.danger) {
		background: var(--danger);
		color: #fff;
		border-color: transparent;
	}
</style>
