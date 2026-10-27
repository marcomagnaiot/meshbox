<!-- Botón para activar notificaciones de alertas públicas (oculto si el sitio no tiene push). -->
<script lang="ts">
	import BellOff from '@lucide/svelte/icons/bell-off';
	import BellRing from '@lucide/svelte/icons/bell-ring';
	import { onMount } from 'svelte';
	import { m } from '$lib/paraglide/messages';
	import { push } from '$lib/stores/push.svelte';
	import { site } from '$lib/stores/site.svelte';
	import Button from '$lib/components/ui/Button.svelte';

	onMount(() => void push.refresh());

	const message = $derived(
		push.state === 'denied'
			? m.push_denied()
			: push.state === 'unsupported'
				? m.push_unsupported()
				: push.state === 'needs-install'
					? m.push_ios_install()
					: push.state === 'unavailable'
						? m.push_unavailable()
						: push.state === 'on'
							? m.push_enabled()
							: null
	);
</script>

{#if site.data.features.push}
	<section class="push card" aria-labelledby="push-title">
		<div class="text">
			<h2 id="push-title">{m.push_title()}</h2>
			<p>{m.push_description()}</p>
			{#if message}<p class="state" role="status">{message}</p>{/if}
		</div>
		{#if push.state === 'on'}
			<Button icon={BellOff} variant="secondary" onclick={() => push.disable()}
				>{m.push_disable()}</Button
			>
		{:else if push.state === 'off' || push.state === 'working' || push.state === 'checking'}
			<Button
				icon={BellRing}
				variant="primary"
				loading={push.state === 'working'}
				disabled={push.state === 'checking'}
				onclick={() => push.enable()}>{m.push_enable()}</Button
			>
		{/if}
	</section>
{/if}

<style>
	.push {
		display: flex;
		align-items: center;
		gap: 12px;
		flex-wrap: wrap;
		padding: 12px 14px;
	}

	.text {
		flex: 1;
		min-width: 200px;
	}

	h2 {
		margin: 0 0 2px;
		font-size: 0.875rem;
		font-weight: 700;
	}

	p {
		margin: 0;
		font-size: 0.8125rem;
		color: var(--text-2);
	}

	.state {
		margin-top: 4px;
		color: var(--text-1);
		font-weight: 600;
	}
</style>
