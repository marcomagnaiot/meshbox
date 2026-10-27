<!--
  Radio (18.2): conectores MQTT, USB, TCP y reproducción. Alta, edición, baja, reinicio,
  prueba, contadores, último error y grabación a archivo. Por USB: información del nodo en
  solo lectura, reiniciar el nodo y liberar el puerto (18.4).
-->
<script lang="ts">
	import Cpu from '@lucide/svelte/icons/cpu';
	import Circle from '@lucide/svelte/icons/circle';
	import Pencil from '@lucide/svelte/icons/pencil';
	import Plug from '@lucide/svelte/icons/plug';
	import Plus from '@lucide/svelte/icons/plus';
	import Power from '@lucide/svelte/icons/power';
	import RefreshCw from '@lucide/svelte/icons/refresh-cw';
	import RotateCcw from '@lucide/svelte/icons/rotate-ccw';
	import Trash2 from '@lucide/svelte/icons/trash-2';
	import Zap from '@lucide/svelte/icons/zap';
	import { onMount } from 'svelte';
	import * as adminApi from '$lib/admin/api';
	import { connectorActive, connectorKindLabel, connectorStateLabel } from '$lib/admin/labels';
	import { Busy, Resource } from '$lib/admin/resource.svelte';
	import type { ConnectorConfig, ConnectorTest } from '$lib/admin/types';
	import { fmt } from '$lib/i18n/fmt.svelte';
	import { m } from '$lib/paraglide/messages';
	import { admin } from '$lib/stores/admin.svelte';
	import { toasts } from '$lib/stores/ui.svelte';
	import Button from '$lib/components/ui/Button.svelte';
	import Modal from '$lib/components/ui/Modal.svelte';
	import Skeleton from '$lib/components/ui/Skeleton.svelte';
	import ConfirmAction from '$lib/components/admin/ConfirmAction.svelte';
	import JsonView from '$lib/components/admin/JsonView.svelte';
	import KeyValue from '$lib/components/admin/KeyValue.svelte';
	import PageHeader from '$lib/components/admin/PageHeader.svelte';
	import Panel from '$lib/components/admin/Panel.svelte';
	import ProblemNote from '$lib/components/admin/ProblemNote.svelte';
	import SelectField from '$lib/components/admin/SelectField.svelte';
	import StatusPill from '$lib/components/admin/StatusPill.svelte';
	import ConnectorForm from '$lib/components/admin/radio/ConnectorForm.svelte';

	const isAdmin = $derived(admin.session?.role === 'admin');
	const list = new Resource(() => adminApi.connectors.list());
	const extras = new Resource(async () => {
		if (!isAdmin) return { ports: [], recordings: [], root: '' };
		const [ports, recs, acc] = await Promise.all([
			adminApi.connectors.serialPorts().catch(() => ({ ports: [] })),
			adminApi.connectors.recordings().catch(() => ({ files: [] })),
			adminApi.mqtt.accounts().catch(() => null)
		]);
		return { ports: ports.ports, recordings: recs.files, root: acc?.root ?? '' };
	});
	const busy = new Busy();

	let formOpen = $state(false);
	let editing = $state<ConnectorConfig | null>(null);
	let target = $state<ConnectorConfig | null>(null);
	let confirmKind = $state<'delete' | 'reboot' | 'release' | null>(null);
	let confirmOpen = $state(false);
	let testResult = $state<{ id: string; result: ConnectorTest } | null>(null);
	let nodeInfo = $state<{ id: string; data: Record<string, unknown> } | null>(null);
	let nodeOpen = $state(false);
	let recordFor = $state<ConnectorConfig | null>(null);
	let recordOpen = $state(false);
	let recordSeconds = $state<number>(3600);

	onMount(() => {
		void list.load();
		void extras.load();
		const stop = list.poll(10_000);
		return () => {
			stop();
			list.dispose();
		};
	});

	function detail(c: ConnectorConfig): string {
		switch (c.kind) {
			case 'mqtt':
				return `${c.username ? `${c.username}@` : ''}${c.host}:${c.port}${c.tls ? ' (TLS)' : ''}`;
			case 'tcp':
				return `${c.host}:${c.port}`;
			case 'serial':
				return String(c.port ?? '');
			default:
				return `${String(c.file ?? '')
					.split(/[\\/]/)
					.pop()} · ×${c.speed}${c.loop ? ` · ${m.adm_replay_loop()}` : ''}`;
		}
	}

	function ask(kind: 'delete' | 'reboot' | 'release', c: ConnectorConfig): void {
		target = c;
		confirmKind = kind;
		confirmOpen = true;
	}

	async function restart(c: ConnectorConfig): Promise<void> {
		const ok = await busy.run(`r-${c.id}`, () => adminApi.connectors.restart(c.id), {
			success: m.adm_connector_restarted({ id: c.id })
		});
		if (ok) setTimeout(() => list.load(), 1500);
	}

	async function test(c: ConnectorConfig): Promise<void> {
		const result = await busy.run(`t-${c.id}`, () => adminApi.connectors.test(c.id));
		if (result) testResult = { id: c.id, result };
	}

	async function showNode(c: ConnectorConfig): Promise<void> {
		const data = await busy.run(`n-${c.id}`, () => adminApi.connectors.node(c.id));
		if (data) {
			nodeInfo = { id: c.id, data };
			nodeOpen = true;
		}
	}

	async function record(): Promise<void> {
		if (!recordFor) return;
		const id = recordFor.id;
		const out = await busy.run(`rec-${id}`, () => adminApi.connectors.record(id, recordSeconds));
		if (out) {
			toasts.show(m.adm_record_started({ file: out.file, until: fmt.dateTime(out.until) }), {
				kind: 'success',
				timeout: 10000
			});
			recordOpen = false;
			void extras.load();
		}
	}

	function testText(r: ConnectorTest): string {
		if ('error' in r && r.error) return m.adm_test_failed({ error: r.error });
		if ('messages' in r) {
			return m.adm_test_mqtt_ok({
				ms: r.connected_ms,
				messages: r.messages,
				valid: r.valid_envelopes,
				seconds: r.seconds
			});
		}
		if ('node' in r) return m.adm_test_usb_ok();
		if ('file' in r) return r.ok ? m.adm_test_file_ok() : m.adm_test_file_missing();
		return r.ok ? m.adm_test_ok() : m.adm_test_failed({ error: '' });
	}

	const confirmTitle = $derived(
		!target
			? ''
			: confirmKind === 'delete'
				? m.adm_connector_delete_title({ id: target.id })
				: confirmKind === 'reboot'
					? m.adm_node_reboot_title()
					: m.adm_release_title({ id: target.id })
	);
	const confirmDesc = $derived(
		confirmKind === 'delete'
			? m.adm_connector_delete_desc()
			: confirmKind === 'reboot'
				? m.adm_node_reboot_desc()
				: m.adm_release_desc()
	);

	async function runConfirm(): Promise<unknown> {
		if (!target) return;
		if (confirmKind === 'delete') return adminApi.connectors.remove(target.id);
		if (confirmKind === 'reboot') return adminApi.connectors.rebootNode(target.id);
		return adminApi.connectors.release(target.id);
	}
