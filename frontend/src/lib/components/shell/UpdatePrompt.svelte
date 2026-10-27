<!--
  Registro del service worker y aviso de nueva versión con botón "Actualizar" (sección 20).
  El registro espera a que la página termine de cargar y el mapa haga su primer dibujo (o 10 s):
  la primera instalación baja unos 2,4 MB de precache que, con una conexión lenta, competirían
  con el mapa y las teselas.
-->
<script lang="ts">
	import { onMount } from 'svelte';
	import { mapController } from '$lib/map/controller.svelte';
	import { m } from '$lib/paraglide/messages';
	import { toasts } from '$lib/stores/ui.svelte';
	import { site } from '$lib/stores/site.svelte';

	const MAX_WAIT_MS = 10_000;

	function afterLoad(): Promise<void> {
		if (document.readyState === 'complete') return Promise.resolve();
		return new Promise((resolve) =>
			window.addEventListener('load', () => resolve(), { once: true })
		);
	}

	function idle(): Promise<void> {
		return new Promise((resolve) => {
			if ('requestIdleCallback' in window) requestIdleCallback(() => resolve(), { timeout: 5000 });
			else setTimeout(resolve, 500);
		});
	}

	async function quiet(): Promise<void> {
		await afterLoad();
		await Promise.race([
			mapController.whenIdle(),
			new Promise((resolve) => setTimeout(resolve, MAX_WAIT_MS))
		]);
		await idle();
	}

	onMount(() => {
		if (import.meta.env.DEV || !('serviceWorker' in navigator)) return;
		let unsub: (() => void) | undefined;
		let cancelled = false;
		void quiet()
			.then(() => site.load())
			.then(async (info) => {
				if (info.server !== 'remote') return false;
				// Hostname de administración: sin PWA (su caché mostraría el mapa en "/").
				const regs = await navigator.serviceWorker.getRegistrations();
				await Promise.all(regs.map((r) => r.unregister()));
				return true;
			})
			.then((adminHost) => (cancelled || adminHost ? null : import('virtual:pwa-register/svelte')))
			.then((mod) => {
				if (!mod || cancelled) return;
				const { needRefresh, offlineReady, updateServiceWorker } = mod.useRegisterSW({
					immediate: true,
					onRegisterError: (err) => console.warn('service worker:', err)
				});
				const a = needRefresh.subscribe((need) => {
					if (!need) return;
					toasts.show(m.update_available(), {
						kind: 'info',
						timeout: 0,
						action: { label: m.update_action(), run: () => void updateServiceWorker(true) }
					});
				});
				const b = offlineReady.subscribe((ready) => {
					if (ready) toasts.show(m.offline_ready(), { kind: 'success', timeout: 4000 });
				});
				unsub = () => {
					a();
					b();
				};
			})
			.catch((err) => console.warn('service worker:', err));
		return () => {
			cancelled = true;
			unsub?.();
		};
	});
</script>
