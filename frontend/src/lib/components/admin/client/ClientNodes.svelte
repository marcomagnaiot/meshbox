<!--
  Nodos que conoce la placa (su propia base, no la de meshbox): última vez escuchado, señal,
  saltos y batería. Desde cada uno: mensaje directo, traceroute y pedido de posición, que
  transmiten y respetan el límite de la sección 22, y la administración remota (ADR 0017).
-->
<script lang="ts">
	import MapPin from '@lucide/svelte/icons/map-pin';
	import MessageSquare from '@lucide/svelte/icons/message-square';
	import Route from '@lucide/svelte/icons/route';
	import SlidersHorizontal from '@lucide/svelte/icons/sliders-horizontal';
	import { Busy } from '$lib/admin/resource.svelte';
	import { radioApi, type BoardNode } from '$lib/admin/radio';
	import { fmt } from '$lib/i18n/fmt.svelte';
	import { m } from '$lib/paraglide/messages';
	import { shortFromId } from '$lib/utils/ids';
	import { toasts } from '$lib/stores/ui.svelte';
	import Button from '$lib/components/ui/Button.svelte';
	import NodeTag from '$lib/components/ui/NodeTag.svelte';
	import DataTable from '$lib/components/admin/DataTable.svelte';
	import Panel from '$lib/components/admin/Panel.svelte';
	import SelectField from '$lib/components/admin/SelectField.svelte';
	import TextField from '$lib/components/admin/TextField.svelte';
	import type { Column } from '$lib/components/admin/types';
	import NodeFacts from './NodeFacts.svelte';

	interface Props {
		cid: string;
		nodes: BoardNode[];
		/** Puede transmitir: administrador, [tx] habilitado y radio de la placa encendida. */
		canTx: boolean;
		onmessage: (id: string) => void;
		/** Solo administradores: administrar el nodo a distancia (pestaña Remoto). */
		onadmin?: (id: string) => void;
	}

	let { cid, nodes, canTx, onmessage, onadmin }: Props = $props();

	const busy = new Busy();
	let q = $state('');
	let selectedId = $state<string | null>(null);
	let hops = $state(3);

	const name = (n: BoardNode) => n.long_name || n.short_name || n.id || String(n.num);
	const rows = $derived.by(() => {
		const needle = q.trim().toLowerCase();
		if (!needle) return nodes;
		return nodes.filter((n) =>
			[n.long_name, n.short_name, n.id].some((v) => v?.toLowerCase().includes(needle))
		);
	});
	const selected = $derived(nodes.find((n) => n.id === selectedId) ?? null);

	const columns: Column<BoardNode>[] = [
		{
			key: 'name',
			label: m.adm_name(),
			width: 'minmax(200px, 2fr)',
			cell: nameCell,
			sort: (a, b) => name(a).localeCompare(name(b))
		},
		{
			key: 'heard',
			label: m.adm_last_heard(),
			width: '120px',
			text: (n) => (n.is_self ? m.adm_cli_this_board() : fmt.relative(n.last_heard)),
			sort: (a, b) => (a.last_heard ?? 0) - (b.last_heard ?? 0)
		},
		{
			key: 'hops',
			label: m.adm_cli_hops_col(),
			width: '90px',
			align: 'end',
			text: (n) =>
				n.is_self ? '' : n.hops === null ? '—' : n.hops === 0 ? m.adm_cli_direct_rx() : n.hops,
			sort: (a, b) => (a.hops ?? 99) - (b.hops ?? 99)
		},
		{
			key: 'snr',
			label: 'SNR',
			width: '90px',
			align: 'end',
			text: (n) => (n.snr === null || n.is_self ? '' : fmt.db(n.snr)),
			sort: (a, b) => (a.snr ?? -99) - (b.snr ?? -99)
		},
		{
			key: 'battery',
			label: m.adm_battery(),
			width: '100px',
			align: 'end',
			text: (n) => {
				const b = n.metrics.batteryLevel;
				return b === undefined ? '' : b > 100 ? m.adm_powered() : `${b} %`;
			},
			sort: (a, b) => (a.metrics.batteryLevel ?? -1) - (b.metrics.batteryLevel ?? -1)
		},
		{
			key: 'role',
			label: m.adm_role(),
			width: 'minmax(120px, 1fr)',
			text: (n) => `${n.role}${n.via_mqtt ? ' · MQTT' : ''}`,
			sort: (a, b) => a.role.localeCompare(b.role)
		}
	];

	async function traceroute(n: BoardNode): Promise<void> {
		if (!n.id) return;
		await busy.run('trace', () => radioApi.traceroute(cid, n.id as string, hops, n.channel), {
			success: m.adm_cli_trace_sent()
		});
	}

	async function requestPosition(n: BoardNode): Promise<void> {
		if (!n.id) return;
		const out = await busy.run('pos', () =>
			radioApi.requestPosition(cid, n.id as string, n.channel)
		);
		if (out) {
			toasts.show(out.answered ? m.adm_cli_pos_answered() : m.adm_cli_pos_no_answer(), {
				kind: out.answered ? 'success' : 'info'
			});
		}
	}
