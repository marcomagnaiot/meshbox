<!--
  Panel (18.2): servicios, recursos del equipo, paquetes por minuto, conectores, gateways,
  clientes en vivo, alertas recientes y versión. Se actualiza solo cada 10 s.
-->
<script lang="ts">
	import RefreshCw from '@lucide/svelte/icons/refresh-cw';
	import { onMount } from 'svelte';
	import * as adminApi from '$lib/admin/api';
	import { Resource } from '$lib/admin/resource.svelte';
	import { connectorActive, connectorKindLabel, connectorStateLabel } from '$lib/admin/labels';
	import { snapshotOf, type ConnectorStatus, type GatewayInfo } from '$lib/admin/types';
	import { fmt } from '$lib/i18n/fmt.svelte';
	import { portLabel, severityLabel } from '$lib/i18n/labels';
	import { m } from '$lib/paraglide/messages';
	import { admin } from '$lib/stores/admin.svelte';
	import Button from '$lib/components/ui/Button.svelte';
	import Skeleton from '$lib/components/ui/Skeleton.svelte';
	import TimeSeriesChart from '$lib/components/ui/TimeSeriesChart.svelte';
	import BarList from '$lib/components/stats/BarList.svelte';
	import DataTable from '$lib/components/admin/DataTable.svelte';
	import KeyValue from '$lib/components/admin/KeyValue.svelte';
	import Meter from '$lib/components/admin/Meter.svelte';
	import PageHeader from '$lib/components/admin/PageHeader.svelte';
	import Panel from '$lib/components/admin/Panel.svelte';
	import ProblemNote from '$lib/components/admin/ProblemNote.svelte';
	import StatusPill from '$lib/components/admin/StatusPill.svelte';
	import ServiceList from '$lib/components/admin/system/ServiceList.svelte';
	import type { Column } from '$lib/components/admin/types';

	const status = new Resource((signal) => adminApi.system.status(signal));
	const isAdmin = $derived(admin.session?.role === 'admin');

	onMount(() => {
		void status.load();
		const stop = status.poll(10_000);
		return () => {
			stop();
			status.dispose();
		};
	});

	const d = $derived(status.data);
	const sys = $derived(snapshotOf(d?.system));
	const services = $derived(d ? Object.values(d.services) : []);
	const ppm = $derived(d?.packets_per_minute ?? []);
	const dbSize = $derived(sys ? sys.db.db + sys.db.db_wal + sys.db.db_shm : null);
	const memUsed = $derived(sys ? sys.mem_total - sys.mem_available : null);
	const portRows = $derived(
		Object.entries(d?.counters.portnums_last_hour ?? {}).map(([k, v]) => ({
			key: k,
			label: portLabel(k),
			value: v
		}))
	);

	const connectorColumns: Column<ConnectorStatus>[] = [
		{ key: 'id', label: m.adm_connector_id(), width: 'minmax(120px, 1fr)', text: (c) => c.id },
		{
			key: 'kind',
			label: m.adm_connector_kind(),
			width: '110px',
			text: (c) => connectorKindLabel(c.kind)
		},
		{ key: 'state', label: m.adm_status(), width: '150px', cell: connectorState },
		{
			key: 'packets',
			label: m.adm_packets(),
			width: '90px',
			align: 'end',
			text: (c) => fmt.number(c.packets, 0)
		},
		{
			key: 'errors',
			label: m.adm_errors(),
			width: '80px',
			align: 'end',
			text: (c) => fmt.number(c.errors + c.invalid, 0)
		},
		{
			key: 'last',
			label: m.adm_last_packet(),
			width: '120px',
			text: (c) => (c.last_packet_at ? fmt.relative(c.last_packet_at) : m.adm_never())
		},
		{
			key: 'error',
			label: m.adm_last_error(),
			width: 'minmax(160px, 2fr)',
			text: (c) => c.last_error ?? ''
		}
	];

	const gatewayColumns: Column<GatewayInfo>[] = [
		{ key: 'id', label: m.adm_gateway(), width: '120px', cell: gatewayId },
		{
			key: 'fw',
			label: m.adm_firmware(),
			width: 'minmax(120px, 1fr)',
			text: (g) => g.firmware_version ?? ''
		},
		{
			key: 'preset',
			label: m.adm_preset(),
			width: 'minmax(120px, 1fr)',
			text: (g) => [g.region, g.modem_preset].filter(Boolean).join(' · ')
		},
		{
			key: 'local',
			label: m.adm_local_nodes(),
			width: '110px',
			align: 'end',
			text: (g) =>
				g.num_online_local_nodes === null ? '' : fmt.number(g.num_online_local_nodes, 0)
		},
		{
			key: 'packets',
			label: m.adm_packets(),
			width: '90px',
			align: 'end',
			text: (g) => fmt.number(g.packets, 0)
		},
		{
			key: 'seen',
			label: m.adm_last_seen(),
			width: '120px',
			text: (g) => fmt.relative(g.last_seen)
		}
	];
