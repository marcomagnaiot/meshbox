<!-- Avisos emergentes: superficie sólida (no glass), arriba de todo y anunciados al lector. -->
<script lang="ts">
	import X from '@lucide/svelte/icons/x';
	import { m } from '$lib/paraglide/messages';
	import { toasts } from '$lib/stores/ui.svelte';
</script>

<div class="toaster" role="region" aria-label={m.toasts_label()}>
	<!-- Región viva persistente: los avisos nuevos se anuncian; los errores, con role="alert". -->
	<ol aria-live="polite" aria-relevant="additions">
		{#each toasts.list as toast (toast.id)}
			<li class="toast surface-raised" data-kind={toast.kind}>
				<span class="msg" role={toast.kind === 'error' ? 'alert' : undefined}>{toast.message}</span>
				{#if toast.action}
					{@const action = toast.action}
					<button
						type="button"
						class="action"
						onclick={() => {
							action.run();
							toasts.dismiss(toast.id);
						}}>{action.label}</button
					>
				{/if}
				<button
					type="button"
					class="close"
					aria-label={m.dismiss()}
					onclick={() => toasts.dismiss(toast.id)}
				>
					<X size={16} aria-hidden="true" />
				</button>
			</li>
		{/each}
	</ol>
</div>

<style>
	.toaster {
		position: fixed;
		z-index: var(--z-toasts);
		left: 50%;
		transform: translateX(-50%);
		top: calc(var(--safe-top) + 12px);
		width: min(440px, calc(100vw - 24px));
		pointer-events: none;
	}

	ol {
		list-style: none;
		margin: 0;
		padding: 0;
		display: flex;
		flex-direction: column;
		gap: 8px;
	}

	.toast {
		pointer-events: auto;
		display: flex;
		align-items: center;
		gap: 8px;
		padding: 8px 8px 8px 14px;
		border-radius: var(--r-md);
		font-size: 0.875rem;
		animation: slide-up var(--dur-2) var(--ease);
		border-left: 4px solid var(--accent);
	}

	.toast[data-kind='success'] {
		border-left-color: var(--success);
	}

	.toast[data-kind='warning'] {
		border-left-color: var(--warning);
	}

	.toast[data-kind='error'] {
		border-left-color: var(--danger);
	}

	.msg {
		flex: 1;
	}

	.action {
		border: 0;
		background: var(--accent-soft);
		color: var(--text-1);
		font: inherit;
		font-weight: 600;
		padding: 8px 12px;
		border-radius: 8px;
		min-height: 36px;
	}

	.close {
		display: grid;
		place-items: center;
		width: 36px;
		height: 36px;
		border: 0;
		background: transparent;
		color: var(--text-2);
		border-radius: 8px;
	}

	.close:hover {
		background: var(--fill-1);
	}
</style>
