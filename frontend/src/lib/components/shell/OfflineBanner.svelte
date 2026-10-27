<!-- Sin conexión: se muestran los últimos datos guardados (sección 20). -->
<script lang="ts">
	import WifiOff from '@lucide/svelte/icons/wifi-off';
	import { m } from '$lib/paraglide/messages';
	import { live } from '$lib/stores/live.svelte';
</script>

{#if live.status === 'offline'}
	<div class="offline surface-raised" role="status">
		<WifiOff size={16} aria-hidden="true" />
		<span>{m.live_offline_banner()}</span>
		<button type="button" onclick={() => live.restart()}>{m.live_retry()}</button>
	</div>
{/if}

<style>
	.offline {
		display: inline-flex;
		align-items: center;
		gap: 8px;
		padding: 6px 6px 6px 12px;
		border-radius: 999px;
		font-size: 0.8125rem;
		pointer-events: auto;
	}

	button {
		min-height: 36px;
		padding: 0 12px;
		border: 0;
		border-radius: 999px;
		background: var(--fill-2);
		color: var(--text-1);
		font: inherit;
		font-weight: 650;
	}
</style>
