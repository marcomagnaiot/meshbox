<!--
  Paquetes (18.2): captura en vivo (stream del panel, con pausa) y desde la base (paginada),
  con filtros por tipo, origen, destino, canal, gateway, SNR, saltos y texto; detalle de cada
  paquete y exportación CSV o JSONL con los mismos filtros.
-->
<script lang="ts">
	import Download from '@lucide/svelte/icons/download';
	import Pause from '@lucide/svelte/icons/pause';
	import Play from '@lucide/svelte/icons/play';
	import Trash2 from '@lucide/svelte/icons/trash-2';
	import { onMount } from 'svelte';
	import * as adminApi from '$lib/admin/api';
	import type { PacketFilters } from '$lib/admin/api';
	import { problemText } from '$lib/admin/errors';
	import { AdminStream } from '$lib/admin/stream.svelte';
	import type { LivePacket, PacketRow } from '$lib/admin/types';
	import { fmt } from '$lib/i18n/fmt.svelte';
	import { KNOWN_PORTS, portLabel } from '$lib/i18n/labels';
	import { m } from '$lib/paraglide/messages';
	import Button from '$lib/components/ui/Button.svelte';
	import Modal from '$lib/components/ui/Modal.svelte';
	import Segmented from '$lib/components/ui/Segmented.svelte';
	import DataTable from '$lib/components/admin/DataTable.svelte';
	import NumberField from '$lib/components/admin/NumberField.svelte';
	import PageHeader from '$lib/components/admin/PageHeader.svelte';
	import Panel from '$lib/components/admin/Panel.svelte';
	import ProblemNote from '$lib/components/admin/ProblemNote.svelte';
	import SelectField from '$lib/components/admin/SelectField.svelte';
	import TextField from '$lib/components/admin/TextField.svelte';
	import PacketDetailView from '$lib/components/admin/packets/PacketDetail.svelte';
	import type { Column } from '$lib/components/admin/types';

	/** Fila común a la captura en vivo y al historial. */
	type Row = Pick<
		PacketRow,
		| 'pk'
		| 'portnum'
		| 'from'
		| 'to'
		| 'packet_id'
		| 'channel'
		| 'hops'
		| 'snr'
		| 'rssi'
		| 'gateway'
		| 'is_public'
		| 'encrypted'
		| 'decoded_ok'
		| 'via_mqtt'
		| 'ts'
	> & { duplicate?: boolean; seq?: number };

	const LIVE_MAX = 2000;
	let mode = $state<'live' | 'history'>('live');
	let paused = $state(false);
	let live = $state.raw<Row[]>([]);
	let pending = $state.raw<Row[]>([]);
	let history = $state.raw<Row[]>([]);
	let next = $state<string | null>(null);
	let loading = $state(false);
	let error = $state<unknown>(null);
	let names = $state.raw<Map<string, string>>(new Map());
	let detailPk = $state<number | null>(null);
	let detailOpen = $state(false);
	let showDuplicates = $state(false);

	// Filtros (los del servidor se aplican al pedir; el resto en el navegador).
	let portnum = $state('');
	let from = $state('');
	let to = $state('');
	let channel = $state('');
	let gateway = $state('');
	let minSnr = $state<number | null>(null);
	let maxHops = $state<number | null>(null);
	let q = $state('');

	const filters = $derived<PacketFilters>({
		portnum: portnum || undefined,
		from: from.trim() || undefined,
		to: to.trim() || undefined,
		channel: channel.trim() || undefined,
		gateway: gateway.trim() || undefined,
		min_snr: minSnr,
		max_hops: maxHops,
		q: q.trim() || undefined
	});

	const stream = new AdminStream({
		packet: (data) => {
			const p = data as LivePacket;
			const row: Row = { ...p, pk: p.pk };
			if (paused) {
				pending = [...pending, row];
				if (pending.length > LIVE_MAX) pending = pending.slice(-LIVE_MAX);
				return;
			}
			queue(row);
		}
	});

	// Los paquetes en vivo se agrupan por cuadro para no redibujar la tabla en cada uno.
	let buffer: Row[] = [];
	let raf = 0;
	function queue(row: Row): void {
		buffer.push(row);
		if (!raf) {
			raf = requestAnimationFrame(() => {
				raf = 0;
				const add = buffer.reverse();
				buffer = [];
				live = [...add, ...live].slice(0, LIVE_MAX);
			});
		}
	}

	function openStream(): void {
		const node = filters.from ?? filters.to;
		stream.open({
			packets: 1,
			logs: 0,
			portnum: filters.portnum,
			node,
			gateway: filters.gateway,
			max_packets_per_s: 20
		});
	}

	async function loadHistory(more = false): Promise<void> {
		loading = true;
		try {
			const page = await adminApi.packets.list(filters, more ? next : null, 200);
			history = more ? [...history, ...page.packets] : page.packets;
			next = page.next;
			error = null;
		} catch (err) {
			error = err;
		} finally {
			loading = false;
		}
	}

	function apply(): void {
		if (mode === 'live') {
			live = [];
			openStream();
		} else void loadHistory();
	}

	function clearFilters(): void {
		portnum = from = to = channel = gateway = q = '';
		minSnr = maxHops = null;
		apply();
	}

	onMount(() => {
		openStream();
		adminApi.nodes
			.list()
			.then((r) => {
				names = new Map(r.nodes.map((n) => [n.id, n.long_name || n.short_name || n.id]));
			})
			.catch(() => {});
		return () => {
			stream.close();
			cancelAnimationFrame(raf);
		};
	});

	function setMode(v: 'live' | 'history'): void {
		mode = v;
		if (v === 'live') {
			openStream();
		} else {
			stream.close();
			void loadHistory();
		}
	}

	function togglePause(): void {
		paused = !paused;
		if (!paused && pending.length) {
			live = [...[...pending].reverse(), ...live].slice(0, LIVE_MAX);
			pending = [];
		}
	}

	// Filtros del navegador sobre la captura en vivo (el stream solo filtra tipo, nodo y gateway).
	const liveRows = $derived(
		live.filter((r) => {
			if (!showDuplicates && r.duplicate) return false;
			if (filters.to && r.to !== filters.to) return false;
			if (filters.from && r.from !== filters.from) return false;
			if (filters.channel && r.channel !== filters.channel) return false;
			if (minSnr !== null && (r.snr === null || r.snr < minSnr)) return false;
			if (maxHops !== null && (r.hops === null || r.hops > maxHops)) return false;
			if (filters.q) {
				const needle = filters.q.toLowerCase();
				const name = `${names.get(r.from) ?? ''} ${r.from} ${r.packet_id}`.toLowerCase();
				if (!name.includes(needle)) return false;
			}
			return true;
		})
	);
	const rows = $derived(mode === 'live' ? liveRows : history);
	const nameOf = (id: string) => names.get(id) ?? null;
	const exportCsv = $derived(adminApi.packets.exportUrl('csv', filters));
	const exportJsonl = $derived(adminApi.packets.exportUrl('jsonl', filters));
	const streamText = $derived(
		paused
			? m.adm_paused()
			: stream.status === 'open'
				? m.adm_live()
				: stream.status === 'connecting'
					? m.adm_pkt_connecting()
					: m.adm_pkt_stream_error()
	);

	const columns: Column<Row>[] = [
		{ key: 'ts', label: m.adm_when(), width: '96px', text: (r) => fmt.time(r.ts, true) },
		{ key: 'port', label: m.adm_pkt_type(), width: 'minmax(120px, 1fr)', cell: portCell },
		{ key: 'from', label: m.adm_from(), width: 'minmax(150px, 1.4fr)', cell: fromCell },
		{
			key: 'to',
			label: m.adm_pkt_to(),
			width: '110px',
			text: (r) => (r.to === '^all' ? m.adm_pkt_all() : r.to)
		},
		{ key: 'channel', label: m.adm_channel(), width: '100px', text: (r) => r.channel ?? '' },
		{
			key: 'hops',
			label: m.adm_pkt_hops(),
			width: '64px',
			align: 'end',
			text: (r) => (r.hops === null ? '' : r.hops)
		},
		{ key: 'snr', label: m.adm_snr(), width: '80px', align: 'end', text: (r) => fmt.db(r.snr) },
		{ key: 'rssi', label: m.adm_rssi(), width: '90px', align: 'end', text: (r) => fmt.dbm(r.rssi) },
		{ key: 'gw', label: m.adm_gateway(), width: '100px', text: (r) => r.gateway ?? '' },
		{ key: 'flags', label: m.adm_flags(), width: '130px', cell: flagsCell }
	];
