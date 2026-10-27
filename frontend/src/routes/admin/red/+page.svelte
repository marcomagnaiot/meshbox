<!--
  Red y sistema (18.2): WiFi, IP, hora y NTP, zona horaria, servicios, métricas internas y
  reinicio o apagado. En un equipo dedicado además se buscan y conectan redes, se olvidan, se
  enciende el punto de acceso y se cambia el nombre del equipo; en uno compartido eso lo
  administra el sistema anfitrión (ADR 0004) y el panel lo explica en vez de ofrecerlo.
-->
<script lang="ts">
	import Power from '@lucide/svelte/icons/power';
	import PowerOff from '@lucide/svelte/icons/power-off';
	import RefreshCw from '@lucide/svelte/icons/refresh-cw';
	import Wifi from '@lucide/svelte/icons/wifi';
	import { onMount } from 'svelte';
	import * as adminApi from '$lib/admin/api';
	import { Busy, Resource } from '$lib/admin/resource.svelte';
	import { snapshotOf, type WifiNetwork } from '$lib/admin/types';
	import { fmt } from '$lib/i18n/fmt.svelte';
	import { m } from '$lib/paraglide/messages';
	import { admin } from '$lib/stores/admin.svelte';
	import { site } from '$lib/stores/site.svelte';
	import { toasts } from '$lib/stores/ui.svelte';
	import Button from '$lib/components/ui/Button.svelte';
	import Modal from '$lib/components/ui/Modal.svelte';
	import Skeleton from '$lib/components/ui/Skeleton.svelte';
	import Toggle from '$lib/components/ui/Toggle.svelte';
	import ConfirmAction from '$lib/components/admin/ConfirmAction.svelte';
	import DataTable from '$lib/components/admin/DataTable.svelte';
	import JobProgress from '$lib/components/admin/JobProgress.svelte';
	import KeyValue from '$lib/components/admin/KeyValue.svelte';
	import PageHeader from '$lib/components/admin/PageHeader.svelte';
	import Panel from '$lib/components/admin/Panel.svelte';
	import ProblemNote from '$lib/components/admin/ProblemNote.svelte';
	import SecretField from '$lib/components/admin/SecretField.svelte';
	import SelectField from '$lib/components/admin/SelectField.svelte';
	import TextField from '$lib/components/admin/TextField.svelte';
	import ServiceList from '$lib/components/admin/system/ServiceList.svelte';
	import type { Column } from '$lib/components/admin/types';

	const HOSTNAME_RE = /^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?$/;

	const net = new Resource(() => adminApi.network.status());
	const sys = new Resource((signal) => adminApi.system.status(signal));
	const metrics = new Resource(() => adminApi.system.metrics(60));
	const busy = new Busy();

	// En un equipo compartido la red, el WiFi y el nombre del equipo son del anfitrión.
	const shared = $derived(
		admin.session?.mode === 'shared' || (net.data !== null && !net.data.managed)
	);

	let scan = $state.raw<WifiNetwork[] | null>(null);
	let scannedAt = $state<number | null>(null);
	let connectTo = $state<WifiNetwork | null>(null);
	let psk = $state('');
	let connectAck = $state(false);
	let connectOpen = $state(false);
	let forgetSsid = $state('');
	let forgetOpen = $state(false);
	let hotspotTarget = $state(false);
	let hotspotOpen = $state(false);
	let hostname = $state('');
	let hostnameOpen = $state(false);
	let tz = $state('');
	let power = $state<'reboot' | 'shutdown'>('reboot');
	let powerOpen = $state(false);
	let wifiTimer: ReturnType<typeof setTimeout> | null = null;

	const zones: string[] = (() => {
		try {
			return Intl.supportedValuesOf('timeZone');
		} catch {
			return [];
		}
	})();

	const zoneOptions = $derived.by(() => {
		const list = zones.includes(tz) || !tz ? zones : [tz, ...zones];
		return list.map((z) => ({ value: z, label: z.replaceAll('_', ' ') }));
	});

	onMount(() => {
		void loadNet();
		void sys.load();
		void metrics.load();
		const stopSys = sys.poll(15_000);
		const stopMetrics = metrics.poll(30_000);
		return () => {
			stopSys();
			stopMetrics();
			sys.dispose();
			metrics.dispose();
			if (wifiTimer) clearTimeout(wifiTimer);
		};
	});

	async function loadNet(): Promise<void> {
		const d = await net.load();
		if (!d) return;
		if (!hostname) hostname = d.system.hostname;
		if (!tz) tz = site.data.timezone || d.time.timezone;
		// Mientras privd cambia de red, se sigue el trabajo.
		if (d.wifi.job?.state === 'running') wifiTimer = setTimeout(() => void loadNet(), 3000);
	}

	async function doScan(): Promise<void> {
		const out = await busy.run('scan', () => adminApi.network.scan());
		if (out) {
			scan = out.networks;
			scannedAt = out.scanned_at;
		}
	}

	async function saveTimezone(): Promise<void> {
		const out = await busy.run('tz', () => adminApi.system.timezone(tz));
		if (!out) return;
		toasts.show(out.system_changed ? m.adm_tz_saved_system() : m.adm_tz_saved_site(), {
			kind: 'success'
		});
		void site.load(true);
		void net.load();
	}

	function openConnect(n: WifiNetwork): void {
		connectTo = n;
		psk = '';
		connectAck = false;
		connectOpen = true;
	}

	async function connect(e: SubmitEvent): Promise<void> {
		e.preventDefault();
		const target = connectTo;
		if (!target || psk.length < 8 || !connectAck) return;
		const out = await busy.run('connect', () => adminApi.network.connect(target.ssid, psk));
		if (!out) return;
		connectOpen = false;
		psk = '';
		toasts.show(m.adm_net_connecting({ ssid: target.ssid }), { kind: 'info', timeout: 12_000 });
		wifiTimer = setTimeout(() => void loadNet(), 2000);
	}

	function wifiState(state: string): string {
		switch (state) {
			case 'connected':
				return m.adm_net_st_connected();
			case 'connecting':
				return m.adm_net_st_connecting();
			case 'disconnected':
				return m.adm_net_st_disconnected();
			case 'unavailable':
				return m.adm_net_st_unavailable();
			case 'unmanaged':
				return m.adm_net_st_unmanaged();
			default:
				return state;
		}
	}

	const subscriberColumns: Column<{ name: string; queued: number; dropped: number }>[] = [
		{ key: 'name', label: m.adm_m_subscriber(), width: 'minmax(160px, 1fr)', text: (s) => s.name },
		{
			key: 'queued',
			label: m.adm_m_queued(),
			width: '110px',
			align: 'end',
			text: (s) => fmt.number(s.queued, 0)
		},
		{
			key: 'dropped',
			label: m.adm_m_dropped(),
			width: '110px',
			align: 'end',
			text: (s) => fmt.number(s.dropped, 0)
		}
	];
