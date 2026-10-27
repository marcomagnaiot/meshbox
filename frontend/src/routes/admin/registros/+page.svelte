<!--
  Registros (18.2, 29): journal de meshbox, Mosquitto, cloudflared y privd con filtro por
  nivel, texto y período. Los de meshbox llegan además en vivo por el stream del panel. Cada
  línea abre su detalle completo (con la traza de la excepción, si la hay) y se puede
  descargar lo que está a la vista.
-->
<script lang="ts">
	import Download from '@lucide/svelte/icons/download';
	import RefreshCw from '@lucide/svelte/icons/refresh-cw';
	import { onMount } from 'svelte';
	import * as adminApi from '$lib/admin/api';
	import { AdminStream } from '$lib/admin/stream.svelte';
	import type { LogEntry, LogUnit } from '$lib/admin/types';
	import { fmt } from '$lib/i18n/fmt.svelte';
	import { m } from '$lib/paraglide/messages';
	import { saveBlob } from '$lib/utils/download';
	import Button from '$lib/components/ui/Button.svelte';
	import Modal from '$lib/components/ui/Modal.svelte';
	import Toggle from '$lib/components/ui/Toggle.svelte';
	import CopyBlock from '$lib/components/admin/CopyBlock.svelte';
	import DataTable from '$lib/components/admin/DataTable.svelte';
	import KeyValue from '$lib/components/admin/KeyValue.svelte';
	import PageHeader from '$lib/components/admin/PageHeader.svelte';
	import Panel from '$lib/components/admin/Panel.svelte';
	import ProblemNote from '$lib/components/admin/ProblemNote.svelte';
	import SelectField from '$lib/components/admin/SelectField.svelte';
	import TextField from '$lib/components/admin/TextField.svelte';
	import type { Column } from '$lib/components/admin/types';

	type Entry = LogEntry & { exc?: string; key: string };

	const MAX = 2000;
	const RANK: Record<string, number> = {
		DEBUG: 10,
		INFO: 20,
		WARNING: 30,
		ERROR: 40,
		CRITICAL: 50
	};
	const UNITS: LogUnit[] = ['meshbox', 'mosquitto', 'meshbox-cloudflared', 'meshbox-privd'];
	const SINCE_RE =
		/^(-?\d{1,6}\s?(s|min|h|d)|today|yesterday|\d{4}-\d{2}-\d{2}( \d{2}:\d{2}(:\d{2})?)?)$/;

	let unit = $state<LogUnit>('meshbox');
	let level = $state('');
	let q = $state('');
	let since = $state('');
	let lines = $state(500);
	let live = $state(true);
	let entries = $state.raw<Entry[]>([]);
	let loading = $state(false);
	let error = $state<unknown>(null);
	let loadedAt = $state<number | null>(null);
	let selected = $state<Entry | null>(null);
	let detailOpen = $state(false);
	let counter = 0;

	const liveAvailable = $derived(unit === 'meshbox');
	const sinceValid = $derived(!since || SINCE_RE.test(since.trim()));

	function matches(e: LogEntry): boolean {
		if (level && (RANK[e.level] ?? 0) < (RANK[level] ?? 0)) return false;
		if (q.trim() && !e.msg.toLowerCase().includes(q.trim().toLowerCase())) return false;
		return true;
	}

	const stream = new AdminStream({
		log: (data) => {
			const e = data as LogEntry & { exc?: string };
			if (unit !== 'meshbox' || !matches(e)) return;
			queue({ ...e, key: `s${e.seq ?? ++counter}` });
		}
	});

	// Las líneas en vivo se agrupan por cuadro (más nuevas arriba).
	let buffer: Entry[] = [];
	let raf = 0;
	function queue(e: Entry): void {
		buffer.push(e);
		if (raf) return;
		raf = requestAnimationFrame(() => {
			raf = 0;
			const add = buffer.reverse();
			buffer = [];
			entries = [...add, ...entries].slice(0, MAX);
		});
	}

	async function load(): Promise<void> {
		if (!sinceValid) return;
		loading = true;
		try {
			const out = await adminApi.system.logs({
				unit,
				lines,
				since: since.trim() || undefined,
				level: level || undefined,
				q: q.trim() || undefined
			});
			// El servidor las devuelve en orden cronológico: acá van las más nuevas arriba.
			entries = out.entries
				.map((e) => ({ ...e, key: `l${++counter}` }) as Entry)
				.reverse()
				.slice(0, MAX);
			error = null;
			loadedAt = Date.now();
		} catch (err) {
			error = err;
		} finally {
			loading = false;
		}
		syncStream();
	}

	function syncStream(): void {
		if (live && liveAvailable && !since.trim()) stream.open({ packets: 0, logs: 1 });
		else stream.close();
	}

	onMount(() => {
		void load();
		return () => {
			stream.close();
			cancelAnimationFrame(raf);
		};
	});

	function download(): void {
		const text = [...entries]
			.reverse()
			.map((e) => {
				const when = e.ts ? new Date(e.ts * 1000).toISOString() : '-';
				const body = e.exc ? `${e.msg}\n${e.exc}` : e.msg;
				return `${when} ${e.level.padEnd(8)} ${e.logger ?? e.unit}: ${body}`;
			})
			.join('\n');
		const stamp = new Date().toISOString().slice(0, 19).replaceAll(':', '-');
		saveBlob(new Blob([text + '\n'], { type: 'text/plain' }), `${unit}-${stamp}.log`);
	}

	function levelClass(lv: string): string {
		if (lv === 'ERROR' || lv === 'CRITICAL') return 'danger';
		if (lv === 'WARNING') return 'warn';
		if (lv === 'DEBUG') return 'muted';
		return '';
	}

	function levelLabel(lv: string): string {
		switch (lv) {
			case 'DEBUG':
				return m.adm_log_debug();
			case 'INFO':
				return m.adm_log_info();
			case 'WARNING':
				return m.adm_log_warning();
			case 'ERROR':
				return m.adm_log_error();
			case 'CRITICAL':
				return m.adm_log_critical();
			default:
				return lv;
		}
	}

	function when(ts: number | null): string {
		if (ts === null) return '';
		const today = fmt.dayKey(Date.now() / 1000) === fmt.dayKey(ts);
		return today ? fmt.time(ts, true) : `${fmt.date(ts)} ${fmt.time(ts, true)}`;
	}

	const streamText = $derived(
		stream.status === 'open'
			? m.adm_live()
			: stream.status === 'connecting'
				? m.adm_pkt_connecting()
				: stream.status === 'error'
					? m.adm_pkt_stream_error()
					: m.adm_log_not_live()
	);

	const columns: Column<Entry>[] = [
		{ key: 'ts', label: m.adm_when(), width: '150px', text: (e) => when(e.ts) },
		{ key: 'level', label: m.adm_log_level(), width: '110px', cell: levelCell },
		{
			key: 'logger',
			label: m.adm_log_source(),
			width: 'minmax(140px, 0.6fr)',
			text: (e) => e.logger ?? e.unit
		},
		{ key: 'msg', label: m.adm_log_message(), width: 'minmax(260px, 2.4fr)', cell: msgCell }
	];
