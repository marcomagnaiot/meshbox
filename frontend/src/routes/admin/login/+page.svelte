<!-- Inicio de sesión del panel: errores RFC 9457, 429 con espera (Retry-After) y redirección a `next`. -->
<script lang="ts">
	import LogIn from '@lucide/svelte/icons/log-in';
	import { onDestroy } from 'svelte';
	import { goto } from '$app/navigation';
	import { page } from '$app/state';
	import { ApiError, NetworkError } from '$lib/api/client';
	import { m } from '$lib/paraglide/messages';
	import { admin } from '$lib/stores/admin.svelte';
	import { site } from '$lib/stores/site.svelte';
	import Button from '$lib/components/ui/Button.svelte';

	let username = $state('');
	let password = $state('');
	let error = $state<string | null>(null);
	let fieldErrors = $state<Record<string, string>>({});
	let busy = $state(false);
	let wait = $state(0);
	let timer: ReturnType<typeof setInterval> | null = null;

	const next = $derived.by(() => {
		const n = page.url.searchParams.get('next');
		// Solo destinos propios: el panel o el asistente de primer uso.
		return n && (n.startsWith('/admin') || n === '/setup') && !n.startsWith('//') ? n : '/admin';
	});

	function countdown(seconds: number) {
		wait = seconds;
		if (timer) clearInterval(timer);
		timer = setInterval(() => {
			wait = Math.max(0, wait - 1);
			if (wait === 0 && timer) {
				clearInterval(timer);
				timer = null;
				error = null;
			}
		}, 1000);
	}

	onDestroy(() => {
		if (timer) clearInterval(timer);
	});

	async function submit(e: SubmitEvent) {
		e.preventDefault();
		error = null;
		fieldErrors = {};
		if (!username.trim() || !password) {
			fieldErrors = {
				...(username.trim() ? {} : { username: m.admin_required() }),
				...(password ? {} : { password: m.admin_required() })
			};
			return;
		}
		busy = true;
		try {
			await admin.login(username.trim(), password);
			password = '';
			await goto(next, { replaceState: true });
		} catch (err) {
			password = '';
			if (err instanceof ApiError) {
				if (err.status === 429) {
					const s = err.retryAfter ?? 30;
					error = m.admin_login_wait({ seconds: s });
					countdown(s);
				} else {
					error = err.problem.detail || err.problem.title;
					fieldErrors = err.fieldErrors;
				}
			} else if (err instanceof NetworkError) {
				error = m.error_network();
			} else {
				error = m.error_generic();
			}
		} finally {
			busy = false;
		}
	}
</script>

<svelte:head><title>{m.admin_login_title()} · {site.data.name}</title></svelte:head>

<main id="contenido" class="login-page">
	<form
		class="login surface-raised"
		onsubmit={submit}
		novalidate
		aria-describedby={error ? 'login-error' : undefined}
	>
		<img src={site.data.logo_url ?? '/favicon.svg'} alt="" width="48" height="48" class="logo" />
		<h1>{m.admin_login_title()}</h1>
		<p class="intro">{m.admin_login_intro()}</p>
		{#if admin.notice === 'expired'}<p class="note" role="status">
				{m.admin_session_expired()}
			</p>{/if}

		<label class="field">
			<span>{m.admin_username()}</span>
			<input
				name="username"
				autocomplete="username"
				autocapitalize="none"
				spellcheck="false"
				bind:value={username}
				aria-invalid={fieldErrors.username ? 'true' : undefined}
				aria-describedby={fieldErrors.username ? 'err-username' : undefined}
			/>
			{#if fieldErrors.username}<span class="ferr" id="err-username">{fieldErrors.username}</span
				>{/if}
		</label>
		<label class="field">
			<span>{m.admin_password()}</span>
			<input
				name="password"
				type="password"
				autocomplete="current-password"
				bind:value={password}
				aria-invalid={fieldErrors.password ? 'true' : undefined}
				aria-describedby={fieldErrors.password ? 'err-password' : undefined}
			/>
			{#if fieldErrors.password}<span class="ferr" id="err-password">{fieldErrors.password}</span
				>{/if}
		</label>

		{#if error}
			<p class="error" id="login-error" role="alert">
				{wait > 0 ? m.admin_login_wait({ seconds: wait }) : error}
			</p>
		{/if}

		<Button type="submit" variant="primary" full icon={LogIn} loading={busy} disabled={wait > 0}>
			{busy ? m.admin_logging_in() : m.admin_login()}
		</Button>
		<a class="back" href="/" data-sveltekit-reload>{m.admin_back_to_site()}</a>
	</form>
</main>

<style>
	.login-page {
		min-height: 100dvh;
		display: grid;
		place-items: center;
		padding: 24px 16px;
		background: var(--bg);
	}

	.login {
		width: min(400px, 100%);
		display: flex;
		flex-direction: column;
		gap: 14px;
		padding: 28px 24px;
		border-radius: var(--r-lg);
		background: var(--surface-1);
	}

	.logo {
		border-radius: 12px;
	}

	h1 {
		margin: 0;
		font-size: 1.5rem;
	}

	.intro,
	.note {
		margin: 0;
		color: var(--text-2);
		font-size: 0.875rem;
	}

	.note {
		color: var(--text-1);
	}

	.field {
		display: flex;
		flex-direction: column;
		gap: 6px;
		font-size: 0.875rem;
		font-weight: 600;
	}

	input {
		height: 44px;
		padding: 0 12px;
		border-radius: var(--r-sm);
		border: 1px solid var(--line-strong);
		background: var(--surface-2);
		color: var(--text-1);
		font: inherit;
		font-weight: 400;
	}

	input[aria-invalid='true'] {
		border-color: var(--danger);
	}

	.ferr {
		font-size: 0.75rem;
		font-weight: 500;
		color: var(--text-1);
	}

	.ferr::before {
		content: '⚠ ';
	}

	.error {
		margin: 0;
		padding: 10px 12px;
		border-radius: var(--r-sm);
		background: var(--danger-soft);
		border: 1px solid color-mix(in oklch, var(--danger) 60%, transparent);
		font-size: 0.875rem;
		font-weight: 600;
	}

	.back {
		align-self: center;
		font-size: 0.8125rem;
		min-height: 32px;
		display: inline-flex;
		align-items: center;
	}
</style>
