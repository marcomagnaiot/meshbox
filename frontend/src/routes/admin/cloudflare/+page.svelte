<!--
  Cloudflare (15, 18.2): estado del túnel, modo token (se pega el token del túnel), modo API
  (verificar el token, elegir la zona y publicar), administración remota con Access y
  desconexión (con borrado opcional de DNS y túnel).
-->
<script lang="ts">
	import Cloud from '@lucide/svelte/icons/cloud';
	import Globe from '@lucide/svelte/icons/globe';
	import Link2Off from '@lucide/svelte/icons/link-2-off';
	import RefreshCw from '@lucide/svelte/icons/refresh-cw';
	import ShieldCheck from '@lucide/svelte/icons/shield-check';
	import { onMount } from 'svelte';
	import * as adminApi from '$lib/admin/api';
	import { problemText } from '$lib/admin/errors';
	import { Busy, Resource } from '$lib/admin/resource.svelte';
	import type { CloudflareZone, ProvisionStep } from '$lib/admin/types';
	import { ApiError } from '$lib/api/client';
	import { fmt } from '$lib/i18n/fmt.svelte';
	import { m } from '$lib/paraglide/messages';
	import { toasts } from '$lib/stores/ui.svelte';
	import Button from '$lib/components/ui/Button.svelte';
	import Segmented from '$lib/components/ui/Segmented.svelte';
	import Skeleton from '$lib/components/ui/Skeleton.svelte';
	import Toggle from '$lib/components/ui/Toggle.svelte';
	import ConfirmAction from '$lib/components/admin/ConfirmAction.svelte';
	import CopyBlock from '$lib/components/admin/CopyBlock.svelte';
	import KeyValue from '$lib/components/admin/KeyValue.svelte';
	import PageHeader from '$lib/components/admin/PageHeader.svelte';
	import Panel from '$lib/components/admin/Panel.svelte';
	import ProblemNote from '$lib/components/admin/ProblemNote.svelte';
	import SecretField from '$lib/components/admin/SecretField.svelte';
	import SelectField from '$lib/components/admin/SelectField.svelte';
	import StatusPill from '$lib/components/admin/StatusPill.svelte';
	import TagsField from '$lib/components/admin/TagsField.svelte';
	import TextField from '$lib/components/admin/TextField.svelte';

	const status = new Resource(() => adminApi.cloudflare.status(false));
	const busy = new Busy();
	let setupMode = $state<'token' | 'api'>('token');
	// modo token
	let tunnelToken = $state('');
	let tokenHost = $state('');
	let tokenHint = $state<string | null>(null);
	// modo API
	let apiToken = $state('');
	let accountId = $state('');
	let zones = $state.raw<CloudflareZone[]>([]);
	let zoneId = $state('');
	let sub = $state('mesh');
	let adminSub = $state('');
	let replaceDns = $state(false);
	let steps = $state.raw<ProvisionStep[]>([]);
	let provisionError = $state<string | null>(null);
	let restartNote = $state(false);
	// Access
	let emails = $state<string[]>([]);
	let accessNote = $state<string | null>(null);
	// desconexión
	let disconnectOpen = $state(false);
	let deleteDns = $state(false);
	let deleteTunnel = $state(false);
	let doneList = $state<string[]>([]);

	onMount(() => {
		void status.load();
	});

	const d = $derived(status.data);
	const zone = $derived(zones.find((z) => z.id === zoneId) ?? null);
	const publicHost = $derived(zone ? (sub.trim() ? `${sub.trim()}.${zone.name}` : zone.name) : '');
	const adminHost = $derived(zone && adminSub.trim() ? `${adminSub.trim()}.${zone.name}` : '');

	async function probe(): Promise<void> {
		await busy.run('probe', async () => {
			status.data = await adminApi.cloudflare.status(true);
		});
	}

	async function saveToken(e: Event): Promise<void> {
		e.preventDefault();
		const out = await busy.run('token', () =>
			adminApi.cloudflare.token(tunnelToken.trim(), tokenHost.trim().toLowerCase())
		);
		if (out) {
			tunnelToken = '';
			tokenHint = out.hint;
			toasts.show(m.adm_cf_token_saved(), { kind: 'success' });
			void status.load();
		}
	}

	async function verify(e: Event): Promise<void> {
		e.preventDefault();
		const out = await busy.run('verify', () =>
			adminApi.cloudflare.verify(apiToken.trim(), accountId.trim())
		);
		if (out) {
			zones = out.zones;
			zoneId = out.zones[0]?.id ?? '';
			apiToken = '';
			toasts.show(m.adm_cf_verified({ count: out.zones.length }), { kind: 'success' });
			void status.load();
		}
	}

	async function loadZones(): Promise<void> {
		const out = await busy.run('zones', () => adminApi.cloudflare.zones());
		if (out) {
			zones = out.zones;
			zoneId = zoneId || out.zones[0]?.id || '';
		}
	}

	async function provision(e: Event): Promise<void> {
		e.preventDefault();
		if (!zone) return;
		provisionError = null;
		steps = [];
		busy.keys = { ...busy.keys, provision: true };
		try {
			const out = await adminApi.cloudflare.provision({
				zone_id: zone.id,
				public_hostname: publicHost,
				admin_hostname: adminHost,
				replace_dns: replaceDns
			});
			steps = out.steps;
			restartNote = out.restart_needed_for_admin;
			toasts.show(m.adm_cf_published({ host: publicHost }), { kind: 'success' });
			void status.load();
		} catch (err) {
			provisionError = problemText(err);
			if (err instanceof ApiError && Array.isArray(err.problem.steps))
				steps = err.problem.steps as ProvisionStep[];
		} finally {
			const { provision: _p, ...rest } = busy.keys;
			busy.keys = rest;
		}
	}

	async function access(e: Event): Promise<void> {
		e.preventDefault();
		const out = await busy.run('access', () => adminApi.cloudflare.access(emails));
		if (out) {
			accessNote = m.adm_cf_access_done({ team: out.team_domain });
			void status.load();
		}
	}

	function stepText(s: ProvisionStep): string {
		const extra = Object.entries(s)
			.filter(([k]) => k !== 'step')
			.map(([k, v]) => `${k}: ${typeof v === 'object' ? JSON.stringify(v) : String(v)}`)
			.join(' · ');
		return extra ? `${s.step} — ${extra}` : s.step;
	}
