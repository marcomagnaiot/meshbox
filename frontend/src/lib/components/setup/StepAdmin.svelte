<!--
  Paso 3 (13.2): usuario y contraseña del administrador. No hay contraseña por defecto. Al
  crearlo, el servidor deja la sesión iniciada y el código de configuración deja de valer.
-->
<script lang="ts">
	import { problemText } from '$lib/admin/errors';
	import type { AdminSession } from '$lib/api/types';
	import { ApiError } from '$lib/api/client';
	import { m } from '$lib/paraglide/messages';
	import type { Wizard } from '$lib/setup/wizard.svelte';
	import { admin } from '$lib/stores/admin.svelte';
	import SecretField from '$lib/components/admin/SecretField.svelte';
	import TextField from '$lib/components/admin/TextField.svelte';
	import StepFrame from './StepFrame.svelte';

	interface Props {
		wizard: Wizard;
	}

	let { wizard }: Props = $props();
	const USER_RE = /^[a-z0-9._-]{3,32}$/;
	let username = $state('admin');
	let password = $state('');
	let repeat = $state('');
	let busy = $state(false);
	let error = $state<string | null>(null);
	let errors = $state<Record<string, string>>({});
	let exists = $state(false);

	function check(): Record<string, string> {
		const out: Record<string, string> = {};
		const user = username.trim().toLowerCase();
		if (!USER_RE.test(user)) out.username = m.setup_admin_user_invalid();
		if (password.length < 8) out.password = m.setup_admin_pw_short();
		else if (user && password.toLowerCase().includes(user)) out.password = m.setup_admin_pw_user();
		else if (new Set(password).size < 5) out.password = m.setup_admin_pw_repetitive();
		if (!out.password && repeat !== password) out.repeat = m.setup_admin_pw_mismatch();
		return out;
	}

	async function submit(): Promise<void> {
		errors = check();
		if (Object.keys(errors).length) return;
		busy = true;
		error = null;
		try {
			const out = await wizard.post<AdminSession & { ok: boolean }>('admin', {
				username: username.trim().toLowerCase(),
				password
			});
			password = repeat = '';
			admin.adopt(out);
			wizard.access = 'session';
			void admin.check();
			wizard.complete('admin');
		} catch (err) {
			if (wizard.handleAuth(err)) return;
			exists = err instanceof ApiError && err.status === 409;
			error = problemText(err);
		} finally {
			busy = false;
		}
	}
</script>

<StepFrame
	title={m.setup_admin_title()}
	description={m.setup_admin_desc()}
	onsubmit={submit}
	onback={wizard.index > 0 ? () => wizard.back() : undefined}
	submitLabel={m.setup_admin_create()}
	{busy}
	{error}
>
	<TextField
		label={m.admin_username()}
		hint={m.setup_admin_user_hint()}
		bind:value={username}
		required
		maxlength={32}
		autocomplete="username"
		autocapitalize="none"
		spellcheck={false}
		mono
		error={errors.username}
	/>
	<SecretField
		label={m.admin_password()}
		hint={m.setup_admin_pw_hint()}
		bind:value={password}
		required
		autocomplete="new-password"
		error={errors.password}
	/>
	<SecretField
		label={m.setup_admin_repeat()}
		bind:value={repeat}
		required
		autocomplete="new-password"
		error={errors.repeat}
	/>
	{#if exists}
		<p class="adm-note">
			{m.setup_admin_exists()}
			<a class="adm-link" href="/admin/login?next=/setup">{m.setup_login()}</a>
		</p>
	{/if}
</StepFrame>