</script>

{#snippet portCell(r: Row)}
	<span>{portLabel(r.portnum ?? 'ENCRYPTED')}</span>
{/snippet}

{#snippet fromCell(r: Row)}
	<span class="who">
		<span>{names.get(r.from) ?? r.from}</span>
		<span class="adm-muted adm-mono">{r.from}</span>
	</span>
{/snippet}

{#snippet flagsCell(r: Row)}
	<span class="flags">
		{#if r.is_public}<span class="adm-badge ok" title={m.adm_pkt_public()}
				>{m.adm_pkt_public_short()}</span
			>{/if}
		{#if r.encrypted && !r.decoded_ok}<span class="adm-badge warn" title={m.adm_pkt_encrypted()}
				>{m.adm_pkt_encrypted_short()}</span
			>{/if}
		{#if r.via_mqtt}<span class="adm-badge">MQTT</span>{/if}
		{#if r.duplicate}<span class="adm-badge">{m.adm_pkt_dup()}</span>{/if}
	</span>
{/snippet}

<PageHeader slug="paquetes">
	{#snippet actions()}
		<Button size="sm" icon={Download} href={exportCsv} download>{m.adm_pkt_export_csv()}</Button>
		<Button size="sm" icon={Download} href={exportJsonl} download>{m.adm_pkt_export_jsonl()}</Button
		>
	{/snippet}
</PageHeader>

<div class="adm-stack">
	<Panel>
		<form
			class="filters"
			onsubmit={(e) => {
				e.preventDefault();
				apply();
			}}
		>
			<SelectField
				label={m.adm_pkt_type()}
				bind:value={portnum}
				options={[
					{ value: '', label: m.adm_all() },
					...KNOWN_PORTS.map((p) => ({ value: p, label: portLabel(p) }))
				]}
			/>
			<TextField label={m.adm_from()} bind:value={from} placeholder="!0b03cbf0" mono />
			<TextField label={m.adm_pkt_to()} bind:value={to} placeholder="!… o ^all" mono />
			<TextField label={m.adm_channel()} bind:value={channel} placeholder="MediumFast" />
			<TextField label={m.adm_gateway()} bind:value={gateway} placeholder="!a1b2c3d4" mono />
			<NumberField label={m.adm_pkt_min_snr()} bind:value={minSnr} step="any" unit="dB" />
			<NumberField label={m.adm_pkt_max_hops()} bind:value={maxHops} min={0} max={7} step={1} />
			<TextField label={m.adm_pkt_text()} hint={m.adm_pkt_text_hint()} bind:value={q} />
			<div class="buttons">
				<Button type="submit" variant="primary" size="sm">{m.adm_filter()}</Button>
				<Button size="sm" variant="ghost" onclick={clearFilters}>{m.adm_clear_filters()}</Button>
			</div>
		</form>
	</Panel>

	<Panel flush>
		{#snippet actions()}
			<div class="bar">
				<Segmented
					label={m.adm_pkt_source_mode()}
					size="sm"
					options={[
						{ value: 'live', label: m.adm_live() },
						{ value: 'history', label: m.adm_pkt_history() }
					]}
					value={mode}
					onchange={(v) => setMode(v)}
				/>
				{#if mode === 'live'}
					<Button size="sm" icon={paused ? Play : Pause} onclick={togglePause} aria-pressed={paused}
						>{paused ? m.adm_resume() : m.adm_pause()}</Button
					>
					<Button size="sm" variant="ghost" icon={Trash2} onclick={() => (live = [])}
						>{m.adm_pkt_clear()}</Button
					>
					<label class="dup">
						<input type="checkbox" bind:checked={showDuplicates} />
						{m.adm_pkt_show_dup()}
					</label>
				{/if}
			</div>
		{/snippet}
		<div class="status-line">
			{#if mode === 'live'}
				<span class="live-dot {stream.status}" aria-hidden="true"></span>
				<span role="status">{streamText}</span>
				<span class="adm-muted">· {m.adm_pkt_count({ count: liveRows.length })}</span>
				{#if paused && pending.length}<span class="adm-muted"
						>· {m.adm_pkt_pending({ count: pending.length })}</span
					>{/if}
			{:else}
				<span class="adm-muted">{m.adm_pkt_count({ count: history.length })}</span>
			{/if}
		</div>
		{#if mode === 'history' && error}
			<div class="pad"><ProblemNote {error} onretry={() => loadHistory()} /></div>
		{/if}
		<DataTable
			{rows}
			{columns}
			rowKey={(r) => `${r.pk}-${r.seq ?? ''}`}
			label={m.admin_section_packets()}
			rowHeight={48}
			height="min(64vh, 640px)"
			minWidth="1100px"
			onrowclick={(r) => {
				detailPk = r.pk;
				detailOpen = true;
			}}
		>
			{#snippet empty()}
				<p class="adm-muted">{mode === 'live' ? m.adm_pkt_waiting() : m.adm_no_results()}</p>
			{/snippet}
		</DataTable>
		{#if mode === 'history' && next}
			<div class="more">
				<Button size="sm" {loading} onclick={() => loadHistory(true)}>{m.adm_load_more()}</Button>
			</div>
		{/if}
	</Panel>
	{#if error && mode === 'history'}<p class="sr-only" role="alert">{problemText(error)}</p>{/if}
</div>

<Modal bind:open={detailOpen} title={m.adm_pkt_detail({ pk: detailPk ?? 0 })} size="lg">
	{#if detailPk !== null && detailOpen}
		<PacketDetailView pk={detailPk} {nameOf} />
	{/if}
</Modal>

<style>
	.filters {
		display: grid;
		grid-template-columns: repeat(auto-fill, minmax(min(100%, 180px), 1fr));
		gap: 12px;
		align-items: end;
	}

	.buttons {
		display: flex;
		gap: 8px;
		align-items: center;
		min-height: 44px;
	}

	.bar {
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		gap: 8px;
	}

	.dup {
		display: inline-flex;
		align-items: center;
		gap: 6px;
		min-height: 36px;
		font-size: 0.8125rem;
	}

	.dup input {
		width: 18px;
		height: 18px;
		accent-color: var(--accent);
	}

	.status-line {
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		gap: 6px;
		padding: 0 16px 10px;
		font-size: 0.8125rem;
	}

	.live-dot {
		width: 10px;
		height: 10px;
		border-radius: 50%;
		border: 2px solid var(--text-3);
	}

	.live-dot.open {
		border-color: transparent;
		background: var(--success);
	}

	.live-dot.error {
		border-color: var(--danger);
	}

	.who {
		display: flex;
		flex-direction: column;
		line-height: 1.2;
		min-width: 0;
	}

	.who span {
		overflow: hidden;
		text-overflow: ellipsis;
	}

	.flags {
		display: inline-flex;
		gap: 4px;
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