</script>

<PageHeader slug="red">
	{#snippet actions()}
		<Button
			size="sm"
			icon={RefreshCw}
			loading={net.loading || sys.loading}
			onclick={() => {
				void loadNet();
				void sys.load();
				void metrics.load();
			}}>{m.adm_reload()}</Button
		>
	{/snippet}
</PageHeader>

<div class="adm-stack">
	{#if shared}
		<p class="adm-note" role="note">{m.adm_shared_explain()}</p>
	{/if}

	{#if net.error && !net.data}
		<ProblemNote error={net.error} onretry={() => loadNet()} />
	{:else if !net.data}
		<Skeleton lines={6} label={m.loading()} />
	{:else}
		{@const w = net.data.wifi}
		{@const s = net.data.system}
		{@const t = net.data.time}
		<div class="adm-grid two">
			<Panel title={m.adm_net_wifi()}>
				<KeyValue
					items={[
						{
							label: m.adm_net_state(),
							value: w.hotspot ? m.adm_net_state_hotspot() : wifiState(w.state)
						},
						{ label: m.adm_net_ssid(), value: w.ssid ?? w.connection },
						{
							label: m.adm_net_signal(),
							value: w.signal === null ? null : fmt.percent(w.signal, 0)
						},
						{ label: m.adm_net_ip(), value: w.ip4.join(', '), mono: true },
						{ label: m.adm_net_lan_ip(), value: net.data.lan_ip, mono: true },
						{ label: m.adm_net_device(), value: w.device, mono: true },
						{ label: m.adm_net_saved(), value: w.saved.map((x) => x.ssid).join(', ') }
					]}
				/>
				{#if w.job && (w.job.state === 'running' || w.job.state === 'failed')}
					<div class="job">
						<JobProgress
							label={m.adm_net_job()}
							state={w.job.state}
							progress={w.job.progress}
							step={w.job.step}
							message={w.job.message}
							error={w.job.state === 'failed' ? (w.job.message ?? w.job.error_code) : null}
						/>
					</div>
				{/if}
				{#if !shared}
					<div class="adm-row actions">
						<Button icon={Wifi} loading={busy.is('scan')} onclick={doScan}
							>{m.adm_net_scan()}</Button
						>
						<Button
							onclick={() => {
								hotspotTarget = !w.hotspot;
								hotspotOpen = true;
							}}>{w.hotspot ? m.adm_net_hotspot_off() : m.adm_net_hotspot_on()}</Button
						>
					</div>
				{/if}
			</Panel>

			<Panel title={m.adm_net_system()}>
				<KeyValue
					items={[
						{ label: m.adm_net_hostname(), value: s.hostname, mono: true },
						{ label: m.adm_net_model(), value: s.model },
						{ label: m.adm_net_os(), value: s.os },
						{ label: m.adm_net_kernel(), value: `${s.kernel} · ${s.arch}` },
						{ label: m.adm_net_uptime(), value: fmt.duration(s.uptime_s) },
						{ label: m.adm_net_python(), value: s.python },
						{ label: m.adm_net_privd(), value: s.privd_version },
						{
							label: m.adm_mode(),
							value: s.mode === 'shared' ? m.adm_mode_shared() : m.adm_mode_appliance()
						}
					]}
				/>
				{#if !shared}
					<form
						class="inline-form"
						onsubmit={(e) => {
							e.preventDefault();
							if (HOSTNAME_RE.test(hostname) && hostname !== s.hostname) hostnameOpen = true;
						}}
					>
						<TextField
							label={m.adm_net_hostname_new()}
							hint={m.adm_net_hostname_hint()}
							bind:value={hostname}
							mono
							maxlength={63}
							autocomplete="off"
							spellcheck={false}
						>
							{#snippet trailing()}
								<Button
									type="submit"
									disabled={!HOSTNAME_RE.test(hostname) || hostname === s.hostname}
									>{m.adm_save()}</Button
								>
							{/snippet}
						</TextField>
					</form>
				{/if}
			</Panel>
		</div>

		{#if scan && !shared}
			<Panel
				title={m.adm_net_networks()}
				description={scannedAt ? m.adm_net_scanned({ time: fmt.time(scannedAt) }) : undefined}
			>
				{#if scan.length === 0}
					<p class="adm-muted">{m.adm_net_no_networks()}</p>
				{:else}
					<ul class="nets">
						{#each scan as n (n.bssid)}
							{@const saved = w.saved.some((x) => x.ssid === n.ssid)}
							<li>
								<span class="ssid">{n.ssid || m.adm_net_hidden_ssid()}</span>
								<span class="adm-muted"
									>{fmt.percent(n.signal, 0)} · {n.security || m.adm_net_open()} · {m.adm_net_channel(
										{
											ch: n.channel
										}
									)}</span
								>
								<span class="net-actions">
									{#if n.in_use}
										<span class="adm-badge ok">{m.adm_net_in_use()}</span>
									{:else if n.ssid}
										<Button size="sm" onclick={() => openConnect(n)}>{m.adm_net_connect()}</Button>
									{/if}
									{#if saved && !n.in_use}
										<Button
											size="sm"
											variant="ghost"
											onclick={() => {
												forgetSsid = n.ssid;
												forgetOpen = true;
											}}>{m.adm_net_forget()}</Button
										>
									{/if}
								</span>
							</li>
						{/each}
					</ul>
				{/if}
			</Panel>
		{/if}

		<Panel title={m.adm_net_time()}>
			<div class="adm-stack">
				<KeyValue
					columns={3}
					items={[
						{ label: m.adm_net_time_now(), value: t.time },
						{
							label: m.adm_ntp(),
							value: t.ntp_synchronized
								? m.adm_net_ntp_ok()
								: t.ntp
									? m.adm_net_ntp_wait()
									: m.adm_net_ntp_off()
						},
						{ label: m.adm_net_tz_system(), value: t.timezone }
					]}
				/>
				{#if !t.ntp_synchronized}
					<p class="adm-note warn">{m.adm_net_ntp_warn()}</p>
				{/if}
				<form
					class="inline-form tz"
					onsubmit={(e) => {
						e.preventDefault();
						void saveTimezone();
					}}
				>
					{#snippet saveTz()}
						<Button type="submit" variant="primary" loading={busy.is('tz')} disabled={!tz}
							>{m.adm_save()}</Button
						>
					{/snippet}
					{#if zoneOptions.length}
						<SelectField
							label={m.adm_net_tz()}
							hint={shared ? m.adm_net_tz_shared() : m.adm_net_tz_hint()}
							bind:value={tz}
							options={zoneOptions}
							trailing={saveTz}
						/>
					{:else}
						<TextField
							label={m.adm_net_tz()}
							hint={shared ? m.adm_net_tz_shared() : m.adm_net_tz_hint()}
							bind:value={tz}
							mono
							trailing={saveTz}
						/>
					{/if}
				</form>
			</div>
		</Panel>
	{/if}

	<Panel title={m.adm_services()}>
		{#if sys.data}
			<ServiceList
				services={Object.values(sys.data.services)}
				canRestart
				onrestarted={() => setTimeout(() => sys.load(), 2000)}
			/>
		{:else if sys.error}
			<ProblemNote error={sys.error} onretry={() => sys.load()} />
		{:else}
			<Skeleton lines={3} label={m.loading()} />
		{/if}
	</Panel>

	{#if metrics.data}
		{@const md = metrics.data}
		{@const snap = snapshotOf(md.system)}
		<Panel title={m.adm_metrics()} description={m.adm_metrics_desc()}>
			<div class="adm-stack">
				{#if snap}
					<KeyValue
						columns={3}
						items={[
							{
								label: m.adm_cpu(),
								value: `${fmt.percent(snap.cpu_system, 0)} · ${m.adm_m_process({ value: fmt.percent(snap.cpu_process, 1) })}`
							},
							{ label: m.adm_m_load(), value: snap.load.map((l) => fmt.number(l, 2)).join(' · ') },
							{ label: m.adm_m_threads(), value: fmt.number(snap.threads, 0) },
							{
								label: m.adm_ram(),
								value: `${fmt.bytes(snap.mem_total - snap.mem_available)} / ${fmt.bytes(snap.mem_total)}`
							},
							{
								label: m.adm_m_rss(),
								value: `${fmt.number(snap.rss_mb, 0)} MB · ${m.adm_m_peak({ value: fmt.number(snap.rss_peak_mb, 0) })}`
							},
							{
								label: m.adm_m_swap(),
								value: `${fmt.bytes(snap.swap_used)} (${fmt.percent(snap.swap_percent, 0)})`
							},
							{
								label: m.adm_temperature(),
								value: snap.temperature === null ? null : fmt.unit(snap.temperature, 'celsius', 1)
							},
							{
								label: m.adm_disk(),
								value: `${fmt.bytes(snap.disk.used)} / ${fmt.bytes(snap.disk.total)}`
							},
							{
								label: m.adm_m_db(),
								value: `${fmt.bytes(snap.db.db)} + WAL ${fmt.bytes(snap.db.db_wal)}`
							},
							{ label: m.adm_m_boot(), value: fmt.dateTime(snap.boot_time) }
						]}
					/>
					<hr class="adm-sep" />
				{/if}
				<KeyValue
					columns={3}
					items={[
						{ label: m.adm_m_writer_queue(), value: fmt.number(md.writer.queue, 0) },
						{ label: m.adm_m_written(), value: fmt.number(md.writer.written_ops, 0) },
						{
							label: m.adm_m_batch(),
							value: m.adm_m_batch_value({
								ms: fmt.number(md.writer.last_batch_ms, 1),
								size: md.writer.last_batch_size
							})
						},
						{
							label: m.adm_m_writer_lost(),
							value: `${fmt.number(md.writer.dropped_ops, 0)} · ${fmt.number(md.writer.failed_ops, 0)}`
						},
						{
							label: m.adm_m_ingest(),
							value: `${fmt.number(md.ingest.queue, 0)} · ${m.adm_m_dropped_n({ count: md.ingest.dropped })}`
						},
						{
							label: m.adm_m_bus(),
							value: `${fmt.number(md.bus.seq, 0)} · ${m.adm_m_dropped_n({ count: md.bus.dropped })}`
						},
						{ label: m.adm_m_dedup(), value: fmt.number(md.dedup_entries, 0) },
						{
							label: m.adm_m_memory_guard(),
							value: m.adm_m_memory_guard_value({
								soft: md.memory_guard.soft_mb,
								hard: md.memory_guard.hard_mb,
								hits: md.memory_guard.soft_hits
							})
						}
					]}
				/>
				{#if md.bus.subscribers?.length}
					<DataTable
						rows={md.bus.subscribers}
						columns={subscriberColumns}
						rowKey={(r) => r.name}
						label={m.adm_m_subscribers()}
						height="auto"
						minWidth="360px"
					/>
				{/if}
			</div>
		</Panel>
	{:else if metrics.error}
		<ProblemNote error={metrics.error} onretry={() => metrics.load()} />
	{/if}

	<Panel
		title={m.adm_power()}
		description={shared ? m.adm_power_shared() : m.adm_power_desc()}
		tone="danger"
	>
		<div class="adm-row">
			<Button
				variant="danger"
				icon={Power}
				onclick={() => {
					power = 'reboot';
					powerOpen = true;
				}}>{m.adm_reboot()}</Button
			>
			<Button
				variant="danger"
				icon={PowerOff}
				onclick={() => {
					power = 'shutdown';
					powerOpen = true;
				}}>{m.adm_shutdown()}</Button
			>
		</div>
	</Panel>
</div>

<Modal
	bind:open={connectOpen}
	title={m.adm_net_connect_title({ ssid: connectTo?.ssid ?? '' })}
	description={m.adm_net_connect_desc()}
>
	<form id="wifi-form" class="adm-stack" onsubmit={connect}>
		<p class="adm-note warn">{m.adm_net_connect_warn()}</p>
		<SecretField
			label={m.adm_net_psk()}
			hint={m.adm_net_psk_hint()}
			bind:value={psk}
			autocomplete="off"
			required
			minlength={8}
			maxlength={63}
		/>
		<Toggle label={m.adm_net_connect_ack()} bind:checked={connectAck} />
	</form>
	{#snippet footer()}
		<Button onclick={() => (connectOpen = false)}>{m.adm_cancel()}</Button>
		<Button
			type="submit"
			form="wifi-form"
			variant="primary"
			loading={busy.is('connect')}
			disabled={psk.length < 8 || !connectAck}>{m.adm_net_connect()}</Button
		>
	{/snippet}
</Modal>

<ConfirmAction
	bind:open={forgetOpen}
	title={m.adm_net_forget_title({ ssid: forgetSsid })}
	description={m.adm_net_forget_desc()}
	confirmLabel={m.adm_net_forget()}
	danger
	action={() => adminApi.network.forget(forgetSsid)}
	onsuccess={() => void loadNet()}
/>

<ConfirmAction
	bind:open={hotspotOpen}
	title={hotspotTarget ? m.adm_net_hotspot_on_title() : m.adm_net_hotspot_off_title()}
	description={hotspotTarget ? m.adm_net_hotspot_on_desc() : m.adm_net_hotspot_off_desc()}
	confirmLabel={hotspotTarget ? m.adm_net_hotspot_on() : m.adm_net_hotspot_off()}
	danger
	action={() => adminApi.network.hotspot(hotspotTarget)}
	onsuccess={(r) => {
		const out = r as { ssid?: string; address?: string };
		if (hotspotTarget && out.ssid) {
			toasts.show(m.adm_net_hotspot_started({ ssid: out.ssid, address: out.address ?? '' }), {
				kind: 'info',
				timeout: 15_000
			});
		}
		wifiTimer = setTimeout(() => void loadNet(), 2000);
	}}
/>

<ConfirmAction
	bind:open={hostnameOpen}
	title={m.adm_net_hostname_title({ name: hostname })}
	description={m.adm_net_hostname_desc()}
	confirmLabel={m.adm_save()}
	action={() => adminApi.system.hostname(hostname)}
	onsuccess={() => {
		toasts.show(m.adm_saved(), { kind: 'success' });
		void loadNet();
	}}
/>

<ConfirmAction
	bind:open={powerOpen}
	title={power === 'reboot' ? m.adm_reboot_title() : m.adm_shutdown_title()}
	description={(power === 'reboot' ? m.adm_reboot_desc() : m.adm_shutdown_desc()) +
		(shared ? ` ${m.adm_power_shared()}` : '')}
	confirmLabel={power === 'reboot' ? m.adm_reboot() : m.adm_shutdown()}
	danger
	requireText={power === 'reboot' ? m.adm_reboot_word() : m.adm_shutdown_word()}
	action={() => (power === 'reboot' ? adminApi.system.reboot() : adminApi.system.shutdown())}
	onsuccess={() =>
		toasts.show(power === 'reboot' ? m.adm_reboot_done() : m.adm_shutdown_done(), {
			kind: 'info',
			timeout: 20_000
		})}
/>

<style>
	.actions,
	.job,
	.inline-form {
		margin-top: 14px;
	}

	.tz {
		margin-top: 0;
		max-width: 560px;
	}

	.nets {
		list-style: none;
		margin: 0;
		padding: 0;
		display: flex;
		flex-direction: column;
		gap: 8px;
	}

	.nets li {
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		gap: 6px 14px;
		padding-bottom: 8px;
		border-bottom: 1px solid var(--line);
	}

	.nets li:last-child {
		border-bottom: 0;
		padding-bottom: 0;
	}

	.ssid {
		font-weight: 650;
		min-width: 160px;
	}

	.net-actions {
		margin-left: auto;
		display: inline-flex;
		align-items: center;
		gap: 8px;
	}
</style>