</script>

{#snippet connectorState(c: ConnectorStatus)}
	<StatusPill
		active={connectorActive(c.state)}
		state={c.state === 'error' ? 'error' : null}
		label={connectorStateLabel(c.state)}
	/>
{/snippet}

{#snippet gatewayId(g: GatewayInfo)}
	<a class="adm-link adm-mono" href="/n/{encodeURIComponent(g.id)}" data-sveltekit-reload>{g.id}</a>
{/snippet}

<PageHeader slug="">
	{#snippet actions()}
		<Button size="sm" icon={RefreshCw} loading={status.loading} onclick={() => status.load()}
			>{m.adm_reload()}</Button
		>
	{/snippet}
	{#if status.loadedAt}
		<p class="adm-muted updated" aria-live="off">
			{m.adm_last_update({ time: fmt.time(status.loadedAt / 1000, true) })}
		</p>
	{/if}
</PageHeader>

{#if status.error && !d}
	<ProblemNote error={status.error} onretry={() => status.load()} />
{:else if !d}
	<Skeleton lines={6} label={m.loading()} />
{:else}
	<div class="adm-stack">
		{#if status.error}
			<ProblemNote error={status.error} title={m.adm_stale()} onretry={() => status.load()} />
		{/if}

		<div class="adm-grid two">
			<Panel title={m.adm_services()} description={m.adm_services_desc({ mode: d.mode })}>
				<ServiceList
					{services}
					canRestart={isAdmin}
					onrestarted={() => setTimeout(() => status.load(), 2000)}
				/>
			</Panel>

			<Panel title={m.adm_device()}>
				{#if sys}
					<div class="meters">
						<Meter
							label={m.adm_cpu()}
							text={fmt.percent(sys.cpu_system, 0)}
							percent={sys.cpu_system}
							detail={m.adm_cpu_detail({
								process: fmt.percent(sys.cpu_process, 1),
								load: sys.load.map((l) => fmt.number(l, 2)).join(' · ')
							})}
						/>
						<Meter
							label={m.adm_ram()}
							text={fmt.percent(sys.mem_percent, 0)}
							percent={sys.mem_percent}
							detail={m.adm_ram_detail({
								used: fmt.bytes(memUsed),
								total: fmt.bytes(sys.mem_total),
								rss: fmt.number(sys.rss_mb, 0)
							})}
						/>
						<Meter
							label={m.adm_temperature()}
							text={sys.temperature === null ? '—' : fmt.unit(sys.temperature, 'celsius', 0)}
							percent={sys.temperature === null ? null : (sys.temperature / 85) * 100}
							warnAt={(65 / 85) * 100}
							dangerAt={(75 / 85) * 100}
						/>
						<Meter
							label={m.adm_disk()}
							text={fmt.percent(sys.disk.percent, 0)}
							percent={sys.disk.percent}
							detail={m.adm_disk_detail({
								free: fmt.bytes(sys.disk.free),
								db: fmt.bytes(dbSize)
							})}
						/>
					</div>
				{:else}
					<p class="adm-muted">{m.adm_no_metrics()}</p>
				{/if}
			</Panel>
		</div>

		<Panel title={m.adm_ppm()} description={m.adm_ppm_desc()}>
			{#if ppm.length}
				<TimeSeriesChart
					ts={ppm.map((p) => p.t)}
					values={ppm.map((p) => p.n)}
					label={m.adm_ppm()}
					integer
					height={180}
					format={(v) => fmt.number(v, 0)}
				/>
			{/if}
		</Panel>

		<div class="adm-grid two">
			<Panel title={m.adm_overview()}>
				<KeyValue
					items={[
						{ label: m.adm_version(), value: d.version },
						{
							label: m.adm_mode(),
							value: d.mode === 'shared' ? m.adm_mode_shared() : m.adm_mode_appliance()
						},
						{
							label: m.adm_last_packet(),
							value: d.last_packet_at ? fmt.relative(d.last_packet_at) : m.adm_never()
						},
						{
							label: m.adm_live_clients(),
							value: m.adm_live_clients_value({
								public: d.sse_clients.public,
								admin: d.sse_clients.admin
							})
						},
						{
							label: m.adm_nodes(),
							value: m.adm_nodes_value({
								total: d.summary.nodes.total ?? 0,
								active: d.summary.nodes.active ?? 0
							})
						},
						{ label: m.adm_packets_hour(), value: fmt.number(d.summary.packets_last_hour, 0) },
						{
							label: m.adm_channel_util(),
							value: fmt.percent(d.summary.channel_utilization_avg, 1)
						},
						{
							label: m.adm_ntp(),
							value:
								d.ntp_synced === null ? m.adm_unknown() : d.ntp_synced ? m.adm_yes() : m.adm_no()
						},
						{ label: m.adm_privd(), value: d.privd }
					]}
				/>
				{#if d.update?.update_available}
					<p class="adm-note ok update">
						{m.adm_update_available({ version: d.update.latest ?? '' })}
						<a class="adm-link" href="/admin/actualizaciones">{m.admin_section_updates()}</a>
					</p>
				{/if}
			</Panel>

			<Panel title={m.adm_counters()} description={m.adm_counters_desc()}>
				<KeyValue
					items={[
						{ label: m.adm_c_packets(), value: fmt.number(d.counters.packets_total, 0) },
						{ label: m.adm_c_duplicates(), value: fmt.number(d.counters.duplicates_total, 0) },
						{ label: m.adm_c_invalid(), value: fmt.number(d.counters.invalid_total, 0) },
						{ label: m.adm_c_undecryptable(), value: fmt.number(d.counters.undecryptable, 0) },
						{ label: m.adm_c_decode_errors(), value: fmt.number(d.counters.decode_errors, 0) },
						{ label: m.adm_c_hidden(), value: fmt.number(d.counters.hidden_dropped, 0) }
					]}
				/>
			</Panel>
		</div>

		{#if portRows.length}
			<Panel title={m.adm_by_port()}>
				<BarList
					rows={portRows}
					caption={m.adm_by_port()}
					labelHeader={m.adm_port()}
					valueHeader={m.adm_packets()}
					shareHeader={m.adm_share()}
					otherLabel={m.adm_others()}
				/>
			</Panel>
		{/if}

		<Panel title={m.adm_connectors()} flush>
			<DataTable
				rows={d.connectors}
				columns={connectorColumns}
				rowKey={(c) => c.id}
				label={m.adm_connectors()}
				height="auto"
				minWidth="820px"
			>
				{#snippet empty()}<p class="adm-muted">{m.adm_empty()}</p>{/snippet}
			</DataTable>
		</Panel>

		<Panel title={m.adm_gateways()} flush>
			<DataTable
				rows={d.gateways}
				columns={gatewayColumns}
				rowKey={(g) => g.id}
				label={m.adm_gateways()}
				height="auto"
				minWidth="720px"
			>
				{#snippet empty()}<p class="adm-muted">{m.adm_no_gateways()}</p>{/snippet}
			</DataTable>
		</Panel>

		<Panel title={m.adm_recent_alerts()}>
			{#if d.recent_alerts.length}
				<ul class="alerts">
					{#each d.recent_alerts as a (a.id)}
						<li>
							<span
								class="adm-badge {a.severity === 'critical'
									? 'danger'
									: a.severity === 'warning'
										? 'warn'
										: ''}">{severityLabel(a.severity)}</span
							>
							<span class="a-title">{a.title}</span>
							<span class="adm-muted"
								>{fmt.relative(a.ts)} · {a.state === 'firing'
									? m.adm_alert_firing()
									: m.adm_alert_resolved()}</span
							>
						</li>
					{/each}
				</ul>
			{:else}
				<p class="adm-muted">{m.adm_no_alerts()}</p>
			{/if}
		</Panel>
	</div>
{/if}

<style>
	.updated {
		margin: 6px 0 0;
	}

	.meters {
		display: grid;
		grid-template-columns: repeat(auto-fill, minmax(min(100%, 200px), 1fr));
		gap: 18px 24px;
	}

	.update {
		margin-top: 14px;
	}

	.alerts {
		list-style: none;
		margin: 0;
		padding: 0;
		display: flex;
		flex-direction: column;
		gap: 10px;
	}

	.alerts li {
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		gap: 4px 10px;
	}

	.a-title {
		font-weight: 600;
	}
</style>
