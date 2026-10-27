<!--
  Equipo recién instalado: en la red local el sitio avisa que falta el asistente de primer uso y
  lleva a /setup. Solo el servidor de la red local tiene /api/v1/setup (en el público da 404),
  y el aviso se va en cuanto existe el primer usuario.
-->
<script lang="ts">
	import Settings from '@lucide/svelte/icons/settings';
	import { onMount } from 'svelte';
	import { m } from '$lib/paraglide/messages';

	let pending = $state(false);

	onMount(() => {
		fetch('/api/v1/setup/state', { headers: { accept: 'application/json' } })
			.then((r) => (r.ok ? r.json() : null))
			.then((s: { users_exist?: boolean } | null) => (pending = s?.users_exist === false))
			.catch(() => {});
	});
</script>

{#if pending}
	<div class="setup surface-raised" role="status">
		<Settings size={16} aria-hidden="true" />
		<span>{m.setup_banner_text()}</span>
		<a href="/setup" data-sveltekit-reload>{m.setup_banner_action()}</a>
	</div>
{/if}

<style>
	.setup {
		display: inline-flex;
		align-items: center;
		gap: 8px;
		padding: 6px 6px 6px 12px;
		border-radius: 999px;
		font-size: 0.8125rem;
		pointer-events: auto;
	}

	a {
		display: inline-flex;
		align-items: center;
		min-height: 36px;
		padding: 0 12px;
		border-radius: 999px;
		background: var(--accent);
		color: var(--on-accent);
		font-weight: 650;
		text-decoration: none;
	}
</style>
