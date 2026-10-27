<!--
  Mensajes (18.2): moderación del chat público. Ocultar saca el mensaje del sitio (también de
  quien lo tenga abierto, por el stream) y queda en la auditoría; mostrar lo devuelve.
-->
<script lang="ts">
	import Eye from '@lucide/svelte/icons/eye';
	import EyeOff from '@lucide/svelte/icons/eye-off';
	import RefreshCw from '@lucide/svelte/icons/refresh-cw';
	import { onMount } from 'svelte';
	import * as adminApi from '$lib/admin/api';
	import { Busy } from '$lib/admin/resource.svelte';
	import type { AdminMessage } from '$lib/admin/types';
	import { fmt } from '$lib/i18n/fmt.svelte';
	import { m } from '$lib/paraglide/messages';
	import { matches } from '$lib/utils/text';
	import Button from '$lib/components/ui/Button.svelte';
	import Skeleton from '$lib/components/ui/Skeleton.svelte';
	import DataTable from '$lib/components/admin/DataTable.svelte';
	import PageHeader from '$lib/components/admin/PageHeader.svelte';
	import Panel from '$lib/components/admin/Panel.svelte';
	import ProblemNote from '$lib/components/admin/ProblemNote.svelte';
	import SelectField from '$lib/components/admin/SelectField.svelte';
	import TextField from '$lib/components/admin/TextField.svelte';
	import type { Column } from '$lib/components/admin/types';

	let items = $state.raw<AdminMessage[]>([]);
	let next = $state<string | null>(null);
	let loading = $state(false);
	let loaded = $state(false);
	let error = $state<unknown>(null);
	let query = $state('');
	let show = $state<'all' | 'hidden' | 'alerts'>('all');
	const busy = new Busy();

	async function load(more = false): Promise<void> {
		loading = true;
		try {
			const page = await adminApi.messages.list(more ? next : null, 200);
			items = more ? [...items, ...page.messages] : page.messages;
			next = page.next;
			error = null;
			loaded = true;
		} catch (err) {
			error = err;
		} finally {
			loading = false;
		}
	}

	onMount(() => {
		void load();
	});

	const rows = $derived(
		items.filter((msg) => {
			if (show === 'hidden' && !msg.hidden) return false;
			if (show === 'alerts' && !msg.is_alert) return false;
			return !query.trim() || matches(`${msg.text} ${msg.from_name ?? ''} ${msg.from}`, query);
		})
	);

	async function moderate(msg: AdminMessage, hidden: boolean): Promise<void> {
		const out = await busy.run(String(msg.pk), () => adminApi.messages.moderate(msg.pk, hidden), {
			success: hidden ? m.adm_msg_hidden_done() : m.adm_msg_shown_done()
		});
		if (out) items = items.map((x) => (x.pk === msg.pk ? { ...x, hidden } : x));
	}

	const columns: Column<AdminMessage>[] = [
		{
			key: 'ts',
			label: m.adm_when(),
			width: '150px',
			text: (x) => fmt.dateTime(x.ts),
			sort: (a, b) => a.ts - b.ts
		},
		{ key: 'from', label: m.adm_from(), width: 'minmax(150px, 1fr)', cell: fromCell },
		{ key: 'channel', label: m.adm_channel(), width: '110px', text: (x) => x.channel ?? '' },
		{ key: 'text', label: m.adm_text(), width: 'minmax(240px, 3fr)', cell: textCell },
		{ key: 'action', label: m.adm_actions(), width: '130px', align: 'end', cell: actionCell }
	];
</script>

{#snippet fromCell(x: AdminMessage)}
	<span class="from">
		<span>{x.from_name ?? x.from}</span>
		<span class="adm-muted adm-mono">{x.from}</span>
	</span>
{/snippet}

{#snippet textCell(x: AdminMessage)}
	<span class="text" class:hidden-msg={x.hidden}>
		{#if x.hidden}<span class="adm-badge warn">{m.adm_hidden()}</span>{/if}
		{#if x.is_alert}<span class="adm-badge danger">{m.adm_alert()}</span>{/if}
		{#if x.emoji}<span class="adm-badge">{m.adm_reaction()}</span>{:else if x.reply_id}<span
				class="adm-badge">{m.adm_reply()}</span
			>{/if}
		<span class="body" title={x.text}>{x.text}</span>
	</span>
{/snippet}

{#snippet actionCell(x: AdminMessage)}
	{#if x.hidden}
		<Button
			size="sm"
			icon={Eye}
			loading={busy.is(String(x.pk))}
			onclick={(e: MouseEvent) => {
				e.stopPropagation();
				void moderate(x, false);
			}}>{m.adm_show_action()}</Button
		>
	{:else}
		<Button
			size="sm"
			icon={EyeOff}
			loading={busy.is(String(x.pk))}
			onclick={(e: MouseEvent) => {
				e.stopPropagation();
				void moderate(x, true);
			}}>{m.adm_hide_action()}</Button
		>
	{/if}
{/snippet}

<PageHeader slug="mensajes">
	{#snippet actions()}
		<Button size="sm" icon={RefreshCw} {loading} onclick={() => load()}>{m.adm_reload()}</Button>
	{/snippet}
</PageHeader>

{#if error && !loaded}
	<ProblemNote {error} onretry={() => load()} />
{:else if !loaded}
	<Skeleton lines={8} label={m.loading()} />
{:else}
	<Panel flush>
		<div class="filters">
			<TextField label={m.adm_search()} type="search" bind:value={query} />
			<SelectField
				label={m.adm_show()}
				bind:value={show}
				options={[
					{ value: 'all', label: m.adm_all() },
					{ value: 'hidden', label: m.adm_show_hidden_msgs() },
					{ value: 'alerts', label: m.adm_show_alert_msgs() }
				]}
			/>
			<p class="adm-muted count" aria-live="polite">
				{m.adm_showing({ shown: rows.length, total: items.length })}
			</p>
		</div>
		<DataTable
			{rows}
			{columns}
			rowKey={(x) => x.pk}
			label={m.admin_section_messages()}
			rowHeight={52}
			minWidth="900px"
			sortKey="ts"
			sortDir="desc"
		>
			{#snippet empty()}<p class="adm-muted">{m.adm_no_results()}</p>{/snippet}
		</DataTable>
		{#if next}
			<div class="more">
				<Button size="sm" {loading} onclick={() => load(true)}>{m.adm_load_more()}</Button>
			</div>
		{/if}
	</Panel>
	{#if error}<ProblemNote {error} onretry={() => load()} />{/if}
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

	.from {
		display: flex;
		flex-direction: column;
		line-height: 1.25;
		min-width: 0;
	}

	.from span {
		overflow: hidden;
		text-overflow: ellipsis;
	}

	.text {
		display: flex;
		align-items: center;
		gap: 6px;
		min-width: 0;
	}

	.body {
		overflow: hidden;
		text-overflow: ellipsis;
	}

	.hidden-msg .body {
		text-decoration: line-through;
		color: var(--text-2);
	}

	.more {
		display: flex;
		justify-content: center;
		padding: 12px;
	}
</style>
