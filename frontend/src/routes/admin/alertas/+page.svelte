<!--
  Alertas (18.2, 19): reglas (alta, edición, prueba, baja), historial con confirmación y canales
  de notificación (solo administradores). Las reglas se editan con un formulario generado desde
  el JSON Schema de cada tipo.
-->
<script lang="ts">
	import BellRing from '@lucide/svelte/icons/bell-ring';
	import Check from '@lucide/svelte/icons/check';
	import Pencil from '@lucide/svelte/icons/pencil';
	import Plus from '@lucide/svelte/icons/plus';
	import RefreshCw from '@lucide/svelte/icons/refresh-cw';
	import Send from '@lucide/svelte/icons/send';
	import Trash2 from '@lucide/svelte/icons/trash-2';
	import { onMount } from 'svelte';
	import * as adminApi from '$lib/admin/api';
	import { notifyChannelLabel, ruleKindLabel } from '$lib/admin/labels';
	import { Busy, Resource } from '$lib/admin/resource.svelte';
	import type { AdminAlertEvent, AlertRule } from '$lib/admin/types';
	import { fmt } from '$lib/i18n/fmt.svelte';
	import { severityLabel } from '$lib/i18n/labels';
	import { m } from '$lib/paraglide/messages';
	import { admin } from '$lib/stores/admin.svelte';
	import { toasts } from '$lib/stores/ui.svelte';
	import { base64UrlToBytes } from '$lib/stores/push.svelte';
	import Button from '$lib/components/ui/Button.svelte';
	import Modal from '$lib/components/ui/Modal.svelte';
	import Segmented from '$lib/components/ui/Segmented.svelte';
	import Skeleton from '$lib/components/ui/Skeleton.svelte';
	import ConfirmAction from '$lib/components/admin/ConfirmAction.svelte';
	import DataTable from '$lib/components/admin/DataTable.svelte';
	import PageHeader from '$lib/components/admin/PageHeader.svelte';
	import Panel from '$lib/components/admin/Panel.svelte';
	import ProblemNote from '$lib/components/admin/ProblemNote.svelte';
	import ChannelsForm from '$lib/components/admin/alerts/ChannelsForm.svelte';
	import RuleForm from '$lib/components/admin/alerts/RuleForm.svelte';
	import type { Column } from '$lib/components/admin/types';

	type Tab = 'rules' | 'events' | 'channels';
	const isAdmin = $derived(admin.session?.role === 'admin');
	let tab = $state<Tab>('rules');

	const rules = new Resource(() => adminApi.alerts.rules());
	const schemas = new Resource(() => adminApi.alerts.rulesSchema());
	const channels = new Resource(() => adminApi.alerts.channels());
	const busy = new Busy();
	let events = $state.raw<AdminAlertEvent[]>([]);
	let eventsNext = $state<string | null>(null);
	let eventsLoading = $state(false);
	let eventsError = $state<unknown>(null);
	let nodeOptions = $state.raw<{ value: string; label: string }[]>([]);
	let connectorIds = $state.raw<string[]>([]);

	let formOpen = $state(false);
	let editing = $state<AlertRule | null>(null);
	let deleting = $state<AlertRule | null>(null);
	let deleteOpen = $state(false);
	let testOut = $state<{ id: number; results: Record<string, string | null> } | null>(null);

	async function loadEvents(more = false): Promise<void> {
		eventsLoading = true;
		try {
			const page = await adminApi.alerts.events(more ? eventsNext : null, 100);
			events = more ? [...events, ...page.events] : page.events;
			eventsNext = page.next;
			eventsError = null;
		} catch (err) {
			eventsError = err;
		} finally {
			eventsLoading = false;
		}
	}

	onMount(() => {
		void rules.load();
		void schemas.load();
		void loadEvents();
		adminApi.nodes
			.list()
			.then((r) => {
				nodeOptions = r.nodes.map((n) => ({
					value: n.id,
					label: n.long_name || n.short_name || n.id
				}));
			})
			.catch(() => {});
		adminApi.connectors
			.list()
			.then((r) => (connectorIds = r.connectors.map((c) => c.id)))
			.catch(() => {});
		const timer = setInterval(() => {
			if (document.visibilityState === 'visible' && tab === 'events') void loadEvents();
		}, 30_000);
		return () => clearInterval(timer);
	});

	$effect(() => {
		if (tab === 'channels' && isAdmin && !channels.data && !channels.loading) void channels.load();
	});

	async function toggleRule(r: AlertRule, enabled: boolean): Promise<void> {
		const out = await busy.run(`e-${r.id}`, () =>
			adminApi.alerts.updateRule(r.id, {
				name: r.name,
				kind: r.kind,
				params: r.params,
				enabled,
				cooldown_s: r.cooldown_s,
				channels: r.channels,
				severity: r.severity,
				is_public: r.is_public
			})
		);
		if (out) void rules.load();
	}

	async function testRule(r: AlertRule): Promise<void> {
		const out = await busy.run(`t-${r.id}`, () => adminApi.alerts.testRule(r.id));
		if (out) testOut = { id: r.id, results: (out.results ?? {}) as Record<string, string | null> };
	}

	async function ack(ev: AdminAlertEvent): Promise<void> {
		const out = await busy.run(`a-${ev.id}`, () => adminApi.alerts.ack(ev.id), {
			success: m.adm_alert_acked()
		});
		if (out)
			events = events.map((x) =>
				x.id === ev.id ? { ...x, ack_by: out.ack_by, ack_at: Date.now() / 1000 } : x
			);
	}

	/** Suscribe este navegador a todas las alertas (suscripción de administración, 19.2). */
	async function subscribeHere(): Promise<void> {
		await busy.run('sub', async () => {
			const key = channels.data?.webpush.public_key;
			if (!key || !('serviceWorker' in navigator) || !('PushManager' in window)) {
				throw new Error(m.adm_push_unsupported());
			}
			const reg = await navigator.serviceWorker.getRegistration();
			if (!reg) throw new Error(m.adm_push_no_sw());
			const permission = await Notification.requestPermission();
			if (permission !== 'granted') throw new Error(m.adm_push_denied());
			const sub = await reg.pushManager.subscribe({
				userVisibleOnly: true,
				applicationServerKey: base64UrlToBytes(key)
			});
			const json = sub.toJSON() as { endpoint?: string; keys?: Record<string, string> };
			await adminApi.alerts.subscribe({
				endpoint: json.endpoint ?? sub.endpoint,
				keys: json.keys ?? {}
			});
			toasts.show(m.adm_push_subscribed(), { kind: 'success' });
			void channels.load();
		});
	}

	const eventColumns: Column<AdminAlertEvent>[] = [
		{ key: 'ts', label: m.adm_when(), width: '150px', text: (e) => fmt.dateTime(e.ts) },
		{ key: 'sev', label: m.adm_severity(), width: '120px', cell: sevCell },
		{ key: 'title', label: m.adm_alert_title(), width: 'minmax(220px, 2fr)', cell: titleCell },
		{
			key: 'kind',
			label: m.adm_rule_kind(),
			width: 'minmax(130px, 1fr)',
			text: (e) => ruleKindLabel(e.kind)
		},
		{
			key: 'state',
			label: m.adm_status(),
			width: '100px',
			text: (e) => (e.state === 'firing' ? m.adm_alert_firing() : m.adm_alert_resolved())
		},
		{ key: 'ack', label: m.adm_alert_ack(), width: '170px', align: 'end', cell: ackCell }
	];
