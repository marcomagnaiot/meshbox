<!--
  Estado de la placa: datos del nodo, batería con su historia (telemetría guardada por meshbox),
  tráfico propio (LocalStats), posición fija (fijarla en el mapa, reponerla o quitarla) y
  acciones (nombre, reiniciar, apagar). Apagar no se permite desde internet.
-->
<script lang="ts">
	import Crosshair from '@lucide/svelte/icons/crosshair';
	import LocateFixed from '@lucide/svelte/icons/locate-fixed';
	import MapPin from '@lucide/svelte/icons/map-pin';
	import Pencil from '@lucide/svelte/icons/pencil';
	import Power from '@lucide/svelte/icons/power';
	import RotateCcw from '@lucide/svelte/icons/rotate-ccw';
	import { Busy } from '$lib/admin/resource.svelte';
	import { precisionMeters, radioApi, type BoardStatus } from '$lib/admin/radio';
	import { ApiError } from '$lib/api/client';
	import { publicApi } from '$lib/api/public';
	import type { TelemetrySeries } from '$lib/api/types';
	import { fmt } from '$lib/i18n/fmt.svelte';
	import { i18n } from '$lib/i18n/locale.svelte';
	import { m } from '$lib/paraglide/messages';
	import { clock } from '$lib/stores/clock.svelte';
	import { toasts } from '$lib/stores/ui.svelte';
	import Button from '$lib/components/ui/Button.svelte';
	import Modal from '$lib/components/ui/Modal.svelte';
	import Segmented from '$lib/components/ui/Segmented.svelte';
	import TimeSeriesChart from '$lib/components/ui/TimeSeriesChart.svelte';
	import ConfirmAction from '$lib/components/admin/ConfirmAction.svelte';
	import KeyValue from '$lib/components/admin/KeyValue.svelte';
	import Meter from '$lib/components/admin/Meter.svelte';
	import NumberField from '$lib/components/admin/NumberField.svelte';
	import Panel from '$lib/components/admin/Panel.svelte';
	import PositionPicker from '$lib/components/admin/PositionPicker.svelte';
	import TextField from '$lib/components/admin/TextField.svelte';
	import { metricDef, resolutionLabel } from '$lib/components/node/metrics';
	import BatteryTrend from './BatteryTrend.svelte';

	interface Props {
		cid: string;
		status: BoardStatus;
		isAdmin: boolean;
		onchange: () => void;
	}

	let { cid, status, isAdmin, onchange }: Props = $props();

	const busy = new Busy();
	const node = $derived(status.node);
	const battery = $derived(status.metrics.batteryLevel ?? null);
	const powered = $derived(battery !== null && battery > 100);
	const yesNo = (v: boolean | null | undefined) => (v ? m.adm_yes() : m.adm_no());

	// Historia de la batería: lo que meshbox guardó de la telemetría de esta placa. Voltaje y
	// carga en dos gráficos (escalas distintas); hasta 30 días con detalle de minutos.
	type Range = '86400' | '172800' | '604800' | '2592000';
	let range = $state<Range>('172800');
	let series = $state.raw<TelemetrySeries | null>(null);
	/** null = bien; `missing` = meshbox no tiene historia de este nodo (404). */
	let seriesProblem = $state<'missing' | 'failed' | null>(null);
	const voltDef = metricDef('device', 'voltage');
	const pctDef = metricDef('device', 'battery_level');

	$effect(() => {
		const id = status.gateway_id;
		const span = Number(range);
		if (!id) return;
		const ctrl = new AbortController();
		const to = clock.exact();
		seriesProblem = null;
		publicApi
			.telemetry(id, 'device', to - span, to, ctrl.signal)
			.then((d) => (series = d))
			.catch((err) => {
				if (err instanceof DOMException) return;
				seriesProblem = err instanceof ApiError && err.status === 404 ? 'missing' : 'failed';
			});
		return () => ctrl.abort();
	});

	const stats = $derived(status.local_stats);
	const statItems = $derived(
		stats
			? [
					{ label: m.adm_cli_uptime(), value: fmt.duration(stats.uptime_seconds ?? null) },
					{ label: m.adm_cli_chutil(), value: fmt.percent((stats.channel_utilization ?? 0) / 100) },
					{ label: m.adm_cli_airtx(), value: fmt.percent((stats.air_util_tx ?? 0) / 100) },
					{ label: m.adm_cli_pkts_rx(), value: fmt.number(stats.num_packets_rx ?? 0, 0) },
					{ label: m.adm_cli_pkts_rx_bad(), value: fmt.number(stats.num_packets_rx_bad ?? 0, 0) },
					{ label: m.adm_cli_pkts_dupe(), value: fmt.number(stats.num_rx_dupe ?? 0, 0) },
					{ label: m.adm_cli_pkts_tx(), value: fmt.number(stats.num_packets_tx ?? 0, 0) },
					{ label: m.adm_cli_relayed(), value: fmt.number(stats.num_tx_relay ?? 0, 0) },
					{
						label: m.adm_cli_online(),
						value: m.adm_cli_online_value({
							online: stats.num_online_nodes ?? 0,
							total: stats.num_total_nodes ?? 0
						})
					}
				]
			: []
	);

	// Nombre de la placa.
	let ownerOpen = $state(false);
	let longName = $state('');
	let shortName = $state('');
	let ownerError = $state<string | null>(null);
	let rebootOpen = $state(false);
	let shutdownOpen = $state(false);
	let unfixOpen = $state(false);

	function openOwner(): void {
		longName = node.long_name ?? '';
		shortName = node.short_name ?? '';
		ownerError = null;
		ownerOpen = true;
	}

	async function saveOwner(e: SubmitEvent): Promise<void> {
		e.preventDefault();
		const bytes = (s: string) => new TextEncoder().encode(s.trim()).length;
		if (!longName.trim() || bytes(longName) > 39) return void (ownerError = m.adm_cli_long_hint());
		if (!shortName.trim() || bytes(shortName) > 4)
			return void (ownerError = m.adm_cli_short_hint());
		const out = await busy.run(
			'owner',
			() => radioApi.owner(cid, longName.trim(), shortName.trim()),
			{
				success: m.adm_cli_saved_backup()
			}
		);
		if (out) {
			ownerOpen = false;
			onchange();
		}
	}

	async function refreshPosition(): Promise<void> {
		const out = await busy.run('pos', () => radioApi.refreshPosition(cid), {
			success: m.adm_cli_pos_refreshed()
		});
		if (out) onchange();
	}

	// Cómo comparte la posición el canal primario (el público): lo que se ve en el mapa.
	const primary = $derived(status.channels.find((c) => c.role === 'PRIMARY') ?? null);
	const shareText = $derived.by(() => {
		if (!primary) return '';
		const meters = precisionMeters(primary.position_precision);
		if (meters === null) return m.adm_cli_share_none({ channel: primary.name });
		if (meters === 0) return m.adm_cli_share_exact({ channel: primary.name });
		return m.adm_cli_share_approx({ channel: primary.name, meters: fmt.number(meters, 0) });
	});

	// Fijar la posición en el mapa.
	let fixOpen = $state(false);
	let fixLat = $state<number | null>(null);
	let fixLon = $state<number | null>(null);
	let fixAlt = $state<number | null>(0);
	let fixError = $state<string | null>(null);
	const canGeo =
		typeof window !== 'undefined' && window.isSecureContext && 'geolocation' in navigator;

	function openFix(): void {
		fixLat = status.position.latitude ?? null;
		fixLon = status.position.longitude ?? null;
		fixAlt = status.position.altitude ?? 0;
		fixError = null;
		fixOpen = true;
	}

	function useMyLocation(): void {
		fixError = null;
		navigator.geolocation.getCurrentPosition(
			(p) => {
				fixLat = Math.round(p.coords.latitude * 1e6) / 1e6;
				fixLon = Math.round(p.coords.longitude * 1e6) / 1e6;
				if (p.coords.altitude !== null) fixAlt = Math.round(p.coords.altitude);
			},
			() => (fixError = m.adm_cli_geo_failed()),
			{ enableHighAccuracy: true, timeout: 15_000 }
		);
	}

	async function saveFix(e: SubmitEvent): Promise<void> {
		e.preventDefault();
		const lat = Number(fixLat);
		const lon = Number(fixLon);
		if (
			fixLat === null ||
			fixLon === null ||
			!Number.isFinite(lat) ||
			!Number.isFinite(lon) ||
			Math.abs(lat) > 90 ||
			Math.abs(lon) > 180 ||
			(lat === 0 && lon === 0)
		) {
			fixError = m.adm_cli_fix_invalid();
			return;
		}
		const alt = Math.round(Number(fixAlt) || 0);
		const out = await busy.run('fix', () => radioApi.setPosition(cid, lat, lon, alt), {
			success: m.adm_cli_fix_saved()
		});
		if (out) {
			fixOpen = false;
			onchange();
		}
	}
