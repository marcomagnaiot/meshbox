<!--
  Diálogo modal (bits-ui Dialog): superficie sólida sobre un velo (sin glass sobre glass),
  foco atrapado, Escape para cerrar y título obligatorio.
-->
<script lang="ts">
	import { Dialog } from 'bits-ui';
	import X from '@lucide/svelte/icons/x';
	import type { Snippet } from 'svelte';
	import { m } from '$lib/paraglide/messages';

	interface Props {
		open: boolean;
		title: string;
		description?: string;
		children: Snippet;
		footer?: Snippet;
		size?: 'md' | 'lg' | 'full';
		onOpenChange?: (open: boolean) => void;
	}

	let {
		open = $bindable(false),
		title,
		description,
		children,
		footer,
		size = 'md',
		onOpenChange
	}: Props = $props();
</script>

<Dialog.Root bind:open {onOpenChange}>
	<Dialog.Portal>
		<Dialog.Overlay class="modal-overlay" />
		<Dialog.Content class="modal-content surface-raised modal-{size}">
			<header class="modal-head">
				<Dialog.Title class="modal-title">{title}</Dialog.Title>
				<Dialog.Close class="modal-close" aria-label={m.close()}>
					<X size={20} aria-hidden="true" />
				</Dialog.Close>
			</header>
			{#if description}
				<Dialog.Description class="modal-desc">{description}</Dialog.Description>
			{/if}
			<div class="modal-body">{@render children()}</div>
			{#if footer}<footer class="modal-foot">{@render footer()}</footer>{/if}
		</Dialog.Content>
	</Dialog.Portal>
</Dialog.Root>

<style>
	:global(.modal-overlay) {
		position: fixed;
		inset: 0;
		z-index: var(--z-modals);
		background: oklch(0% 0 0 / 0.55);
		animation: fade-in var(--dur-1) var(--ease);
	}

	:global(.modal-content) {
		position: fixed;
		z-index: var(--z-modals);
		left: 50%;
		top: 50%;
		transform: translate(-50%, -50%);
		width: min(560px, calc(100vw - 24px));
		max-height: calc(100dvh - 48px - var(--safe-top) - var(--safe-bottom));
		display: flex;
		flex-direction: column;
		border-radius: var(--r-lg);
		background: var(--surface-1);
		color: var(--text-1);
		animation: fade-in var(--dur-2) var(--ease);
	}

	:global(.modal-content.modal-lg) {
		width: min(860px, calc(100vw - 24px));
	}

	@media (max-width: 767px) {
		:global(.modal-content.modal-lg),
		:global(.modal-content.modal-full) {
			inset: auto 0 0 0;
			top: auto;
			left: 0;
			transform: none;
			width: 100%;
			max-height: calc(100dvh - var(--safe-top) - 24px);
			border-radius: var(--r-xl) var(--r-xl) 0 0;
			padding-bottom: var(--safe-bottom);
		}
	}

	.modal-head {
		display: flex;
		align-items: center;
		gap: 8px;
		padding: 12px 8px 4px 20px;
	}

	:global(.modal-title) {
		flex: 1;
		margin: 0;
		font-size: 1.125rem;
		font-weight: 650;
	}

	:global(.modal-close) {
		display: grid;
		place-items: center;
		width: 44px;
		height: 44px;
		border: 0;
		border-radius: var(--r-sm);
		background: transparent;
		color: var(--text-1);
	}

	:global(.modal-close:hover) {
		background: var(--fill-1);
	}

	:global(.modal-desc) {
		margin: 0;
		padding: 0 20px;
		color: var(--text-2);
		font-size: 0.875rem;
	}

	.modal-body {
		padding: 12px 20px 20px;
		overflow: auto;
	}

	.modal-foot {
		display: flex;
		justify-content: flex-end;
		gap: 8px;
		padding: 12px 20px 20px;
		border-top: 1px solid var(--line);
	}
</style>
