<!--
  Ficha de un nodo de la placa, la misma en la pestaña Nodos y al tocar a quien escribió en
  Mensajes: sus datos y, desde ahí, mensaje directo, traceroute y pedidos de posición y de
  NodeInfo, que transmiten y respetan los límites de envío (sección 22), la administración
  remota (ADR 0017) y los últimos traceroutes del nodo.
-->
<script lang="ts">
	import IdCard from '@lucide/svelte/icons/id-card';
	import MapPin from '@lucide/svelte/icons/map-pin';
	import MessageSquare from '@lucide/svelte/icons/message-square';
	import Route from '@lucide/svelte/icons/route';
	import SlidersHorizontal from '@lucide/svelte/icons/sliders-horizontal';
	import { Busy } from '$lib/admin/resource.svelte';
	import { radioApi, type BoardNode } from '$lib/admin/radio';
	import { m } from '$lib/paraglide/messages';
	import { toasts } from '$lib/stores/ui.svelte';
	import Button from '$lib/components/ui/Button.svelte';
	import SelectField from '$lib/components/admin/SelectField.svelte';
	import TraceroutePanel from '$lib/components/admin/TraceroutePanel.svelte';
	import NodeFacts from './NodeFacts.svelte';
	import { traces } from './traces.svelte';

	interface Props {
		cid: string;
		id: string;
		/** Los nodos que conoce la placa: los datos de este y los nombres de los saltos. */
		nodes: BoardNode[];
		/** Canal de los pedidos si la placa todavía no tiene el nodo en su base. */
		channel?: number;
		/** Puede transmitir: administrador, [tx] habilitado y radio de la placa encendida. */
		canTx: boolean;
		onmessage: (id: string) => void;
		/** Solo administradores: administrar el nodo a distancia (pestaña Remoto). */
		onadmin?: (id: string) => void;
	}

	let { cid, id, nodes, channel = 0, canTx, onmessage, onadmin }: Props = $props();

	const busy = new Busy();
	const byId = $derived(new Map(nodes.filter((n) => n.id).map((n) => [n.id as string, n])));
	const node = $derived(byId.get(id) ?? null);
	const ch = $derived(node?.channel ?? channel);
	const sent = $derived(traces.sent[id] ?? null);
	const label = (nid: string) => {
		const n = byId.get(nid);
		return n?.long_name || n?.short_name || nid;
	};

	async function traceroute(): Promise<void> {
		const dest = id;
		const hops = traces.hops;
		const out = await busy.run('trace', () => radioApi.traceroute(cid, dest, hops, ch), {
			success: m.adm_cli_trace_sent()
		});
		if (out) traces.sent[dest] = { at: out.sent_at, t0: Date.now(), hops };
	}

	async function requestNodeinfo(): Promise<void> {
		const out = await busy.run('info', () => radioApi.requestNodeinfo(cid, id, ch));
		if (out) {
			toasts.show(out.answered ? m.adm_cli_nodeinfo_answered() : m.adm_cli_pos_no_answer(), {
				kind: out.answered ? 'success' : 'info'
			});
		}
	}

	async function requestPosition(): Promise<void> {
		const out = await busy.run('pos', () => radioApi.requestPosition(cid, id, ch));
		if (out) {
			toasts.show(out.answered ? m.adm_cli_pos_answered() : m.adm_cli_pos_no_answer(), {
				kind: out.answered ? 'success' : 'info'
			});
		}
	}
</script>

<div class="adm-stack">
	{#if node}
		<NodeFacts {node} />
	{:else}
		<p class="adm-muted">{m.adm_cli_card_unknown()}</p>
	{/if}
	{#if !node?.is_self}
		{#if onadmin}
			<div class="adm-row">
				<Button size="sm" icon={SlidersHorizontal} onclick={() => onadmin(id)}
					>{m.adm_cli_remote_admin()}</Button
				>
			</div>
		{/if}
		{#if canTx}
			<div class="adm-row">
				<Button size="sm" variant="primary" icon={MessageSquare} onclick={() => onmessage(id)}
					>{m.adm_cli_dm()}</Button
				>
				<SelectField
					label={m.adm_tx_hops()}
					hideLabel
					bind:value={traces.hops}
					options={[1, 2, 3, 4, 5, 6, 7].map((h) => ({
						value: h,
						label: m.adm_cli_hops_max({ count: h })
					}))}
				/>
				<Button size="sm" icon={Route} loading={busy.is('trace')} onclick={traceroute}
					>{m.adm_tx_trace_send()}</Button
				>
				<Button size="sm" icon={MapPin} loading={busy.is('pos')} onclick={requestPosition}
					>{m.adm_cli_request_pos()}</Button
				>
				<Button
					size="sm"
					icon={IdCard}
					loading={busy.is('info')}
					title={m.adm_cli_nodeinfo_hint()}
					onclick={requestNodeinfo}>{m.adm_cli_request_nodeinfo()}</Button
				>
			</div>
			<p class="adm-muted">
				{m.adm_cli_tx_note()}
				<a class="adm-link" href="/admin/transmision#limites">{m.adm_tx_limits_change()}</a>
			</p>
		{:else}
			<p class="adm-muted">{m.adm_cli_no_tx()}</p>
		{/if}
		<TraceroutePanel
			node={id}
			name={label}
			sentAt={sent?.at ?? null}
			startedAt={sent?.t0}
			hopLimit={sent?.hops ?? traces.hops}
		/>
	{/if}
</div>