</script>

<PageHeader slug="radio">
	{#snippet actions()}
		<Button size="sm" icon={RefreshCw} loading={list.loading} onclick={() => list.load()}
			>{m.adm_reload()}</Button
		>
		{#if isAdmin}
			<Button
				size="sm"
				variant="primary"
				icon={Plus}
				onclick={() => {
					editing = null;
					formOpen = true;
				}}>{m.adm_connector_add()}</Button
			>
		{/if}
	{/snippet}
</PageHeader>

{#if list.error && !list.data}
	<ProblemNote error={list.error} onretry={() => list.load()} />
{:else if !list.data}
	<Skeleton lines={6} label={m.loading()} />
{:else}
	<div class="adm-stack">
		{#if list.data.connectors.length === 0}
			<Panel><p class="adm-muted">{m.adm_connectors_empty()}</p></Panel>
		{/if}
		{#each list.data.connectors as c (c.id)}
			<Panel title={c.id} description="{connectorKindLabel(c.kind)} · {detail(c)}">
				{#snippet actions()}
					<StatusPill
						active={c.enabled ? connectorActive(c.status.state) : false}
						state={c.status.state === 'error' ? 'error' : null}
						label={c.enabled ? connectorStateLabel(c.status.state) : m.adm_disabled()}
					/>
				{/snippet}
				<div class="adm-stack">
					<KeyValue
						columns={4}
						items={[
							{ label: m.adm_packets(), value: fmt.number(c.status.packets ?? 0, 0) },
							{ label: m.adm_invalid(), value: fmt.number(c.status.invalid ?? 0, 0) },
							{ label: m.adm_errors(), value: fmt.number(c.status.errors ?? 0, 0) },
							{
								label: m.adm_last_packet(),
								value: c.status.last_packet_at
									? fmt.relative(c.status.last_packet_at)
									: m.adm_never()
							}
						]}
					/>
					{#if c.status.last_error}
						<p class="adm-note danger">{m.adm_last_error()}: {c.status.last_error}</p>
					{/if}
					{#if c.kind === 'mqtt' && c.topics?.length}
						<p class="adm-muted adm-mono">{c.topics.join(' · ')}</p>
					{/if}
					{#if testResult?.id === c.id}
						<p class="adm-note {testResult.result.ok ? 'ok' : 'danger'}" role="status">
							{testText(testResult.result)}
						</p>
					{/if}
					{#if isAdmin}
						<div class="adm-row">
							<Button size="sm" icon={Zap} loading={busy.is(`t-${c.id}`)} onclick={() => test(c)}
								>{busy.is(`t-${c.id}`) ? m.adm_testing() : m.adm_test()}</Button
							>
							<Button
								size="sm"
								icon={RotateCcw}
								loading={busy.is(`r-${c.id}`)}
								onclick={() => restart(c)}>{m.adm_restart()}</Button
							>
							<Button
								size="sm"
								icon={Circle}
								onclick={() => {
									recordFor = c;
									recordOpen = true;
								}}>{m.adm_record()}</Button
							>
							<Button
								size="sm"
								icon={Pencil}
								onclick={() => {
									editing = c;
									formOpen = true;
								}}>{m.adm_edit()}</Button
							>
							{#if c.kind === 'serial' || c.kind === 'tcp'}
								<Button
									size="sm"
									icon={Cpu}
									loading={busy.is(`n-${c.id}`)}
									onclick={() => showNode(c)}>{m.adm_node_info()}</Button
								>
							{/if}
							{#if c.kind === 'serial'}
								<Button size="sm" icon={Power} onclick={() => ask('reboot', c)}
									>{m.adm_node_reboot()}</Button
								>
								<Button size="sm" icon={Plug} onclick={() => ask('release', c)}
									>{m.adm_release()}</Button
								>
							{/if}
							<Button size="sm" variant="ghost" icon={Trash2} onclick={() => ask('delete', c)}
								>{m.adm_delete()}</Button
							>
						</div>
					{/if}
				</div>
			</Panel>
		{/each}

		{#if isAdmin && extras.data?.recordings.length}
			<Panel title={m.adm_recordings()} description={m.adm_recordings_desc()}>
				<ul class="files">
					{#each extras.data.recordings as r (r.name)}
						<li>
							<span class="adm-mono">{r.name}</span>
							<span class="adm-muted">{fmt.bytes(r.size)} · {fmt.dateTime(r.mtime)}</span>
						</li>
					{/each}
				</ul>
			</Panel>
		{/if}
	</div>
{/if}

<Modal
	bind:open={formOpen}
	title={editing ? m.adm_connector_edit_title({ id: editing.id }) : m.adm_connector_add()}
	size="lg"
>
	{#if formOpen}
		<ConnectorForm
			existing={editing}
			ports={extras.data?.ports ?? []}
			recordings={extras.data?.recordings ?? []}
			defaultTopic={extras.data?.root ? `${extras.data.root}/2/e/#` : 'msh/AR/…/2/e/#'}
			oncancel={() => (formOpen = false)}
			onsaved={() => {
				formOpen = false;
				toasts.show(m.adm_saved(), { kind: 'success' });
				void list.load();
			}}
		/>
	{/if}
</Modal>

<Modal bind:open={recordOpen} title={m.adm_record_title({ id: recordFor?.id ?? '' })}>
	<div class="adm-stack">
		<p class="adm-muted">{m.adm_record_desc()}</p>
		<SelectField
			label={m.adm_record_duration()}
			bind:value={recordSeconds}
			options={[
				{ value: 600, label: m.adm_minutes({ count: 10 }) },
				{ value: 3600, label: m.adm_hours({ count: 1 }) },
				{ value: 6 * 3600, label: m.adm_hours({ count: 6 }) },
				{ value: 24 * 3600, label: m.adm_hours({ count: 24 }) },
				{ value: 7 * 86400, label: m.adm_days({ count: 7 }) }
			]}
		/>
	</div>
	{#snippet footer()}
		<Button onclick={() => (recordOpen = false)}>{m.adm_cancel()}</Button>
		<Button
			variant="primary"
			icon={Circle}
			loading={busy.is(`rec-${recordFor?.id}`)}
			onclick={record}>{m.adm_record_start()}</Button
		>
	{/snippet}
</Modal>

<Modal bind:open={nodeOpen} title={m.adm_node_info_title({ id: nodeInfo?.id ?? '' })} size="lg">
	{#if nodeInfo}
		<div class="adm-stack">
			<p class="adm-muted">{m.adm_node_info_desc()}</p>
			<KeyValue
				items={[
					{ label: m.adm_gateway(), value: String(nodeInfo.data.gateway_id ?? ''), mono: true },
					{ label: m.adm_nodes_in_db(), value: String(nodeInfo.data.nodes_in_db ?? '') }
				]}
			/>
			<JsonView summary={m.adm_node_my_info()} value={nodeInfo.data.my_info} open />
			<JsonView summary={m.adm_node_metadata()} value={nodeInfo.data.metadata} />
			<JsonView summary={m.adm_node_local_config()} value={nodeInfo.data.local_config} />
			<JsonView summary={m.adm_node_module_config()} value={nodeInfo.data.module_config} />
			<JsonView summary={m.adm_node_channels()} value={nodeInfo.data.channels} />
		</div>
	{/if}
</Modal>

<ConfirmAction
	bind:open={confirmOpen}
	title={confirmTitle}
	description={confirmDesc}
	confirmLabel={confirmKind === 'delete'
		? m.adm_delete()
		: confirmKind === 'reboot'
			? m.adm_node_reboot()
			: m.adm_release()}
	danger={confirmKind !== 'release'}
	action={runConfirm}
	onsuccess={() => {
		toasts.show(confirmKind === 'reboot' ? m.adm_node_reboot_done() : m.adm_saved(), {
			kind: 'success'
		});
		setTimeout(() => list.load(), 1000);
	}}
/>

<style>
	.files {
		list-style: none;
		margin: 0;
		padding: 0;
		display: flex;
		flex-direction: column;
		gap: 8px;
	}

	.files li {
		display: flex;
		flex-wrap: wrap;
		justify-content: space-between;
		gap: 4px 16px;
	}
</style>
