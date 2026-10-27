<!-- Indicador de conexión en vivo: "en vivo", "conectando", "reconectando" o "sin conexión". -->
<script lang="ts">
	import WifiOff from '@lucide/svelte/icons/wifi-off';
	import RefreshCw from '@lucide/svelte/icons/refresh-cw';
	import { m } from '$lib/paraglide/messages';
	import type { LiveStatus } from '$lib/stores/live.svelte';

	interface Props {
		status: LiveStatus;
		compact?: boolean;
		onretry?: () => void;
	}

	let { status, compact = false, onretry }: Props = $props();

	const text = $derived(
		status === 'live'
			? m.live_live()
			: status === 'connecting'
				? m.live_connecting()
				: status === 'reconnecting'
					? m.live_reconnecting()
					: m.live_offline()
	);
</script>

<span class="live" data-status={status}>
	{#if status === 'offline'}
		<WifiOff size={14} aria-hidden="true" />
	{:else}
		<span class="dot" aria-hidden="true"></span>
	{/if}
	<span class:sr-only={compact} aria-hidden="true">{text}</span>
	<span class="sr-only" role="status">{m.live_status({ status: text })}</span>
	{#if status === 'offline' && onretry}
		<button
			type="button"
			class="retry"
			onclick={onretry}
			aria-label={m.live_retry()}
			title={m.live_retry()}
		>
			<RefreshCw size={14} aria-hidden="true" />
		</button>
	{/if}
</span>

<style>
	.live {
		display: inline-flex;
		align-items: center;
		gap: 6px;
		font-size: 0.8125rem;
		font-weight: 600;
		color: var(--text-1);
		white-space: nowrap;
	}

	.dot {
		position: relative;
		width: 8px;
		height: 8px;
		border-radius: 50%;
		background: var(--success);
	}

	.live[data-status='live'] .dot::after {
		content: '';
		position: absolute;
		inset: -4px;
		border-radius: 50%;
		border: 2px solid var(--success);
		animation: pulse-ring 2s var(--ease) infinite;
	}

	.live[data-status='connecting'] .dot,
	.live[data-status='reconnecting'] .dot {
		background: var(--warning);
		animation: fade-in 0.9s ease-in-out infinite alternate;
	}

	.live[data-status='offline'] {
		color: var(--danger);
	}

	.retry {
		display: inline-grid;
		place-items: center;
		width: 28px;
		height: 28px;
		border: 0;
		border-radius: 8px;
		background: var(--fill-1);
		color: var(--text-1);
	}
</style>
