<!--
  Usuarios (18.2): altas y bajas, roles, contraseñas, sesiones activas con cierre remoto,
  auditoría y cambio de la propia contraseña.
-->
<script lang="ts">
	import KeyRound from '@lucide/svelte/icons/key-round';
	import LogOut from '@lucide/svelte/icons/log-out';
	import Pencil from '@lucide/svelte/icons/pencil';
	import Plus from '@lucide/svelte/icons/plus';
	import Trash2 from '@lucide/svelte/icons/trash-2';
	import { onMount } from 'svelte';
	import * as adminApi from '$lib/admin/api';
	import { problemFields, problemText } from '$lib/admin/errors';
	import { Resource } from '$lib/admin/resource.svelte';
	import type { AdminSessionRow, AdminUser, AuditEntry } from '$lib/admin/types';
	import { adminApi as authApi } from '$lib/api/admin';
	import { fmt } from '$lib/i18n/fmt.svelte';
	import { m } from '$lib/paraglide/messages';
	import { admin } from '$lib/stores/admin.svelte';
	import { toasts } from '$lib/stores/ui.svelte';
	import Button from '$lib/components/ui/Button.svelte';
	import Modal from '$lib/components/ui/Modal.svelte';
	import Segmented from '$lib/components/ui/Segmented.svelte';
	import Skeleton from '$lib/components/ui/Skeleton.svelte';
	import Toggle from '$lib/components/ui/Toggle.svelte';
	import ConfirmAction from '$lib/components/admin/ConfirmAction.svelte';
	import DataTable from '$lib/components/admin/DataTable.svelte';
	import PageHeader from '$lib/components/admin/PageHeader.svelte';
	import Panel from '$lib/components/admin/Panel.svelte';
	import ProblemNote from '$lib/components/admin/ProblemNote.svelte';
	import SecretField from '$lib/components/admin/SecretField.svelte';
	import SelectField from '$lib/components/admin/SelectField.svelte';
	import TextField from '$lib/components/admin/TextField.svelte';
	import type { Column } from '$lib/components/admin/types';

	type Tab = 'users' | 'sessions' | 'audit' | 'me';
	let tab = $state<Tab>('users');
	const users = new Resource(() => adminApi.users.list());
	const sessions = new Resource(() => adminApi.users.sessions());
	let audit = $state.raw<AuditEntry[]>([]);
	let auditNext = $state<number | null>(null);
	let auditLoading = $state(false);
	let auditError = $state<unknown>(null);
	let auditAction = $state('');

	// Alta y edición
	let formOpen = $state(false);
	let editing = $state<AdminUser | null>(null);
	let username = $state('');
	let password = $state('');
	let role = $state<'admin' | 'operator'>('operator');
	let disabled = $state(false);
	let mustChange = $state(true);
	let saving = $state(false);
	let errors = $state<Record<string, string>>({});
	let formError = $state<string | null>(null);
	let deleting = $state<AdminUser | null>(null);
	let deleteOpen = $state(false);
	let closing = $state<AdminSessionRow | null>(null);
	let closeOpen = $state(false);

	// Contraseña propia
	let current = $state('');
	let next = $state('');
	let repeat = $state('');
	let pwBusy = $state(false);
	let pwError = $state<string | null>(null);

	const me = $derived(admin.session?.user_id);

	onMount(() => {
		void users.load();
		if (admin.session?.must_change_password) tab = 'me';
	});

	$effect(() => {
		if (tab === 'sessions' && !sessions.data && !sessions.loading) void sessions.load();
		if (tab === 'audit' && audit.length === 0 && !auditLoading && !auditError) void loadAudit();
	});

	async function loadAudit(more = false): Promise<void> {
		auditLoading = true;
		try {
			const page = await adminApi.users.audit(
				more ? auditNext : null,
				auditAction.trim() || undefined,
				200
			);
			audit = more ? [...audit, ...page.entries] : page.entries;
			auditNext = page.next;
			auditError = null;
		} catch (err) {
			auditError = err;
		} finally {
			auditLoading = false;
		}
	}

	function openForm(u: AdminUser | null): void {
		editing = u;
		username = u?.username ?? '';
		password = '';
		role = u?.role ?? 'operator';
		disabled = u?.disabled ?? false;
		mustChange = u ? u.must_change_password : true;
		errors = {};
		formError = null;
		formOpen = true;
	}

	async function save(e: Event): Promise<void> {
		e.preventDefault();
		const errs: Record<string, string> = {};
		if (!editing && (username.trim().length < 3 || username.trim().length > 32))
			errs.username = m.adm_user_name_invalid();
		if ((!editing || password) && password.length < 8) errs.password = m.adm_min_length({ min: 8 });
		errors = errs;
		if (Object.keys(errs).length) return;
		saving = true;
		formError = null;
		try {
			if (editing) {
				await adminApi.users.update(editing.id, {
					role,
					disabled,
					password: password || null,
					must_change_password: mustChange
				});
			} else {
				await adminApi.users.create({
					username: username.trim(),
					password,
					role,
					must_change_password: mustChange
				});
			}
			toasts.show(m.adm_saved(), { kind: 'success' });
			formOpen = false;
			void users.load();
		} catch (err) {
			errors = problemFields(err);
			formError = problemText(err);
		} finally {
			saving = false;
		}
	}

	async function changeOwn(e: Event): Promise<void> {
		e.preventDefault();
		pwError = null;
		if (next.length < 8) {
			pwError = m.adm_min_length({ min: 8 });
			return;
		}
		if (next !== repeat) {
			pwError = m.adm_pw_mismatch();
			return;
		}
		pwBusy = true;
		try {
			await authApi.changePassword(current, next);
			current = next = repeat = '';
			toasts.show(m.adm_pw_changed(), { kind: 'success' });
			await admin.check();
		} catch (err) {
			pwError = problemText(err);
		} finally {
			pwBusy = false;
		}
	}

	const userColumns: Column<AdminUser>[] = [
		{ key: 'name', label: m.admin_username(), width: 'minmax(140px, 1fr)', cell: userCell },
		{
			key: 'role',
			label: m.adm_role(),
			width: '140px',
			text: (u) => (u.role === 'admin' ? m.admin_role_admin() : m.admin_role_operator())
		},
		{ key: 'state', label: m.adm_status(), width: 'minmax(160px, 1fr)', cell: stateCell },
		{
			key: 'login',
			label: m.adm_user_last_login(),
			width: '150px',
			text: (u) => (u.last_login_at ? fmt.relative(u.last_login_at) : m.adm_never())
		},
		{ key: 'created', label: m.adm_created(), width: '150px', text: (u) => fmt.date(u.created_at) },
		{ key: 'act', label: m.adm_actions(), width: '220px', align: 'end', cell: userActions }
	];

	const sessionColumns: Column<AdminSessionRow>[] = [
		{ key: 'user', label: m.admin_username(), width: '140px', cell: sessionUser },
		{ key: 'ip', label: m.adm_ip(), width: '130px', text: (s) => s.ip ?? '' },
		{
			key: 'ua',
			label: m.adm_user_agent(),
			width: 'minmax(180px, 2fr)',
			text: (s) => s.user_agent ?? ''
		},
		{
			key: 'seen',
			label: m.adm_last_activity(),
			width: '130px',
			text: (s) => fmt.relative(s.last_seen_at)
		},
		{ key: 'exp', label: m.adm_expires(), width: '150px', text: (s) => fmt.dateTime(s.expires_at) },
		{ key: 'act', label: m.adm_actions(), width: '140px', align: 'end', cell: sessionActions }
	];

	const auditColumns: Column<AuditEntry>[] = [
		{ key: 'ts', label: m.adm_when(), width: '150px', text: (a) => fmt.dateTime(a.ts) },
		{ key: 'user', label: m.admin_username(), width: '120px', text: (a) => a.username ?? '—' },
		{ key: 'action', label: m.adm_audit_action(), width: '180px', cell: actionCell },
		{
			key: 'target',
			label: m.adm_audit_target(),
			width: 'minmax(120px, 1fr)',
			text: (a) => a.target ?? ''
		},
		{
			key: 'details',
			label: m.adm_details(),
			width: 'minmax(200px, 2fr)',
			text: (a) =>
				typeof a.details === 'string' ? a.details : a.details ? JSON.stringify(a.details) : ''
		},
		{ key: 'ip', label: m.adm_ip(), width: '120px', text: (a) => a.ip ?? '' }
	];