</script>

<PageHeader slug="cloudflare">
	{#snippet actions()}
		<Button
			size="sm"
			icon={Globe}
			loading={busy.is('probe')}
			onclick={probe}
			disabled={!d?.public_hostname}>{m.adm_cf_probe()}</Button
		>
		<Button size="sm" icon={RefreshCw} loading={status.loading} onclick={() => status.load()}
			>{m.adm_reload()}</Button
		>
	{/snippet}
</PageHeader>

{#if status.error && !d}
	<ProblemNote error={status.error} onretry={() => status.load()} />
{:else if !d}
	<Skeleton lines={6} label={m.loading()} />
{:else}
	<div class="adm-stack">
		<Panel title={m.adm_cf_status()}>
			<KeyValue
				columns={3}
				items={[
					{
						label: m.adm_cf_mode(),
						value:
							d.mode === 'none'
								? m.adm_cf_mode_none()
								: d.mode === 'token'
									? m.adm_cf_mode_token()
									: m.adm_cf_mode_api()
					},
					{ label: m.adm_cf_public_host(), value: d.public_hostname || '—', mono: true },
					{ label: m.adm_cf_admin_host(), value: d.admin_hostname || '—', mono: true },
					{ label: m.adm_cf_service(), content: serviceState },
					{
						label: m.adm_cf_tunnel(),
						value: d.tunnel
							? (d.tunnel.error ??
								`${d.tunnel.name ?? ''} · ${d.tunnel.status ?? ''} · ${m.adm_cf_connections({ count: d.tunnel.connections ?? 0 })}`)
							: '—'
					},
					{
						label: m.adm_cf_site_check(),
						value: d.site_check
							? d.site_check.ok === null
								? '—'
								: d.site_check.ok
									? m.adm_cf_site_ok({
											when: d.site_check.checked_at ? fmt.time(d.site_check.checked_at) : ''
										})
									: m.adm_cf_site_fail({
											detail: String(d.site_check.status ?? d.site_check.error ?? '')
										})
							: m.adm_cf_site_unchecked()
					},
					{
						label: m.adm_cf_access(),
						value: d.access.configured
							? m.adm_cf_access_on({ team: d.access.team_domain })
							: m.adm_no()
					},
					{ label: m.adm_cf_public_target(), value: d.public_target, mono: true },
					{ label: m.adm_cf_admin_target(), value: d.admin_target, mono: true }
				]}
			/>
		</Panel>

		{#if d.mode === 'none' || d.mode === 'token'}
			<Panel title={m.adm_cf_setup()} description={m.adm_cf_setup_desc()}>
				<div class="adm-stack">
					<Segmented
						label={m.adm_cf_mode()}
						options={[
							{ value: 'token', label: m.adm_cf_mode_token() },
							{ value: 'api', label: m.adm_cf_mode_api() }
						]}
						value={setupMode}
						onchange={(v) => (setupMode = v)}
					/>
					{#if setupMode === 'token'}
						<ol class="steps">
							<li>{m.adm_cf_token_step1()}</li>
							<li>{m.adm_cf_token_step2({ target: d.public_target })}</li>
							<li>{m.adm_cf_token_step3()}</li>
						</ol>
						<form class="adm-stack" onsubmit={saveToken} novalidate>
							<SecretField
								label={m.adm_cf_tunnel_token()}
								hint={m.adm_cf_tunnel_token_hint()}
								bind:value={tunnelToken}
								isSet={Boolean(d.service.token_configured)}
								autocomplete="off"
							/>
							<TextField
								label={m.adm_cf_public_host()}
								hint={m.adm_cf_public_host_hint()}
								bind:value={tokenHost}
								mono
								placeholder="mesh.ejemplo.com"
							/>
							{#if tokenHint}<p class="adm-note ok">{tokenHint}</p>{/if}
							<div class="adm-row">
								<Button
									type="submit"
									variant="primary"
									icon={Cloud}
									loading={busy.is('token')}
									disabled={tunnelToken.trim().length < 50}>{m.adm_cf_token_connect()}</Button
								>
							</div>
						</form>
					{:else}
						<ol class="steps">
							<li>{m.adm_cf_api_step1()}</li>
							<li>{m.adm_cf_api_step2()}</li>
						</ol>
						<form class="adm-stack" onsubmit={verify} novalidate>
							<div class="adm-grid">
								<SecretField
									label={m.adm_cf_api_token()}
									hint={m.adm_cf_api_token_hint()}
									bind:value={apiToken}
									isSet={d.has_api_token}
									autocomplete="off"
								/>
								<TextField
									label={m.adm_cf_account()}
									hint={m.adm_cf_account_hint()}
									bind:value={accountId}
									mono
								/>
							</div>
							<div class="adm-row">
								<Button
									type="submit"
									loading={busy.is('verify')}
									disabled={apiToken.trim().length < 20}>{m.adm_cf_verify()}</Button
								>
								{#if d.has_api_token}
									<Button variant="ghost" loading={busy.is('zones')} onclick={loadZones}
										>{m.adm_cf_use_saved()}</Button
									>
								{/if}
							</div>
						</form>
						{#if zones.length}
							<form class="adm-stack" onsubmit={provision} novalidate>
								<div class="adm-grid">
									<SelectField
										label={m.adm_cf_zone()}
										bind:value={zoneId}
										options={zones.map((z) => ({
											value: z.id,
											label: `${z.name}${z.account_name ? ` (${z.account_name})` : ''}`
										}))}
									/>
									<TextField
										label={m.adm_cf_subdomain()}
										hint={m.adm_cf_subdomain_hint()}
										bind:value={sub}
										mono
									/>
									<TextField
										label={m.adm_cf_admin_sub()}
										hint={m.adm_cf_admin_sub_hint()}
										bind:value={adminSub}
										mono
									/>
								</div>
								<p class="adm-muted">
									{m.adm_cf_will_publish({ host: publicHost || '—' })}{#if adminHost}
										· {m.adm_cf_will_admin({ host: adminHost })}{/if}
								</p>
								<Toggle
									label={m.adm_cf_replace_dns()}
									hint={m.adm_cf_replace_dns_hint()}
									bind:checked={replaceDns}
								/>
								{#if provisionError}<p class="adm-note danger" role="alert">
										{provisionError}
									</p>{/if}
								{#if steps.length}
									<ol class="steps done" aria-label={m.adm_cf_steps()}>
										{#each steps as s, i (i)}<li>{stepText(s)}</li>{/each}
									</ol>
								{/if}
								{#if restartNote}<p class="adm-note warn">{m.adm_cf_restart_admin()}</p>{/if}
								<div class="adm-row">
									<Button
										type="submit"
										variant="primary"
										icon={Cloud}
										loading={busy.is('provision')}
										disabled={!zone}>{m.adm_cf_publish()}</Button
									>
								</div>
							</form>
						{/if}
					{/if}
				</div>
			</Panel>
		{/if}

		{#if d.mode === 'api' && d.admin_hostname}
			<Panel
				title={m.adm_cf_access_title()}
				description={m.adm_cf_access_desc({ host: d.admin_hostname })}
			>
				<form class="adm-stack" onsubmit={access} novalidate>
					<TagsField
						label={m.adm_cf_emails()}
						hint={m.adm_cf_emails_hint()}
						bind:values={emails}
						max={20}
						validate={(v) =>
							/^[^@\s]+@[^@\s]+\.[a-z]{2,}$/i.test(v) ? null : m.adm_cf_email_invalid()}
					/>
					{#if accessNote}<p class="adm-note ok" role="status">{accessNote}</p>{/if}
					<div class="adm-row">
						<Button
							type="submit"
							icon={ShieldCheck}
							loading={busy.is('access')}
							disabled={emails.length === 0}>{m.adm_cf_access_save()}</Button
						>
					</div>
				</form>
			</Panel>
		{/if}

		{#if d.mode !== 'none'}
			<Panel title={m.adm_cf_disconnect()} description={m.adm_cf_disconnect_desc()} tone="danger">
				<div class="adm-stack">
					{#if doneList.length}
						<ul class="steps done" role="status">
							{#each doneList as item, i (i)}<li>{item}</li>{/each}
						</ul>
					{/if}
					<div class="adm-row">
						<Button variant="danger" icon={Link2Off} onclick={() => (disconnectOpen = true)}
							>{m.adm_cf_disconnect()}</Button
						>
					</div>
				</div>
			</Panel>
		{/if}

		{#if d.public_hostname}
			<Panel title={m.adm_cf_public_site()}>
				<CopyBlock text={`https://${d.public_hostname}`} label={m.adm_cf_public_site()} inline />
			</Panel>
		{/if}
	</div>
{/if}

{#snippet serviceState()}
	<StatusPill active={d?.service.active ?? null} state={d?.service.state ?? null} />
	{#if d?.service.token_configured}<span class="adm-muted"> · {m.adm_cf_token_set()}</span>{/if}
{/snippet}

<ConfirmAction
	bind:open={disconnectOpen}
	title={m.adm_cf_disconnect_title()}
	description={m.adm_cf_disconnect_confirm()}
	confirmLabel={m.adm_cf_disconnect()}
	danger
	requireText={d?.public_hostname || 'DESCONECTAR'}
	action={() => adminApi.cloudflare.disconnect(deleteDns, deleteTunnel)}
	onsuccess={(r) => {
		doneList = (r as { done: string[] }).done;
		void status.load();
	}}
>
	{#if d?.mode === 'api'}
		<Toggle label={m.adm_cf_delete_dns()} bind:checked={deleteDns} />
		<Toggle label={m.adm_cf_delete_tunnel()} bind:checked={deleteTunnel} />
	{/if}
</ConfirmAction>

<style>
	.steps {
		margin: 0;
		padding-left: 20px;
		list-style: decimal;
		display: flex;
		flex-direction: column;
		gap: 6px;
		font-size: 0.875rem;
		line-height: 1.45;
	}

	ul.steps {
		list-style: disc;
	}

	.steps.done {
		font-size: 0.8125rem;
		color: var(--text-2);
	}
</style>
