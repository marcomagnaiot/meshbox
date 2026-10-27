<!--
  Asistente de primer uso (18.1) contra /api/v1/setup: WiFi (solo con el punto de acceso),
  código de configuración, idioma y zona horaria, administrador, sitio, radio, canal público,
  privacidad, mapa base, Cloudflare y verificación. Retoma en el primer paso pendiente; con
  usuarios ya creados pide iniciar sesión, y sin usuarios respeta la ventana de 60 min.
-->
<script lang="ts">
	import Wand from '@lucide/svelte/icons/wand-sparkles';
	import { onMount, tick } from 'svelte';
	import { fmt } from '$lib/i18n/fmt.svelte';
	import { m } from '$lib/paraglide/messages';
	import { Wizard } from '$lib/setup/wizard.svelte';
	import { site } from '$lib/stores/site.svelte';
	import Button from '$lib/components/ui/Button.svelte';
	import Skeleton from '$lib/components/ui/Skeleton.svelte';
	import AppearanceMenu from '$lib/components/shell/AppearanceMenu.svelte';
	import ProblemNote from '$lib/components/admin/ProblemNote.svelte';
	import StepAdmin from '$lib/components/setup/StepAdmin.svelte';
	import StepChannel from '$lib/components/setup/StepChannel.svelte';
	import StepCloudflare from '$lib/components/setup/StepCloudflare.svelte';
	import StepCode from '$lib/components/setup/StepCode.svelte';
	import StepFinish from '$lib/components/setup/StepFinish.svelte';
	import StepLocale from '$lib/components/setup/StepLocale.svelte';
	import StepPrivacy from '$lib/components/setup/StepPrivacy.svelte';
	import StepRadio from '$lib/components/setup/StepRadio.svelte';
	import StepSite from '$lib/components/setup/StepSite.svelte';
	import StepTiles from '$lib/components/setup/StepTiles.svelte';
	import StepWifi from '$lib/components/setup/StepWifi.svelte';
	import Stepper from '$lib/components/setup/Stepper.svelte';
	import '$lib/components/admin/admin.css';

	const wizard = new Wizard();
	/** Con el asistente terminado se muestra un resumen, salvo que se pida revisarlo. */
	let review = $state(false);
	let loaded = false;

	onMount(() => {
		void site.load();
		void wizard.load().then(() => (loaded = true));
	});

	// Al cambiar de paso, el foco va al título (lectores de pantalla y teclado).
	$effect(() => {
		void wizard.current;
		if (!loaded) return;
		void tick().then(() => document.getElementById('step-title')?.focus());
	});

	const finished = $derived(Boolean(wizard.state?.done && wizard.state.users_exist) && !review);
</script>

<svelte:head><title>{m.setup_title()}</title></svelte:head>

<div class="setup">
	<header class="top">
		<span class="brand">
			<img src={site.data.logo_url ?? '/favicon.svg'} alt="" width="28" height="28" />
			<span>{m.setup_title()}</span>
		</span>
		<span class="spacer"></span>
		<AppearanceMenu />
	</header>

	<main id="contenido" class="main" tabindex="-1">
		{#if wizard.access === 'loading'}
			<div class="card surface-raised"><Skeleton lines={6} label={m.loading()} /></div>
		{:else if wizard.access === 'error'}
			<div class="card surface-raised">
				<ProblemNote error={wizard.error} onretry={() => wizard.load()} />
			</div>
		{:else if wizard.access === 'closed'}
			<div class="card surface-raised notice">
				<h1>{m.setup_closed_title()}</h1>
				<p>{m.setup_closed_desc()}</p>
			</div>
		{:else if wizard.access === 'login'}
			<div class="card surface-raised notice">
				<h1>{m.setup_login_title()}</h1>
				<p>{m.setup_login_desc()}</p>
				<div class="adm-row">
					<Button variant="primary" href="/admin/login?next=/setup">{m.setup_login()}</Button>
				</div>
			</div>
		{:else if finished}
			<div class="card surface-raised notice">
				<Wand size={36} aria-hidden="true" />
				<h1>{m.setup_already_title()}</h1>
				<p>{m.setup_already_desc()}</p>
				<div class="adm-row">
					<Button variant="primary" href="/admin">{m.setup_done_admin()}</Button>
					<Button href="/" data-sveltekit-reload>{m.setup_done_map()}</Button>
					<Button variant="ghost" onclick={() => (review = true)}>{m.setup_review()}</Button>
				</div>
			</div>
		{:else}
			<h1 class="sr-only">{m.setup_title()}</h1>
			<div class="layout">
				<aside class="side">
					<Stepper {wizard} />
					{#if wizard.access === 'setup' && wizard.state?.window_closes_at}
						<p class="window adm-muted">
							{m.setup_window_closes({ time: fmt.time(wizard.state.window_closes_at) })}
						</p>
					{/if}
				</aside>
				<div class="card surface-raised">
					{#key wizard.current}
						{#if wizard.current === 'wifi'}
							<StepWifi {wizard} />
						{:else if wizard.current === 'code'}
							<StepCode {wizard} />
						{:else if wizard.current === 'locale'}
							<StepLocale {wizard} />
						{:else if wizard.current === 'admin'}
							<StepAdmin {wizard} />
						{:else if wizard.current === 'site'}
							<StepSite {wizard} />
						{:else if wizard.current === 'radio'}
							<StepRadio {wizard} />
						{:else if wizard.current === 'channel'}
							<StepChannel {wizard} />
						{:else if wizard.current === 'privacy'}
							<StepPrivacy {wizard} />
						{:else if wizard.current === 'tiles'}
							<StepTiles {wizard} />
						{:else if wizard.current === 'cloudflare'}
							<StepCloudflare {wizard} />
						{:else}
							<StepFinish {wizard} />
						{/if}
					{/key}
				</div>
			</div>
		{/if}
	</main>
</div>

<style>
	.setup {
		min-height: 100dvh;
		background: var(--bg);
		display: flex;
		flex-direction: column;
	}

	.top {
		display: flex;
		align-items: center;
		gap: 10px;
		min-height: 60px;
		padding: var(--safe-top) 12px 0 16px;
		border-bottom: 1px solid var(--line);
		background: var(--surface-1);
	}

	.brand {
		display: flex;
		align-items: center;
		gap: 10px;
		font-weight: 700;
	}

	.brand img {
		border-radius: 6px;
	}

	.spacer {
		flex: 1;
	}

	.main {
		flex: 1;
		width: min(1080px, 100%);
		margin: 0 auto;
		padding: 28px 16px 48px;
	}

	.main:focus {
		outline: none;
	}

	.layout {
		display: grid;
		grid-template-columns: 240px minmax(0, 1fr);
		gap: 24px;
		align-items: start;
	}

	.side {
		position: sticky;
		top: 20px;
	}

	.window {
		margin: 14px 10px 0;
		font-size: 0.75rem;
	}

	.card {
		padding: clamp(18px, 3vw, 28px);
		border-radius: var(--r-lg);
		background: var(--surface-1);
		min-width: 0;
	}

	.notice {
		max-width: 620px;
		margin: 0 auto;
		display: flex;
		flex-direction: column;
		gap: 12px;
	}

	.notice h1 {
		margin: 0;
		font-size: 1.5rem;
		font-weight: 650;
	}

	.notice p {
		margin: 0;
		color: var(--text-2);
		line-height: 1.5;
	}

	@media (max-width: 820px) {
		.layout {
			grid-template-columns: 1fr;
			gap: 16px;
		}

		.side {
			position: static;
		}

		.main {
			padding-top: 16px;
		}
	}
</style>