</script>

{#snippet userCell(u: AdminUser)}
	<span class="adm-mono">{u.username}{u.id === me ? ` (${m.adm_you()})` : ''}</span>
{/snippet}

{#snippet stateCell(u: AdminUser)}
	<span class="adm-row">
		{#if u.disabled}<span class="adm-badge warn">{m.adm_user_disabled()}</span>{:else}<span
				class="adm-badge ok">{m.adm_enabled()}</span
			>{/if}
		{#if u.must_change_password}<span class="adm-badge">{m.adm_user_must_change()}</span>{/if}
	</span>
{/snippet}

{#snippet userActions(u: AdminUser)}
	<span class="adm-row">
		<Button size="sm" icon={Pencil} onclick={() => openForm(u)}>{m.adm_edit()}</Button>
		{#if u.id !== me}
			<Button
				size="sm"
				variant="ghost"
				icon={Trash2}
				aria-label="{m.adm_delete()} {u.username}"
				onclick={() => {
					deleting = u;
					deleteOpen = true;
				}}>{m.adm_delete()}</Button
			>
		{/if}
	</span>
{/snippet}

{#snippet sessionUser(s: AdminSessionRow)}
	<span class="adm-mono">{s.username}</span>
	{#if s.current}<span class="adm-badge accent">{m.adm_session_current()}</span>{/if}
{/snippet}

{#snippet sessionActions(s: AdminSessionRow)}
	<Button
		size="sm"
		icon={LogOut}
		onclick={() => {
			closing = s;
			closeOpen = true;
		}}>{m.adm_session_close()}</Button
	>
{/snippet}

{#snippet actionCell(a: AuditEntry)}
	<span class="adm-mono">{a.action}</span>
{/snippet}

<PageHeader slug="usuarios">
	{#snippet actions()}
		{#if tab === 'users'}
			<Button size="sm" variant="primary" icon={Plus} onclick={() => openForm(null)}
				>{m.adm_user_add()}</Button
			>
		{/if}
	{/snippet}
</PageHeader>

<div class="adm-stack">
	<Segmented
		label={m.admin_section_users()}
		options={[
			{ value: 'users', label: m.adm_users_tab() },
			{ value: 'sessions', label: m.adm_sessions_tab() },
			{ value: 'audit', label: m.adm_audit_tab() },
			{ value: 'me', label: m.adm_me_tab() }
		]}
		value={tab}
		onchange={(v) => (tab = v)}
	/>

	{#if tab === 'users'}
		<Panel flush>
			{#if users.error && !users.data}
				<div class="pad"><ProblemNote error={users.error} onretry={() => users.load()} /></div>
			{:else if !users.data}
				<div class="pad"><Skeleton lines={4} label={m.loading()} /></div>
			{:else}
				<DataTable
					rows={users.data.users}
					columns={userColumns}
					rowKey={(u) => u.id}
					label={m.adm_users_tab()}
					height="auto"
					rowHeight={56}
					minWidth="980px"
				/>
			{/if}
		</Panel>
	{:else if tab === 'sessions'}
		<Panel flush title={m.adm_sessions_tab()} description={m.adm_sessions_desc()}>
			{#if sessions.error && !sessions.data}
				<div class="pad">
					<ProblemNote error={sessions.error} onretry={() => sessions.load()} />
				</div>
			{:else if !sessions.data}
				<div class="pad"><Skeleton lines={4} label={m.loading()} /></div>
			{:else}
				<DataTable
					rows={sessions.data.sessions}
					columns={sessionColumns}
					rowKey={(s) => s.id}
					label={m.adm_sessions_tab()}
					height="auto"
					rowHeight={52}
					minWidth="920px"
				/>
			{/if}
		</Panel>
	{:else if tab === 'audit'}
		<Panel flush>
			<form
				class="audit-filter"
				onsubmit={(e) => {
					e.preventDefault();
					audit = [];
					void loadAudit();
				}}
			>
				<TextField
					label={m.adm_audit_filter()}
					hint={m.adm_audit_filter_hint()}
					bind:value={auditAction}
					mono
				/>
				<Button type="submit" size="sm">{m.adm_filter()}</Button>
			</form>
			{#if auditError}<div class="pad">
					<ProblemNote error={auditError} onretry={() => loadAudit()} />
				</div>{/if}
			<DataTable
				rows={audit}
				columns={auditColumns}
				rowKey={(a) => a.id}
				label={m.adm_audit_tab()}
				rowHeight={44}
				minWidth="1040px"
			>
				{#snippet empty()}<p class="adm-muted">
						{auditLoading ? m.loading() : m.adm_no_results()}
					</p>{/snippet}
			</DataTable>
			{#if auditNext}
				<div class="more">
					<Button size="sm" loading={auditLoading} onclick={() => loadAudit(true)}
						>{m.adm_load_more()}</Button
					>
				</div>
			{/if}
		</Panel>
	{:else}
		<Panel title={m.adm_pw_title()} description={m.adm_pw_desc()}>
			<form class="adm-stack narrow" onsubmit={changeOwn} novalidate>
				<input
					type="text"
					class="sr-only"
					autocomplete="username"
					value={admin.session?.username ?? ''}
					readonly
					tabindex="-1"
					aria-hidden="true"
				/>
				<SecretField
					label={m.adm_pw_current()}
					bind:value={current}
					required
					autocomplete="current-password"
				/>
				<SecretField
					label={m.adm_pw_new()}
					hint={m.adm_pw_new_hint()}
					bind:value={next}
					required
					autocomplete="new-password"
				/>
				<SecretField
					label={m.adm_pw_repeat()}
					bind:value={repeat}
					required
					autocomplete="new-password"
				/>
				{#if pwError}<p class="adm-note danger" role="alert">{pwError}</p>{/if}
				<div class="adm-row">
					<Button type="submit" variant="primary" icon={KeyRound} loading={pwBusy}
						>{m.adm_pw_change()}</Button
					>
				</div>
			</form>
		</Panel>
	{/if}
</div>

<Modal
	bind:open={formOpen}
	title={editing ? m.adm_user_edit({ name: editing.username }) : m.adm_user_add()}
>
	<form id="user-form" class="adm-stack" onsubmit={save} novalidate>
		{#if !editing}
			<TextField
				label={m.admin_username()}
				bind:value={username}
				required
				maxlength={32}
				error={errors.username}
				autocomplete="off"
				mono
			/>
		{/if}
		<SelectField
			label={m.adm_role()}
			bind:value={role}
			options={[
				{ value: 'operator', label: m.admin_role_operator() },
				{ value: 'admin', label: m.admin_role_admin() }
			]}
			hint={role === 'operator' ? m.adm_role_operator_hint() : m.adm_role_admin_hint()}
		/>
		<SecretField
			label={editing ? m.adm_pw_new() : m.admin_password()}
			hint={editing ? m.adm_user_pw_keep() : m.adm_pw_new_hint()}
			bind:value={password}
			required={!editing}
			error={errors.password}
			autocomplete="new-password"
		/>
		<Toggle label={m.adm_user_must_change_toggle()} bind:checked={mustChange} />
		{#if editing && editing.id !== me}
			<Toggle
				label={m.adm_user_disabled()}
				hint={m.adm_user_disabled_hint()}
				bind:checked={disabled}
			/>
		{/if}
		{#if formError}<p class="adm-note danger" role="alert">{formError}</p>{/if}
	</form>
	{#snippet footer()}
		<Button onclick={() => (formOpen = false)}>{m.adm_cancel()}</Button>
		<Button type="submit" form="user-form" variant="primary" loading={saving}>{m.adm_save()}</Button
		>
	{/snippet}
</Modal>

{#if deleting}
	<ConfirmAction
		bind:open={deleteOpen}
		title={m.adm_user_delete_title({ name: deleting.username })}
		description={m.adm_user_delete_desc()}
		confirmLabel={m.adm_delete()}
		danger
		action={() => adminApi.users.remove(deleting!.id)}
		onsuccess={() => {
			toasts.show(m.adm_deleted(), { kind: 'success' });
			void users.load();
		}}
	/>
{/if}

{#if closing}
	<ConfirmAction
		bind:open={closeOpen}
		title={m.adm_session_close_title({ name: closing.username })}
		description={closing.current ? m.adm_session_close_current() : m.adm_session_close_desc()}
		confirmLabel={m.adm_session_close()}
		danger={closing.current}
		action={() => adminApi.users.closeSession(closing!.id)}
		onsuccess={() => {
			if (closing?.current) void admin.logout();
			else void sessions.load();
		}}
	/>
{/if}

<style>
	.pad {
		padding: 0 16px 16px;
	}

	.audit-filter {
		display: flex;
		flex-wrap: wrap;
		align-items: flex-end;
		gap: 12px;
		padding: 0 16px 12px;
	}

	.narrow {
		max-width: 420px;
	}

	.more {
		display: flex;
		justify-content: center;
		padding: 12px;
	}
</style>
