<!--
  Broker MQTT (14, 18.2): cuentas por propósito con contraseña generada que se ve una sola vez,
  rotar, borrar, ACL vigente, comandos para el Heltec y salida de eventos (integraciones).
-->
<script lang="ts">
	import KeyRound from '@lucide/svelte/icons/key-round';
	import Plus from '@lucide/svelte/icons/plus';
	import RefreshCw from '@lucide/svelte/icons/refresh-cw';
	import Trash2 from '@lucide/svelte/icons/trash-2';
	import { onMount } from 'svelte';
	import * as adminApi from '$lib/admin/api';
	import { problemFields, problemText } from '$lib/admin/errors';
	import { purposeLabel } from '$lib/admin/labels';
	import { Busy, Resource } from '$lib/admin/resource.svelte';
	import type { MqttAccount, MqttSecret } from '$lib/admin/types';
	import { fmt } from '$lib/i18n/fmt.svelte';
	import { m } from '$lib/paraglide/messages';
	import { toasts } from '$lib/stores/ui.svelte';
	import Button from '$lib/components/ui/Button.svelte';
	import Modal from '$lib/components/ui/Modal.svelte';
	import Skeleton from '$lib/components/ui/Skeleton.svelte';
	import Toggle from '$lib/components/ui/Toggle.svelte';
	import ConfirmAction from '$lib/components/admin/ConfirmAction.svelte';
	import CopyBlock from '$lib/components/admin/CopyBlock.svelte';
	import DataTable from '$lib/components/admin/DataTable.svelte';
	import KeyValue from '$lib/components/admin/KeyValue.svelte';
	import MqttSecretView from '$lib/components/admin/radio/MqttSecretView.svelte';
	import PageHeader from '$lib/components/admin/PageHeader.svelte';
	import Panel from '$lib/components/admin/Panel.svelte';
	import ProblemNote from '$lib/components/admin/ProblemNote.svelte';
	import SelectField from '$lib/components/admin/SelectField.svelte';
	import StatusPill from '$lib/components/admin/StatusPill.svelte';
	import TextField from '$lib/components/admin/TextField.svelte';
	import type { Column } from '$lib/components/admin/types';

	const accounts = new Resource(() => adminApi.mqtt.accounts());
	const status = new Resource(() => adminApi.mqtt.status());
	const acl = new Resource(() => adminApi.mqtt.acl());
	const busy = new Busy();

	let createOpen = $state(false);
	let name = $state('');
	let purpose = $state<'gateway' | 'integration' | 'debug'>('gateway');
	let note = $state('');
	let serialPort = $state('COM5');
	let creating = $state(false);
	let errors = $state<Record<string, string>>({});
	let formError = $state<string | null>(null);
	let secret = $state<MqttSecret | null>(null);
	let secretOpen = $state(false);
	let rotating = $state<MqttAccount | null>(null);
	let rotateOpen = $state(false);
	let deleting = $state<MqttAccount | null>(null);
	let deleteOpen = $state(false);
	let outEnabled = $state(false);
	let outPrefix = $state('meshbox/events');
	let outLoaded = false;

	onMount(() => {
		void accounts.load();
		void acl.load();
		void status.load().then((s) => {
			if (s?.mqtt_out && !outLoaded) {
				outEnabled = s.mqtt_out.enabled;
				outPrefix = s.mqtt_out.prefix;
				outLoaded = true;
			}
		});
		const stop = status.poll(15_000);
		return () => stop();
	});

	const prefixFor = $derived(
		purpose === 'gateway' ? 'gw-' : purpose === 'integration' ? 'int-' : 'dbg-'
	);

	async function create(e: Event): Promise<void> {
		e.preventDefault();
		errors = {};
		if (!/^[a-z0-9][a-z0-9_-]+$/.test(name) || name.length < 2 || name.length > 28) {
			errors = { name: m.adm_mqtt_name_invalid() };
			return;
		}
		creating = true;
		formError = null;
		try {
			secret = await adminApi.mqtt.create({
				name,
				purpose,
				note: note.trim() || null,
				serial_port: serialPort || 'COM5'
			});
			createOpen = false;
			secretOpen = true;
			name = '';
			note = '';
			void accounts.load();
			void acl.load();
		} catch (err) {
			errors = problemFields(err);
			formError = problemText(err);
		} finally {
			creating = false;
		}
	}

	async function saveOut(): Promise<void> {
		const out = await busy.run('out', () => adminApi.mqtt.out(outEnabled, outPrefix.trim()), {
			success: m.adm_saved()
		});
		if (out !== undefined) void status.load();
	}

	const columns: Column<MqttAccount>[] = [
		{ key: 'user', label: m.adm_mqtt_user(), width: 'minmax(160px, 1fr)', cell: userCell },
		{
			key: 'purpose',
			label: m.adm_mqtt_purpose(),
			width: 'minmax(140px, 1fr)',
			text: (a) => purposeLabel(a.purpose)
		},
		{
			key: 'created',
			label: m.adm_created(),
			width: '150px',
			text: (a) => fmt.dateTime(a.created_at)
		},
		{ key: 'note', label: m.adm_note(), width: 'minmax(140px, 1.5fr)', text: (a) => a.note ?? '' },
		{ key: 'act', label: m.adm_actions(), width: '300px', align: 'end', cell: actionsCell }
	];