</script>

<div class="adm-grid two">
	<div class="wide">
		<Panel title={m.adm_cli_battery()}>
			<div class="adm-stack">
				<Meter
					label={m.adm_cli_battery()}
					text={powered
						? m.adm_cli_powered()
						: battery === null
							? '—'
							: `${fmt.number(battery, 0)} %`}
					percent={powered || battery === null ? null : battery}
					detail={status.metrics.voltage ? `${fmt.number(status.metrics.voltage, 2)} V` : undefined}
					low
					warnAt={40}
					dangerAt={20}
				/>
				<div class="adm-row">
					<Segmented
						label={m.chart_range()}
						size="sm"
						bind:value={range}
						options={[
							{ value: '86400', label: m.adm_cli_range_day() },
							{ value: '172800', label: m.adm_cli_range_2days() },
							{ value: '604800', label: m.adm_cli_range_week() },
							{ value: '2592000', label: m.adm_cli_range_month() }
						]}
					/>
					{#if series}<span class="adm-muted res">{resolutionLabel(series)}</span>{/if}
				</div>
				{#if seriesProblem}
					<p class="adm-muted">
						{seriesProblem === 'missing' ? m.chart_no_data() : m.error_generic()}
					</p>
				{:else if series}
					<div class="charts">
						{#each [voltDef, pctDef] as def (def.key)}
							<div>
								<h3 class="chart-title">{def.label()}</h3>
								<TimeSeriesChart
									ts={series.ts}
									values={series.series[def.key] ?? []}
									min={series.min?.[def.key] ?? null}
									max={series.max?.[def.key] ?? null}
									label={def.label()}
									format={(v) => def.format(v, i18n.locale)}
									yRange={def.range ?? null}
									height={200}
									zoom
								/>
							</div>
						{/each}
					</div>
					<p class="adm-muted">{m.adm_cli_battery_101()}</p>
				{:else}
					<p class="adm-muted">{m.chart_loading()}</p>
				{/if}
				{#if status.gateway_id}<BatteryTrend nodeId={status.gateway_id} />{/if}
			</div>
		</Panel>
	</div>
	<Panel title={m.adm_cli_board()}>
		{#snippet actions()}
			{#if isAdmin}
				<Button size="sm" variant="ghost" icon={Pencil} onclick={openOwner}
					>{m.adm_cli_rename()}</Button
				>
			{/if}
		{/snippet}
		<KeyValue
			items={[
				{ label: m.adm_cli_name(), value: `${node.long_name ?? '—'} (${node.short_name ?? '—'})` },
				{ label: m.adm_cli_id(), value: node.id, mono: true },
				{ label: m.adm_cli_hw(), value: node.hw_model },
				{ label: m.adm_cli_firmware(), value: node.firmware, mono: true },
				{ label: m.adm_cli_role(), value: node.role, mono: true },
				{ label: m.adm_cli_link(), value: status.via },
				{ label: m.adm_cli_region(), value: node.region, mono: true },
				{
					label: m.adm_cli_preset(),
					value: `${node.preset}${node.preset_name ? ` · ${node.preset_name}` : ''}`,
					mono: true
				},
				{ label: m.adm_cli_tx_power(), value: `${node.tx_power} dBm` },
				{ label: m.adm_cli_hop_limit(), value: node.hop_limit },
				{ label: m.adm_cli_radio_tx(), value: yesNo(node.tx_enabled) },
				{ label: m.adm_cli_known_nodes(), value: status.nodes_in_db },
				{ label: m.adm_cli_wifi(), value: yesNo(node.wifi_enabled) },
				{ label: m.adm_cli_bluetooth(), value: yesNo(node.bluetooth_enabled) },
				{ label: m.adm_cli_power_saving(), value: yesNo(node.power_saving) },
				{ label: m.adm_cli_mqtt(), value: yesNo(node.mqtt_enabled) },
				{ label: m.adm_cli_map_report(), value: yesNo(node.map_reporting) }
			]}
		/>
		{#if !node.tx_enabled}
			<p class="adm-note warn" role="note">{m.adm_cli_radio_tx_off()}</p>
		{/if}
	</Panel>

	<Panel title={m.adm_cli_traffic()} description={m.adm_cli_traffic_desc()}>
		{#if statItems.length}
			<KeyValue items={statItems} />
		{:else}
			<p class="adm-muted">{m.adm_cli_no_stats()}</p>
		{/if}
	</Panel>

	<Panel title={m.adm_cli_position()}>
		<div class="adm-stack">
			<KeyValue
				items={[
					{
						label: m.adm_cli_coords(),
						value:
							status.position.latitude && status.position.longitude
								? `${status.position.latitude.toFixed(5)}, ${status.position.longitude.toFixed(5)}`
								: '—',
						mono: true
					},
					{ label: m.adm_cli_altitude(), value: status.position.altitude ?? '—' },
					{ label: m.adm_cli_fixed(), value: yesNo(node.fixed_position) },
					{
						label: m.adm_cli_pos_refreshed_at(),
						value: status.position_refreshed_at ? fmt.relative(status.position_refreshed_at) : '—'
					}
				]}
			/>
			{#if shareText}<p class="adm-note" role="note">{shareText}</p>{/if}
			<p class="adm-muted">{m.adm_cli_pos_note()}</p>
			{#if isAdmin}
				<div class="adm-row end">
					{#if node.fixed_position}
						<Button size="sm" variant="ghost" onclick={() => (unfixOpen = true)}
							>{m.adm_cli_unfix()}</Button
						>
						<Button size="sm" icon={Crosshair} loading={busy.is('pos')} onclick={refreshPosition}
							>{m.adm_cli_pos_refresh()}</Button
						>
					{/if}
					<Button size="sm" variant="primary" icon={MapPin} onclick={openFix}
						>{m.adm_cli_fix_position()}</Button
					>
				</div>
			{/if}
		</div>
	</Panel>

	{#if isAdmin}
		<Panel title={m.adm_cli_actions()} tone="danger">
			<div class="adm-stack">
				<p class="adm-muted">{m.adm_cli_actions_desc()}</p>
				<div class="adm-row">
					<Button size="sm" icon={RotateCcw} onclick={() => (rebootOpen = true)}
						>{m.adm_cli_reboot()}</Button
					>
					<Button
						size="sm"
						variant="danger"
						icon={Power}
						disabled={status.remote}
						onclick={() => (shutdownOpen = true)}>{m.adm_cli_shutdown()}</Button
					>
				</div>
				{#if status.remote}<p class="adm-muted">{m.adm_cli_lan_only()}</p>{/if}
			</div>
		</Panel>
	{/if}
</div>

<Modal bind:open={fixOpen} title={m.adm_cli_fix_title()} size="lg">
	<form class="adm-stack" onsubmit={saveFix}>
		<p class="adm-muted">{m.adm_cli_fix_desc()}</p>
		{#if fixOpen}
			<PositionPicker bind:lat={fixLat} bind:lon={fixLon} label={m.adm_cli_fix_title()} />
		{/if}
		<div class="adm-grid">
			<NumberField label={m.adm_cli_lat()} bind:value={fixLat} step="any" min={-90} max={90} />
			<NumberField label={m.adm_cli_lon()} bind:value={fixLon} step="any" min={-180} max={180} />
			<NumberField
				label={m.adm_cli_altitude()}
				bind:value={fixAlt}
				step={1}
				min={-500}
				max={9000}
			/>
		</div>
		{#if canGeo}
			<div class="adm-row">
				<Button size="sm" variant="ghost" icon={LocateFixed} onclick={useMyLocation}
					>{m.adm_cli_use_my_location()}</Button
				>
			</div>
		{/if}
		{#if shareText}<p class="adm-note" role="note">{shareText}</p>{/if}
		{#if fixError}<p class="adm-note danger" role="alert">{fixError}</p>{/if}
		<div class="adm-row end">
			<Button variant="ghost" onclick={() => (fixOpen = false)}>{m.adm_cancel()}</Button>
			<Button type="submit" variant="primary" icon={MapPin} loading={busy.is('fix')}
				>{m.adm_cli_fix_position()}</Button
			>
		</div>
	</form>
</Modal>

<Modal bind:open={ownerOpen} title={m.adm_cli_rename()}>
	<form class="adm-stack" onsubmit={saveOwner}>
		<TextField
			label={m.adm_cli_long_name()}
			hint={m.adm_cli_long_hint()}
			bind:value={longName}
			maxlength={39}
			required
		/>
		<TextField
			label={m.adm_cli_short_name()}
			hint={m.adm_cli_short_hint()}
			bind:value={shortName}
			maxlength={4}
			required
		/>
		{#if ownerError}<p class="adm-note danger" role="alert">{ownerError}</p>{/if}
		<p class="adm-muted">{m.adm_cli_backup_note()}</p>
		<div class="adm-row end">
			<Button variant="ghost" onclick={() => (ownerOpen = false)}>{m.adm_cancel()}</Button>
			<Button type="submit" variant="primary" loading={busy.is('owner')}>{m.adm_save()}</Button>
		</div>
	</form>
</Modal>

<ConfirmAction
	bind:open={rebootOpen}
	title={m.adm_cli_reboot_title()}
	description={m.adm_cli_reboot_desc()}
	confirmLabel={m.adm_cli_reboot()}
	action={() => radioApi.reboot(cid)}
	onsuccess={() => toasts.show(m.adm_cli_rebooting(), { kind: 'success' })}
/>

<ConfirmAction
	bind:open={shutdownOpen}
	title={m.adm_cli_shutdown_title()}
	description={m.adm_cli_shutdown_desc()}
	confirmLabel={m.adm_cli_shutdown()}
	danger
	requireText={m.adm_shutdown_word()}
	action={() => radioApi.shutdown(cid)}
	onsuccess={() => toasts.show(m.adm_cli_shutting_down(), { kind: 'success' })}
/>

<ConfirmAction
	bind:open={unfixOpen}
	title={m.adm_cli_unfix_title()}
	description={m.adm_cli_unfix_desc()}
	confirmLabel={m.adm_cli_unfix()}
	danger
	action={() => radioApi.removePosition(cid)}
	onsuccess={onchange}
/>

<style>
	.wide {
		grid-column: 1 / -1;
	}

	.charts {
		display: grid;
		grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
		gap: 12px 20px;
	}

	.chart-title {
		margin: 0 0 4px;
		font-size: 0.8125rem;
		font-weight: 600;
		color: var(--text-2);
	}

	.res {
		font-size: 0.8125rem;
	}
</style>
