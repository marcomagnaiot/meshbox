<!--
  Nodos (18.2): tabla completa con los ocultos; ocultar o mostrar (baja a pedido), marcar como
  fijo, nota interna y borrar el historial (sección 30, con confirmación escrita).
-->
<script lang="ts">
	import EyeOff from '@lucide/svelte/icons/eye-off';
	import RefreshCw from '@lucide/svelte/icons/refresh-cw';
	import Trash2 from '@lucide/svelte/icons/trash-2';
	import { onMount } from 'svelte';
	import * as adminApi from '$lib/admin/api';
	import { Busy, Resource } from '$lib/admin/resource.svelte';
	import type { AdminNode } from '$lib/admin/types';
	import { fmt } from '$lib/i18n/fmt.svelte';
	import { roleLabel, statusLabel } from '$lib/i18n/labels';
	import { m } from '$lib/paraglide/messages';
	import { shortFromId } from '$lib/utils/ids';
	import { displayName } from '$lib/utils/nodes';
	import { matches } from '$lib/utils/text';
	import Button from '$lib/components/ui/Button.svelte';
	import Modal from '$lib/components/ui/Modal.svelte';
	import NodeTag from '$lib/components/ui/NodeTag.svelte';
	import Skeleton from '$lib/components/ui/Skeleton.svelte';
	import StatusGlyph from '$lib/components/ui/StatusGlyph.svelte';
	import Toggle from '$lib/components/ui/Toggle.svelte';
	import ConfirmAction from '$lib/components/admin/ConfirmAction.svelte';
	import DataTable from '$lib/components/admin/DataTable.svelte';
	import KeyValue from '$lib/components/admin/KeyValue.svelte';
	import PageHeader from '$lib/components/admin/PageHeader.svelte';
	import Panel from '$lib/components/admin/Panel.svelte';
	import ProblemNote from '$lib/components/admin/ProblemNote.svelte';
	import SelectField from '$lib/components/admin/SelectField.svelte';
	import TextArea from '$lib/components/admin/TextArea.svelte';
	import TextField from '$lib/components/admin/TextField.svelte';
	import type { Column } from '$lib/components/admin/types';

	type Show = 'all' | 'visible' | 'hidden' | 'fixed';

	const list = new Resource(() => adminApi.nodes.list());
	const busy = new Busy();
	let query = $state('');
	let show = $state<Show>('all');
	let selectedId = $state<string | null>(null);
	let detailOpen = $state(false);
	let purgeOpen = $state(false);
	let note = $state('');
	let purged = $state<Record<string, number> | null>(null);

	onMount(() => {
		void list.load();
		const stop = list.poll(30_000);
		return () => {
			stop();
			list.dispose();
		};
	});

	const nodes = $derived(list.data?.nodes ?? []);
	const rows = $derived(
		nodes.filter((n) => {
			if (show === 'hidden' && !n.hidden) return false;
			if (show === 'visible' && n.hidden) return false;
			if (show === 'fixed' && !n.is_fixed) return false;
			return !query.trim() || matches(`${n.long_name ?? ''} ${n.short_name ?? ''} ${n.id}`, query);
		})
	);
	const selected = $derived(nodes.find((n) => n.id === selectedId) ?? null);
	const hiddenCount = $derived(nodes.filter((n) => n.hidden).length);

	function open(n: AdminNode): void {
		selectedId = n.id;
		note = n.note ?? '';
		purged = null;
		detailOpen = true;
	}

	async function patch(body: { hidden?: boolean; is_fixed?: boolean; note?: string | null }) {
		if (!selected) return;
		const id = selected.id;
		const out = await busy.run(id, () => adminApi.nodes.patch(id, body), {
			success: m.adm_saved()
		});
		if (out) await list.load();
	}

	const columns: Column<AdminNode>[] = [
		{
			key: 'name',
			label: m.adm_name(),
			width: 'minmax(200px, 2fr)',
			cell: nameCell,
			sort: (a, b) => displayName(a).localeCompare(displayName(b))
		},
		{
			key: 'status',
			label: m.adm_status(),
			width: '130px',
			cell: statusCell,
			sort: (a, b) => a.last_heard - b.last_heard
		},
		{
			key: 'role',
			label: m.adm_role(),
			width: 'minmax(110px, 1fr)',
			// El gateway origina pocos paquetes propios: se marca aparte (el backend lo da por vivo
			// por el tráfico que pasa por él).
			text: (n) =>
				n.is_gateway ? `${roleLabel(n.role)} · ${m.node_gateway()}` : roleLabel(n.role),
			sort: (a, b) => a.role.localeCompare(b.role)
		},
		{
			key: 'battery',
			label: m.adm_battery(),
			width: '90px',
			align: 'end',
			text: (n) => (n.battery === null ? '' : n.battery > 100 ? m.adm_powered() : `${n.battery} %`),
			sort: (a, b) => (a.battery ?? -1) - (b.battery ?? -1)
		},
		{
			key: 'heard',
			label: m.adm_last_heard(),
			width: '120px',
			text: (n) => fmt.relative(n.last_heard),
			sort: (a, b) => a.last_heard - b.last_heard
		},
		{ key: 'flags', label: m.adm_flags(), width: '150px', cell: flagsCell },
		{ key: 'note', label: m.adm_note(), width: 'minmax(140px, 1.5fr)', text: (n) => n.note ?? '' }
	];