</script>

{#snippet userCell(a: MqttAccount)}
	<span class="adm-mono">{a.username}</span>
{/snippet}

{#snippet actionsCell(a: MqttAccount)}
	<span class="adm-row">
		<Button
			size="sm"
			icon={KeyRound}
			onclick={() => {
				rotating = a;
				rotateOpen = true;
			}}>{m.adm_mqtt_rotate()}</Button
		>
		{#if a.purpose !== 'ingest'}
			<Button
				size="sm"
				variant="ghost"
				icon={Trash2}
				aria-label="{m.adm_delete()} {a.username}"
				onclick={() => {
					deleting = a;
					deleteOpen = true;
				}}>{m.adm_delete()}</Button
			>
		{/if}
	</span>
{/snippet}

<PageHeader slug="mqtt">
	{#snippet actions()}
		<Button
			size="sm"
			icon={RefreshCw}
			loading={accounts.loading}
			onclick={() => {
				void accounts.load();
				void status.load();
				void acl.load();
			}}>{m.adm_reload()}</Button
		>
		<Button size="sm" variant="primary" icon={Plus} onclick={() => (createOpen = true)}
			>{m.adm_mqtt_create()}</Button
		>
	{/snippet}
</PageHeader>

<div class="adm-stack">
	<div class="adm-grid two">
		<Panel title={m.adm_mqtt_broker()}>
			{#if status.error && !status.data}
				<ProblemNote error={status.error} onretry={() => status.load()} />
			{:else if !status.data}
				<Skeleton lines={3} label={m.loading()} />
			{:else}
				<KeyValue
					items={[
						{
							label: m.adm_status(),
							content: brokerState
						},
						{
							label: m.adm_mqtt_address(),
							value: `${status.data.lan_ip}:${status.data.port}`,
							mono: true
						},
						{
							label: m.adm_mqtt_root(),
							value: accounts.data?.root ?? '',
							mono: true
						},
						{
							label: m.adm_mqtt_acl_file(),
							value: status.data.broker.acl_present ? m.adm_yes() : m.adm_no()
						}
					]}
				/>
				{#if status.data.broker.error}
					<p class="adm-note danger">{status.data.broker.error}</p>
				{/if}
			{/if}
		</Panel>

		<Panel title={m.adm_mqtt_out()} description={m.adm_mqtt_out_desc()}>
			<div class="adm-stack">
				<Toggle label={m.adm_mqtt_out_enable()} bind:checked={outEnabled} />
				<TextField label={m.adm_mqtt_out_prefix()} bind:value={outPrefix} mono maxlength={64} />
				{#if status.data?.mqtt_out}
					{@const o = status.data.mqtt_out}
					<p class="adm-muted">
						{o.connected ? m.adm_cstate_connected() : m.adm_cstate_disconnected()} ·
						{m.adm_mqtt_published({ count: o.published })} · {m.adm_mqtt_dropped({
							count: o.dropped
						})}
						{#if o.last_error}· {o.last_error}{/if}
					</p>
				{/if}
				<div class="adm-row end">
					<Button size="sm" variant="primary" loading={busy.is('out')} onclick={saveOut}
						>{m.adm_save()}</Button
					>
				</div>
			</div>
		</Panel>
	</div>

	<Panel title={m.adm_mqtt_accounts()} description={m.adm_mqtt_accounts_desc()} flush>
		{#if accounts.error && !accounts.data}
			<div class="pad"><ProblemNote error={accounts.error} onretry={() => accounts.load()} /></div>
		{:else if !accounts.data}
			<div class="pad"><Skeleton lines={3} label={m.loading()} /></div>
		{:else}
			<DataTable
				rows={accounts.data.accounts}
				{columns}
				rowKey={(a) => a.username}
				label={m.adm_mqtt_accounts()}
				height="auto"
				rowHeight={56}
				minWidth="860px"
			>
				{#snippet empty()}<p class="adm-muted">{m.adm_mqtt_no_accounts()}</p>{/snippet}
			</DataTable>
		{/if}
	</Panel>

	<Panel title={m.adm_mqtt_acl()} description={m.adm_mqtt_acl_desc()}>
		{#if acl.data}
			<CopyBlock text={acl.data.acl} label={m.adm_mqtt_acl()} />
		{:else if acl.error}
			<ProblemNote error={acl.error} onretry={() => acl.load()} />
		{:else}
			<Skeleton lines={4} label={m.loading()} />
		{/if}
	</Panel>

	<p class="adm-muted">
		{m.adm_mqtt_monitor_hint()}
		<a class="adm-link" href="/admin/paquetes">{m.admin_section_packets()}</a>
	</p>
</div>

{#snippet brokerState()}
	<StatusPill
		active={status.data?.broker.active ?? null}
		state={status.data?.broker.state ?? null}
	/>
{/snippet}

<Modal bind:open={createOpen} title={m.adm_mqtt_create()}>
	<form id="mqtt-form" class="adm-stack" onsubmit={create} novalidate>
		<SelectField
			label={m.adm_mqtt_purpose()}
			bind:value={purpose}
			options={[
				{ value: 'gateway', label: purposeLabel('gateway') },
				{ value: 'integration', label: purposeLabel('integration') },
				{ value: 'debug', label: purposeLabel('debug') }
			]}
			hint={purpose === 'gateway'
				? m.adm_mqtt_purpose_gateway_hint()
				: purpose === 'integration'
					? m.adm_mqtt_purpose_integration_hint()
					: m.adm_mqtt_purpose_debug_hint()}
		/>
		<TextField
			label={m.adm_name()}
			hint={m.adm_mqtt_name_hint({ username: `${prefixFor}${name || 'nombre'}` })}
			bind:value={name}
			required
			maxlength={28}
			error={errors.name}
			mono
			autocomplete="off"
		/>
		<TextField label={m.adm_note()} bind:value={note} maxlength={200} />
		{#if purpose === 'gateway'}
			<TextField
				label={m.adm_mqtt_serial()}
				hint={m.adm_mqtt_serial_hint()}
				bind:value={serialPort}
				maxlength={40}
				mono
			/>
		{/if}
		{#if formError}<p class="adm-note danger" role="alert">{formError}</p>{/if}
	</form>
	{#snippet footer()}
		<Button onclick={() => (createOpen = false)}>{m.adm_cancel()}</Button>
		<Button type="submit" form="mqtt-form" variant="primary" loading={creating}
			>{m.adm_create()}</Button
		>
	{/snippet}
</Modal>

<Modal
	bind:open={secretOpen}
	title={m.adm_mqtt_secret_title({ username: secret?.username ?? '' })}
	size="lg"
>
	{#if secret}
		<MqttSecretView {secret} />
	{/if}
	{#snippet footer()}
		<Button variant="primary" onclick={() => (secretOpen = false)}
			>{m.adm_mqtt_secret_done()}</Button
		>
	{/snippet}
</Modal>

{#if rotating}
	<ConfirmAction
		bind:open={rotateOpen}
		title={m.adm_mqtt_rotate_title({ username: rotating.username })}
		description={rotating.purpose === 'ingest'
			? m.adm_mqtt_rotate_ingest()
			: m.adm_mqtt_rotate_desc()}
		confirmLabel={m.adm_mqtt_rotate()}
		action={() => adminApi.mqtt.rotate(rotating!.username, serialPort || 'COM5')}
		onsuccess={(r) => {
			secret = r as MqttSecret;
			secretOpen = true;
		}}
	/>
{/if}

{#if deleting}
	<ConfirmAction
		bind:open={deleteOpen}
		title={m.adm_mqtt_delete_title({ username: deleting.username })}
		description={m.adm_mqtt_delete_desc()}
		confirmLabel={m.adm_delete()}
		danger
		action={() => adminApi.mqtt.remove(deleting!.username)}
		onsuccess={() => {
			toasts.show(m.adm_deleted(), { kind: 'success' });
			void accounts.load();
			void acl.load();
		}}
	/>
{/if}

<style>
	.pad {
		padding: 0 16px 16px;
	}
</style>
