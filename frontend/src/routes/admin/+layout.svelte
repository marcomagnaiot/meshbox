<!--
  Panel de administración (18): superficies sólidas por ser una interfaz densa en datos.
  Sin sesión se va al inicio de sesión; el servidor público responde 404 a /admin.
-->
<script lang="ts">
	import ArrowLeft from '@lucide/svelte/icons/arrow-left';
	import LogOut from '@lucide/svelte/icons/log-out';
	import Menu from '@lucide/svelte/icons/menu';
	import TriangleAlert from '@lucide/svelte/icons/triangle-alert';
	import X from '@lucide/svelte/icons/x';
	import { untrack } from 'svelte';
	import { goto } from '$app/navigation';
	import { page } from '$app/state';
	import { sectionBySlug, visibleSections } from '$lib/admin/sections';
	import { m } from '$lib/paraglide/messages';
	import { admin } from '$lib/stores/admin.svelte';
	import { site } from '$lib/stores/site.svelte';
	import Button from '$lib/components/ui/Button.svelte';
	import IconButton from '$lib/components/ui/IconButton.svelte';
	import Skeleton from '$lib/components/ui/Skeleton.svelte';
	import AppearanceMenu from '$lib/components/shell/AppearanceMenu.svelte';
	import '$lib/components/admin/admin.css';

	let { children } = $props();
	let menuOpen = $state(false);
	let failed = $state(false);

	const isLogin = $derived(page.url.pathname.startsWith('/admin/login'));
	const session = $derived(admin.session);
	const sections = $derived(visibleSections(session?.role, Boolean(session?.tx_enabled)));
	const current = $derived(page.url.pathname.replace(/^\/admin\/?/, '').split('/')[0] ?? '');
	// Acceso directo por URL a una sección de otro rol (o a Transmisión deshabilitada).
	const section = $derived(sectionBySlug(current));
	const allowed = $derived(
		!section ||
			!session ||
			(section.roles.includes(session.role) && (!section.tx || Boolean(session.tx_enabled)))
	);

	// Verificación de la sesión: una sola vez por entrada al panel (sin depender de estados
	// que cambian durante la propia verificación, que la repetirían sin fin).
	let checkStarted = false;
	$effect(() => {
		if (isLogin) {
			checkStarted = false;
			return;
		}
		if (admin.session || checkStarted) return;
		checkStarted = true;
		failed = false;
		const target = page.url.pathname;
		untrack(() => admin.check())
			.then((s) => {
				if (!s) {
					void goto(`/admin/login?next=${encodeURIComponent(target)}`, { replaceState: true });
				}
			})
			.catch(() => (failed = true));
	});

	$effect(() => {
		void page.url.pathname;
		menuOpen = false;
	});
</script>