</script>

{#snippet nameCell(n: AdminNode)}
	<span class="ncell">
		<NodeTag id={n.id} label={n.short_name || shortFromId(n.id)} />
		<span class="name">
			<strong>{displayName(n)}</strong>
			<span class="adm-muted adm-mono">{n.id}</span>
		</span>
	</span>
{/snippet}

{#snippet statusCell(n: AdminNode)}
	<span class="status">
		<StatusGlyph status={n.status} infra={n.is_infra} fixed={n.is_fixed} />
		{statusLabel(n.status)}
	</span>
{/snippet}

{#snippet flagsCell(n: AdminNode)}
	<span class="adm-row">
		{#if n.hidden}<span class="adm-badge warn"
				><EyeOff size={12} aria-hidden="true" />{m.adm_hidden()}</span
			>{/if}
		{#if n.is_gateway}<span class="adm-badge accent">{m.node_gateway()}</span>{/if}
		{#if n.is_fixed}<span class="adm-badge">{m.adm_fixed()}</span>{/if}
		{#if n.heard_via_mqtt_only}<span class="adm-badge">MQTT</span>{/if}
	</span>
{/snippet}

<PageHeader slug="nodos">
	{#snippet actions()}
		<Button size="sm" icon={RefreshCw} loading={list.loading} onclick={() => list.load()}
			>{m.adm_reload()}</Button
		>
	{/snippet}
</PageHeader>

{#if list.error && !list.data}
	<ProblemNote error={list.error} onretry={() => list.load()} />
{:else if !list.data}
	<Skeleton lines={8} label={m.loading()} />
{:else}
	<Panel flush>
		<div class="filters">
			<TextField
				label={m.adm_search()}
				type="search"
				bind:value={query}
				placeholder={m.adm_nodes_search_ph()}
			/>
			<SelectField
				label={m.adm_show()}
				bind:value={show}
				options={[
					{ value: 'all', label: m.adm_all() },
					{ value: 'visible', label: m.adm_show_visible() },
					{ value: 'hidden', label: m.adm_show_hidden({ count: hiddenCount }) },
					{ value: 'fixed', label: m.adm_show_fixed() }
				]}
			/>
			<p class="adm-muted count" aria-live="polite">
				{m.adm_showing({ shown: rows.length, total: nodes.length })}
			</p>
		</div>
		<DataTable
			{rows}
			{columns}
			rowKey={(n) => n.id}
			label={m.admin_section_nodes()}
			rowHeight={52}
			minWidth="980px"
			sortKey="heard"
			sortDir="desc"
			selected={detailOpen ? selectedId : null}
			onrowclick={open}
		>
			{#snippet empty()}<p class="adm-muted">{m.adm_no_results()}</p>{/snippet}
		</DataTable>
	</Panel>
{/if}

<Modal bind:open={detailOpen} title={selected ? displayName(selected) : ''} size="lg">
	{#if selected}
		<div class="adm-stack">
			<KeyValue
				columns={3}
				items={[
					{ label: m.adm_node_id(), value: selected.id, mono: true },
					{ label: m.adm_short_name(), value: selected.short_name },
					{
						label: m.adm_role(),
						value: selected.is_gateway
							? `${roleLabel(selected.role)} · ${m.node_gateway()}`
							: roleLabel(selected.role)
					},
					{ label: m.adm_status(), value: statusLabel(selected.status) },
					{ label: m.adm_last_heard(), value: fmt.dateTime(selected.last_heard) },
					{ label: m.adm_first_seen(), value: fmt.dateTime(selected.first_seen) },
					{ label: m.adm_hw_model(), value: selected.hw_model },
					{ label: m.adm_firmware(), value: selected.firmware_version },
					{ label: m.adm_last_gateway(), value: selected.last_gateway, mono: true },
					{
						label: m.adm_position(),
						value:
							selected.lat !== null && selected.lon !== null
								? `${fmt.number(selected.lat, 5)}, ${fmt.number(selected.lon, 5)}`
								: null
					},
					{
						label: m.adm_public_key(),
						value: selected.has_public_key ? m.adm_yes() : m.adm_no()
					},
					{
						label: m.adm_via_mqtt_only(),
						value: selected.heard_via_mqtt_only ? m.adm_yes() : m.adm_no()
					}
				]}
			/>

			<div class="toggles">
				<Toggle
					label={m.adm_node_hidden()}
					hint={m.adm_node_hidden_hint()}
					checked={selected.hidden}
					disabled={busy.is(selected.id)}
					onchange={(v) => patch({ hidden: v })}
				/>
				<Toggle
					label={m.adm_node_fixed()}
					hint={m.adm_node_fixed_hint()}
					checked={selected.is_fixed}
					disabled={busy.is(selected.id)}
					onchange={(v) => patch({ is_fixed: v })}
				/>
			</div>

			<form
				class="adm-stack"
				onsubmit={(e) => {
					e.preventDefault();
					void patch({ note: note.trim() || null });
				}}
			>
				<TextArea
					label={m.adm_internal_note()}
					hint={m.adm_internal_note_hint()}
					bind:value={note}
					maxlength={500}
					rows={3}
				/>
				<div class="adm-row end">
					<Button type="submit" size="sm" variant="primary" loading={busy.is(selected.id)}
						>{m.adm_save()}</Button
					>
				</div>
			</form>

			<Panel title={m.adm_purge_title()} description={m.adm_purge_desc()} tone="danger">
				{#if purged}
					<p class="adm-note ok" role="status">
						{m.adm_purge_done({
							count: Object.values(purged).reduce((a, b) => a + b, 0)
						})}
					</p>
				{/if}
				<Button variant="danger" icon={Trash2} onclick={() => (purgeOpen = true)}
					>{m.adm_purge_action()}</Button
				>
			</Panel>

			{#if !selected.hidden}
				<a class="adm-link" href="/n/{encodeURIComponent(selected.id)}" data-sveltekit-reload
					>{m.adm_open_public()}</a
				>
			{/if}
		</div>
	{/if}
</Modal>

{#if selected}
	<ConfirmAction
		bind:open={purgeOpen}
		title={m.adm_purge_confirm_title({ name: displayName(selected) })}
		description={m.adm_purge_confirm_desc()}
		confirmLabel={m.adm_purge_action()}
		danger
		requireText={selected.short_name || selected.id}
		action={() => adminApi.nodes.purge(selected!.id)}
		onsuccess={(r) => {
			purged = (r as { deleted: Record<string, number> }).deleted;
			void list.load();
		}}
	/>
{/if}

<style>
	.filters {
		display: grid;
		grid-template-columns: minmax(200px, 2fr) minmax(160px, 1fr) auto;
		align-items: end;
		gap: 12px;
		padding: 0 16px 12px;
	}

	@media (max-width: 720px) {
		.filters {
			grid-template-columns: 1fr;
		}
	}

	.count {
		margin: 0 0 12px;
		white-space: nowrap;
	}

	.ncell {
		display: flex;
		align-items: center;
		gap: 10px;
		min-width: 0;
	}

	.name {
		display: flex;
		flex-direction: column;
		line-height: 1.25;
		min-width: 0;
	}

	.name strong,
	.name span {
		overflow: hidden;
		text-overflow: ellipsis;
	}

	.status {
		display: inline-flex;
		align-items: center;
		gap: 6px;
	}

	.toggles {
		display: flex;
		flex-direction: column;
		gap: 4px;
		padding: 4px 0;
		border-top: 1px solid var(--line);
		border-bottom: 1px solid var(--line);
	}
</style>