</script>

{#snippet levelCell(e: Entry)}
	<span class="adm-badge {levelClass(e.level)}">{levelLabel(e.level)}</span>
{/snippet}

{#snippet msgCell(e: Entry)}
	<span class="msg adm-mono"
		>{e.msg}{#if e.exc}<span class="exc"> ⏎ {m.adm_log_has_trace()}</span>{/if}</span
	>
{/snippet}

<PageHeader slug="registros">
	{#snippet actions()}
		<Button size="sm" icon={Download} disabled={entries.length === 0} onclick={download}
			>{m.adm_log_download()}</Button
		>
	{/snippet}
</PageHeader>

<div class="adm-stack">
	<Panel>
		<form
			class="filters"
			onsubmit={(e) => {
				e.preventDefault();
				void load();
			}}
		>
			<SelectField
				label={m.adm_log_unit()}
				bind:value={unit}
				options={UNITS.map((u) => ({ value: u, label: u }))}
				onchange={() => {
					entries = [];
					void load();
				}}
			/>
			<SelectField
				label={m.adm_log_level()}
				bind:value={level}
				options={[
					{ value: '', label: m.adm_all() },
					{ value: 'DEBUG', label: m.adm_log_debug() },
					{ value: 'INFO', label: m.adm_log_info_up() },
					{ value: 'WARNING', label: m.adm_log_warning_up() },
					{ value: 'ERROR', label: m.adm_log_error_up() }
				]}
			/>
			<SelectField
				label={m.adm_log_since()}
				bind:value={since}
				options={[
					{ value: '', label: m.adm_log_since_last() },
					{ value: '-15min', label: m.adm_log_since_15m() },
					{ value: '-1h', label: m.adm_log_since_1h() },
					{ value: '-6h', label: m.adm_log_since_6h() },
					{ value: 'today', label: m.adm_log_since_today() },
					{ value: 'yesterday', label: m.adm_log_since_yesterday() },
					{ value: '-7d', label: m.adm_log_since_7d() }
				]}
			/>
			<SelectField
				label={m.adm_log_lines()}
				bind:value={lines}
				options={[200, 500, 1000, 2000].map((n) => ({ value: n, label: fmt.number(n, 0) }))}
			/>
			<TextField label={m.adm_log_search()} bind:value={q} maxlength={100} type="search" />
			<div class="buttons">
				<Button type="submit" variant="primary" size="sm" icon={RefreshCw} {loading}
					>{m.adm_log_apply()}</Button
				>
			</div>
		</form>
	</Panel>

	<Panel flush>
		<div class="toolbar">
			<div class="status-line">
				{#if liveAvailable && live && !since.trim()}
					<span class="live-dot {stream.status}" aria-hidden="true"></span>
					<span role="status">{streamText}</span>
					<span class="adm-muted">·</span>
				{:else if !liveAvailable}
					<span class="adm-muted">{m.adm_log_live_only_meshbox()}</span>
					<span class="adm-muted">·</span>
				{/if}
				<span class="adm-muted">{m.adm_log_count({ count: entries.length })}</span>
				{#if loadedAt}<span class="adm-muted"
						>· {m.adm_last_update({ time: fmt.time(loadedAt / 1000, true) })}</span
					>{/if}
			</div>
			{#if liveAvailable}
				<div class="live-toggle">
					<Toggle
						label={m.adm_log_live()}
						bind:checked={live}
						disabled={Boolean(since.trim())}
						onchange={() => syncStream()}
					/>
				</div>
			{/if}
		</div>
		{#if error}
			<div class="pad"><ProblemNote {error} onretry={() => load()} /></div>
		{/if}
		<div class="logs">
			<DataTable
				rows={entries}
				{columns}
				rowKey={(e) => e.key}
				label={m.admin_section_logs()}
				rowHeight={36}
				height="min(66vh, 680px)"
				minWidth="860px"
				rowClass={(e) => levelClass(e.level)}
				onrowclick={(e) => {
					selected = e;
					detailOpen = true;
				}}
			>
				{#snippet empty()}
					<p class="adm-muted">{loading ? m.loading() : m.adm_log_empty()}</p>
				{/snippet}
			</DataTable>
		</div>
	</Panel>
</div>

<Modal bind:open={detailOpen} title={m.adm_log_detail()} size="lg">
	{#if selected}
		<div class="adm-stack">
			<KeyValue
				columns={2}
				items={[
					{ label: m.adm_when(), value: selected.ts ? fmt.dateTime(selected.ts) : null },
					{ label: m.adm_log_level(), value: levelLabel(selected.level) },
					{ label: m.adm_log_source(), value: selected.logger, mono: true },
					{ label: m.adm_log_unit(), value: selected.unit, mono: true }
				]}
			/>
			<CopyBlock
				label={m.adm_log_message()}
				text={selected.exc ? `${selected.msg}\n${selected.exc}` : selected.msg}
			/>
		</div>
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

	.toolbar {
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		justify-content: space-between;
		gap: 8px 16px;
		padding: 12px 16px;
	}

	.status-line {
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		gap: 6px;
		font-size: 0.8125rem;
	}

	.live-toggle :global(.toggle) {
		gap: 12px;
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

	.msg {
		display: block;
		overflow: hidden;
		white-space: nowrap;
		text-overflow: ellipsis;
		font-size: 0.8125rem;
	}

	.exc {
		color: var(--danger-text, var(--danger));
	}

	.pad {
		padding: 0 16px 12px;
	}

	.logs :global(.dt-row.danger) {
		background: color-mix(in oklch, var(--danger-soft) 55%, transparent);
	}

	.logs :global(.dt-row.warn) {
		background: color-mix(in oklch, var(--warning-soft) 45%, transparent);
	}

	.logs :global(.dt-row.muted) {
		color: var(--text-2);
	}
</style>