{#if isLogin}
	{@render children()}
{:else if !session}
	<div class="center">
		{#if failed}
			<p role="alert">{m.error_network()}</p>
			<Button onclick={() => location.reload()}>{m.retry()}</Button>
		{:else}
			<div class="wait"><Skeleton lines={3} label={m.admin_checking()} /></div>
		{/if}
	</div>
{:else}
	<div class="admin" class:menu-open={menuOpen}>
		<header class="bar surface">
			<span class="menu-btn">
				<IconButton
					icon={menuOpen ? X : Menu}
					label={m.admin_menu()}
					aria-expanded={menuOpen}
					aria-controls="admin-nav"
					onclick={() => (menuOpen = !menuOpen)}
				/>
			</span>
			<a href="/admin" class="brand">
				<img src={site.data.logo_url ?? '/favicon.svg'} alt="" width="26" height="26" />
				<span>{m.admin_title()}</span>
			</a>
			<span class="spacer"></span>
			<span class="user">
				{session.username} · {session.role === 'admin'
					? m.admin_role_admin()
					: m.admin_role_operator()}
			</span>
			<AppearanceMenu />
			<IconButton icon={LogOut} label={m.admin_logout()} onclick={() => admin.logout()} />
		</header>

		<nav id="admin-nav" class="nav surface" aria-label={m.admin_menu()}>
			<ul>
				{#each sections as s (s.slug)}
					{@const href = s.slug ? `/admin/${s.slug}` : '/admin'}
					<li>
						<a {href} class="item" aria-current={current === s.slug ? 'page' : undefined}>
							<s.icon size={18} aria-hidden="true" />
							<span>{s.title()}</span>
						</a>
					</li>
				{/each}
			</ul>
			<a class="item back" href="/" data-sveltekit-reload>
				<ArrowLeft size={18} aria-hidden="true" /><span>{m.admin_back_to_site()}</span>
			</a>
		</nav>

		<main id="contenido" class="content" tabindex="-1">
			{#if session.insecure_transport}
				<p class="warn" role="note">
					<TriangleAlert size={16} aria-hidden="true" />{m.admin_insecure()}
				</p>
			{/if}
			{#if session.must_change_password}
				<p class="warn strong" role="alert">
					<TriangleAlert size={16} aria-hidden="true" />{m.admin_must_change()}
				</p>
			{/if}
			{#if allowed}
				{@render children()}
			{:else}
				<div class="denied" role="alert">
					<h1>{section?.title()}</h1>
					<p>
						{section?.tx && session.role === 'admin' ? m.adm_tx_disabled() : m.adm_admins_only()}
					</p>
					<a class="adm-link" href="/admin">{m.adm_back_dashboard()}</a>
				</div>
			{/if}
		</main>
	</div>
{/if}

<style>
	.center {
		min-height: 100dvh;
		display: grid;
		place-items: center;
		gap: 12px;
		padding: 24px;
	}

	.wait {
		width: min(360px, 90vw);
	}

	.admin {
		min-height: 100dvh;
		display: grid;
		grid-template-columns: 260px 1fr;
		grid-template-rows: 60px 1fr;
		grid-template-areas: 'bar bar' 'nav content';
		background: var(--bg);
	}

	.bar {
		grid-area: bar;
		position: sticky;
		top: 0;
		z-index: var(--z-panels);
		display: flex;
		align-items: center;
		gap: 8px;
		padding: 0 8px 0 12px;
		padding-top: var(--safe-top);
		border-width: 0 0 1px;
		background: var(--surface-1);
	}

	.menu-btn {
		display: none;
	}

	.brand {
		display: flex;
		align-items: center;
		gap: 10px;
		min-height: 44px;
		color: var(--text-1);
		text-decoration: none;
		font-weight: 700;
	}

	.brand img {
		border-radius: 6px;
	}

	.spacer {
		flex: 1;
	}

	.user {
		font-size: 0.8125rem;
		color: var(--text-2);
	}

	.nav {
		grid-area: nav;
		position: sticky;
		top: 60px;
		height: calc(100dvh - 60px);
		overflow-y: auto;
		padding: 8px;
		border-width: 0 1px 0 0;
		background: var(--surface-1);
		display: flex;
		flex-direction: column;
	}

	.nav ul {
		list-style: none;
		margin: 0;
		padding: 0;
		display: flex;
		flex-direction: column;
		gap: 2px;
		flex: 1;
	}

	.item {
		display: flex;
		align-items: center;
		gap: 10px;
		min-height: 40px;
		padding: 0 10px;
		border-radius: 8px;
		color: var(--text-1);
		text-decoration: none;
		font-size: 0.875rem;
	}

	.item:hover {
		background: var(--fill-1);
	}

	.item[aria-current='page'] {
		background: var(--accent-soft);
		font-weight: 650;
	}

	.back {
		margin-top: 8px;
		color: var(--text-2);
	}

	.content {
		grid-area: content;
		padding: 24px clamp(16px, 3vw, 40px) 40px;
		min-width: 0;
	}

	.content:focus {
		outline: none;
	}

	.denied {
		max-width: 560px;
	}

	.denied h1 {
		margin: 0 0 8px;
		font-size: 1.375rem;
	}

	.denied p {
		color: var(--text-2);
	}

	.warn {
		display: flex;
		align-items: flex-start;
		gap: 8px;
		margin: 0 0 16px;
		padding: 10px 12px;
		border-radius: var(--r-sm);
		background: var(--warning-soft);
		font-size: 0.8125rem;
	}

	.warn.strong {
		background: var(--danger-soft);
		font-weight: 600;
	}

	@media (max-width: 900px) {
		.admin {
			grid-template-columns: 1fr;
			grid-template-areas: 'bar' 'content';
		}

		.menu-btn {
			display: block;
		}

		.user {
			display: none;
		}

		.nav {
			position: fixed;
			z-index: var(--z-menus);
			top: calc(60px + var(--safe-top));
			left: 0;
			bottom: 0;
			height: auto;
			width: min(300px, 86vw);
			transform: translateX(-105%);
			transition: transform var(--dur-2) var(--ease);
			box-shadow: 0 16px 48px oklch(0% 0 0 / 0.4);
		}

		.menu-open .nav {
			transform: none;
		}
	}
</style>
