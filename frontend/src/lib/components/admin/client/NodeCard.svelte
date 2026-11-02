<!--
  Ficha de un nodo al tocar su identificador en una conversación, como en la app: la misma de la
  pestaña Nodos (NodeDetail), para pedir un traceroute, la posición o el NodeInfo sin salir de la
  conversación. El mensaje directo y la administración remota cierran la ficha.
-->
<script lang="ts">
	import type { BoardNode } from '$lib/admin/radio';
	import { shortFromId } from '$lib/utils/ids';
	import Modal from '$lib/components/ui/Modal.svelte';
	import NodeTag from '$lib/components/ui/NodeTag.svelte';
	import NodeDetail from './NodeDetail.svelte';

	interface Props {
		open: boolean;
		cid: string;
		id: string;
		/** Los nodos que conoce la placa. */
		nodes: BoardNode[];
		/** Canal del mensaje: para los pedidos si la placa todavía no tiene el nodo en su base. */
		channel: number;
		canTx: boolean;
		ondm: (id: string) => void;
		/** Solo administradores: lleva a la pestaña Remoto con este nodo. */
		onadmin?: (id: string) => void;
	}

	let { open = $bindable(false), cid, id, nodes, channel, canTx, ondm, onadmin }: Props = $props();

	const node = $derived(nodes.find((n) => n.id === id) ?? null);
	const title = $derived(node?.long_name || node?.short_name || id);

	function dm(nid: string): void {
		open = false;
		ondm(nid);
	}

	function remote(nid: string): void {
		open = false;
		onadmin?.(nid);
	}
</script>

<Modal bind:open {title} description={id} size="lg">
	<div class="adm-stack">
		<div class="who">
			<NodeTag {id} label={node?.short_name || shortFromId(id)} size="md" />
		</div>
		<NodeDetail
			{cid}
			{id}
			{nodes}
			{channel}
			{canTx}
			onmessage={dm}
			onadmin={onadmin ? remote : undefined}
		/>
	</div>
</Modal>

<style>
	.who {
		display: flex;
		align-items: center;
		gap: 10px;
	}
</style>
