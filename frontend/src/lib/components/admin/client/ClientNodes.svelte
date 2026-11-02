<!--
  Nodos que conoce la placa (su propia base, no la de meshbox): última vez escuchado, señal,
  saltos y batería. Al tocar uno se abre su ficha (NodeDetail), la misma que desde Mensajes,
  con el mensaje directo, el traceroute, los pedidos y la administración remota.
-->
<script lang="ts">
	import type { BoardNode } from '$lib/admin/radio';
	import { fmt } from '$lib/i18n/fmt.svelte';
	import { m } from '$lib/paraglide/messages';
	import { shortFromId } from '$lib/utils/ids';
	import Button from '$lib/components/ui/Button.svelte';
	import NodeTag from '$lib/components/ui/NodeTag.svelte';
	import DataTable from '$lib/components/admin/DataTable.svelte';
	import Panel from '$lib/components/admin/Panel.svelte';
	import TextField from '$lib/components/admin/TextField.svelte';
	import type { Column } from '$lib/components/admin/types';
	import NodeDetail from './NodeDetail.svelte';

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

	let q = $state('');
	let selectedId = $state<string | null>(null);

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
	{#if selected?.id}
		<Panel title={name(selected)} description={selected.id}>
			{#snippet actions()}
				<Button size="sm" variant="ghost" onclick={() => (selectedId = null)}>{m.close()}</Button>
			{/snippet}
			<NodeDetail {cid} id={selected.id} {nodes} {canTx} {onmessage} {onadmin} />
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