</script>

{#snippet nameCell(n: BoardNode)}
	<span class="ncell">
		<NodeTag id={n.id} label={n.short_name || (n.id ? shortFromId(n.id) : '?')} />
		<span class="name">
			<strong>{name(n)}</strong>
			<span class="adm-muted adm-mono">{n.id}</span>
		</span>
	</span>
{/snippet}

<div class="adm-stack">
	{#if selected}
		<Panel title={name(selected)} description={selected.id ?? ''}>
			{#snippet actions()}
				<Button size="sm" variant="ghost" onclick={() => (selectedId = null)}>{m.close()}</Button>
			{/snippet}
			<div class="adm-stack">
				<NodeFacts node={selected} />
				{#if !selected.is_self}
					{#if onadmin}
						<div class="adm-row">
							<Button
								size="sm"
								icon={SlidersHorizontal}
								onclick={() => selected?.id && onadmin(selected.id)}
								>{m.adm_cli_remote_admin()}</Button
							>
						</div>
					{/if}
					{#if canTx}
						<div class="adm-row">
							<Button
								size="sm"
								variant="primary"
								icon={MessageSquare}
								onclick={() => selected?.id && onmessage(selected.id)}>{m.adm_cli_dm()}</Button
							>
							<SelectField
								label={m.adm_tx_hops()}
								hideLabel
								bind:value={hops}
								options={[1, 2, 3, 4, 5, 6, 7].map((h) => ({
									value: h,
									label: m.adm_cli_hops_max({ n: h })
								}))}
							/>
							<Button
								size="sm"
								icon={Route}
								loading={busy.is('trace')}
								onclick={() => selected && traceroute(selected)}>{m.adm_tx_trace_send()}</Button
							>
							<Button
								size="sm"
								icon={MapPin}
								loading={busy.is('pos')}
								onclick={() => selected && requestPosition(selected)}
								>{m.adm_cli_request_pos()}</Button
							>
						</div>
						<p class="adm-muted">{m.adm_cli_tx_note()}</p>
					{:else}
						<p class="adm-muted">{m.adm_cli_no_tx()}</p>
					{/if}
				{/if}
			</div>
		</Panel>
	{/if}

	<Panel flush>
		<div class="filter">
			<TextField
				label={m.adm_search()}
				hideLabel
				type="search"
				placeholder={m.adm_cli_search_nodes({ n: nodes.length })}
				bind:value={q}
			/>
		</div>
		<DataTable
			{rows}
			{columns}
			rowKey={(n) => n.num}
			label={m.adm_cli_nodes()}
			rowHeight={52}
			minWidth="760px"
			sortKey="heard"
			sortDir="desc"
			selected={selected?.num ?? null}
			onrowclick={(n) => (selectedId = n.id)}
		>
			{#snippet empty()}<p class="adm-muted">{m.adm_no_results()}</p>{/snippet}
		</DataTable>
	</Panel>
</div>

<style>
	.ncell {
		display: flex;
		align-items: center;
		gap: 10px;
		min-width: 0;
	}

	.name {
		display: flex;
		flex-direction: column;
		min-width: 0;
	}

	.name > * {
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}

	.filter {
		padding: 12px 14px 4px;
	}
</style>