</script>

{#snippet sevCell(e: AdminAlertEvent)}
	<span
		class="adm-badge {e.severity === 'critical'
			? 'danger'
			: e.severity === 'warning'
				? 'warn'
				: ''}">{severityLabel(e.severity)}</span
	>
{/snippet}

{#snippet titleCell(e: AdminAlertEvent)}
	<span class="ev-title" title={e.body ?? ''}>
		<strong>{e.title}</strong>
		{#if e.node}<span class="adm-muted adm-mono"> · {e.node}</span>{/if}
		{#if e.is_public}<span class="adm-badge ok">{m.adm_public_short()}</span>{/if}
	</span>
{/snippet}

{#snippet ackCell(e: AdminAlertEvent)}
	{#if e.ack_at}
		<span class="adm-muted">{m.adm_alert_acked_by({ who: String(e.ack_by ?? '') })}</span>
	{:else}
		<Button size="sm" icon={Check} loading={busy.is(`a-${e.id}`)} onclick={() => ack(e)}
			>{m.adm_alert_ack_action()}</Button
		>
	{/if}
{/snippet}

<PageHeader slug="alertas">
	{#snippet actions()}
		{#if tab === 'rules'}
			<Button
				size="sm"
				variant="primary"
				icon={Plus}
				onclick={() => {
					editing = null;
					formOpen = true;
				}}>{m.adm_rule_add()}</Button
			>
		{:else if tab === 'events'}
			<Button size="sm" icon={RefreshCw} loading={eventsLoading} onclick={() => loadEvents()}
				>{m.adm_reload()}</Button
			>
		{/if}
	{/snippet}
</PageHeader>

<div class="adm-stack">
	<Segmented
		label={m.admin_section_alerts()}
		options={[
			{ value: 'rules', label: m.adm_alert_tab_rules() },
			{ value: 'events', label: m.adm_alert_tab_events() },
			...(isAdmin ? [{ value: 'channels' as Tab, label: m.adm_alert_tab_channels() }] : [])
		]}
		value={tab}
		onchange={(v) => (tab = v)}
	/>

	{#if tab === 'rules'}
		{#if rules.error && !rules.data}
			<ProblemNote error={rules.error} onretry={() => rules.load()} />
		{:else if !rules.data}
			<Skeleton lines={6} label={m.loading()} />
		{:else if rules.data.rules.length === 0}
			<Panel><p class="adm-muted">{m.adm_rules_empty()}</p></Panel>
		{:else}
			<ul class="rules">
				{#each rules.data.rules as r (r.id)}
					<li>
						<Panel title={r.name} description={ruleKindLabel(r.kind)}>
							{#snippet actions()}
								<span
									class="adm-badge {r.severity === 'critical'
										? 'danger'
										: r.severity === 'warning'
											? 'warn'
											: ''}">{severityLabel(r.severity)}</span
								>
								<span class="adm-badge {r.enabled ? 'ok' : ''}"
									>{r.enabled ? m.adm_enabled() : m.adm_disabled()}</span
								>
							{/snippet}
							<div class="adm-stack">
								<p class="adm-muted">
									{m.adm_rule_summary({
										cooldown: fmt.duration(r.cooldown_s),
										channels: r.channels.map(notifyChannelLabel).join(', ') || m.adm_none()
									})}
									{#if r.is_public}· <strong>{m.adm_rule_public_short()}</strong>{/if}
								</p>
								{#if testOut?.id === r.id}
									<ul class="test" role="status">
										{#each Object.entries(testOut.results) as [ch, err] (ch)}
											<li class:fail={err !== null}>
												{notifyChannelLabel(ch)}: {err === null ? m.adm_test_sent() : err}
											</li>
										{:else}
											<li>{m.adm_rule_no_channels()}</li>
										{/each}
									</ul>
								{/if}
								<div class="adm-row">
									<Button
										size="sm"
										icon={Pencil}
										onclick={() => {
											editing = r;
											formOpen = true;
										}}>{m.adm_edit()}</Button
									>
									<Button
										size="sm"
										icon={Send}
										loading={busy.is(`t-${r.id}`)}
										onclick={() => testRule(r)}>{m.adm_test()}</Button
									>
									<Button
										size="sm"
										loading={busy.is(`e-${r.id}`)}
										onclick={() => toggleRule(r, !r.enabled)}
										>{r.enabled ? m.adm_disable() : m.adm_enable()}</Button
									>
									<Button
										size="sm"
										variant="ghost"
										icon={Trash2}
										onclick={() => {
											deleting = r;
											deleteOpen = true;
										}}>{m.adm_delete()}</Button
									>
								</div>
							</div>
						</Panel>
					</li>
				{/each}
			</ul>
		{/if}
	{:else if tab === 'events'}
		<Panel flush>
			{#if eventsError}<div class="pad">
					<ProblemNote error={eventsError} onretry={() => loadEvents()} />
				</div>{/if}
			<DataTable
				rows={events}
				columns={eventColumns}
				rowKey={(e) => e.id}
				label={m.adm_alert_tab_events()}
				rowHeight={52}
				minWidth="900px"
			>
				{#snippet empty()}<p class="adm-muted">{m.adm_no_alerts()}</p>{/snippet}
			</DataTable>
			{#if eventsNext}
				<div class="more">
					<Button size="sm" loading={eventsLoading} onclick={() => loadEvents(true)}
						>{m.adm_load_more()}</Button
					>
				</div>
			{/if}
		</Panel>
	{:else if tab === 'channels'}
		{#if channels.error && !channels.data}
			<ProblemNote error={channels.error} onretry={() => channels.load()} />
		{:else if !channels.data}
			<Skeleton lines={6} label={m.loading()} />
		{:else}
			<Panel title={m.adm_push_here()} description={m.adm_push_here_desc()}>
				<Button icon={BellRing} loading={busy.is('sub')} onclick={subscribeHere}
					>{m.adm_push_here_action()}</Button
				>
			</Panel>
			{#key channels.loadedAt}
				<ChannelsForm data={channels.data} onsaved={() => channels.load()} />
			{/key}
		{/if}
	{/if}
</div>

<Modal
	bind:open={formOpen}
	title={editing ? m.adm_rule_edit({ name: editing.name }) : m.adm_rule_add()}
	size="lg"
>
	{#if formOpen && schemas.error && !schemas.data}
		<ProblemNote error={schemas.error} onretry={() => schemas.load()} />
	{:else if formOpen && !schemas.data}
		<Skeleton lines={5} label={m.loading()} />
	{:else if formOpen && schemas.data}
		<RuleForm
			existing={editing}
			schemas={schemas.data.params}
			nodes={nodeOptions}
			connectors={connectorIds}
			oncancel={() => (formOpen = false)}
			onsaved={() => {
				formOpen = false;
				toasts.show(m.adm_saved(), { kind: 'success' });
				void rules.load();
			}}
		/>
	{/if}
</Modal>

{#if deleting}
	<ConfirmAction
		bind:open={deleteOpen}
		title={m.adm_rule_delete_title({ name: deleting.name })}
		description={m.adm_rule_delete_desc()}
		confirmLabel={m.adm_delete()}
		danger
		action={() => adminApi.alerts.deleteRule(deleting!.id)}
		onsuccess={() => {
			toasts.show(m.adm_deleted(), { kind: 'success' });
			void rules.load();
		}}
	/>
{/if}

<style>
	.rules {
		list-style: none;
		margin: 0;
		padding: 0;
		display: grid;
		grid-template-columns: repeat(auto-fill, minmax(min(100%, 380px), 1fr));
		gap: 16px;
	}

	.test {
		margin: 0;
		padding: 8px 12px;
		list-style: none;
		border-radius: var(--r-sm);
		background: var(--fill-1);
		font-size: 0.8125rem;
	}

	.test li.fail {
		font-weight: 600;
	}

	.ev-title {
		display: inline-flex;
		align-items: center;
		gap: 6px;
		min-width: 0;
		overflow: hidden;
		text-overflow: ellipsis;
	}

	.pad {
		padding: 0 16px 12px;
	}

	.more {
		display: flex;
		justify-content: center;
		padding: 12px;
	}
</style>
