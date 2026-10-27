<script module lang="ts">
	// MapLibre se pide apenas arranca la app, sin esperar al layout público: con una conexión
	// lenta se gana una ida y vuelta (el panel y el asistente no tienen mapa).
	if (typeof location !== 'undefined' && !/^\/(admin|setup)(\/|$)/.test(location.pathname)) {
		import('$lib/map/MapView.svelte').catch(() => {});
	}
</script>

<script lang="ts">
	import '@fontsource-variable/inter';
	import '../app.css';
	import { onMount } from 'svelte';
	import { m } from '$lib/paraglide/messages';
	import { clock } from '$lib/stores/clock.svelte';
	import { prefs } from '$lib/stores/prefs.svelte';
	import { site } from '$lib/stores/site.svelte';
	import { ui } from '$lib/stores/ui.svelte';
	import '$lib/i18n/locale.svelte';
	import Toaster from '$lib/components/ui/Toaster.svelte';
	import UpdatePrompt from '$lib/components/shell/UpdatePrompt.svelte';

	let { children } = $props();

	onMount(() => {
		// La app ya está en pantalla: se quita la pantalla de arranque de app.html.
		const boot = document.getElementById('arranque');
		if (boot) {
			boot.classList.add('fuera');
			setTimeout(() => boot.remove(), 250);
		}
		prefs.apply();
		ui.start();
		clock.start();
		void site.load();
		return () => clock.stop();
	});
</script>

<svelte:head>
	<title>{site.data.name || m.app_name()}</title>
	{#if site.data.description}<meta name="description" content={site.data.description} />{/if}
</svelte:head>

<a class="skip" href="#contenido">{m.skip_to_content()}</a>
{@render children()}
<Toaster />
<UpdatePrompt />

<style>
	.skip {
		position: fixed;
		z-index: var(--z-modals);
		top: calc(var(--safe-top) + 8px);
		left: 8px;
		padding: 10px 14px;
		border-radius: var(--r-sm);
		background: var(--surface-2);
		color: var(--text-1);
		font-weight: 650;
		transform: translateY(-200%);
	}

	.skip:focus {
		transform: none;
	}
</style>
