<!--
  Ficha de un nodo al tocar su identificador en una conversación, como en la app: sus datos y,
  desde ahí, abrir un mensaje directo o administrarlo a distancia.
-->
<script lang="ts">
	import MessageSquare from '@lucide/svelte/icons/message-square';
	import SlidersHorizontal from '@lucide/svelte/icons/sliders-horizontal';
	import type { BoardNode } from '$lib/admin/radio';
	import { m } from '$lib/paraglide/messages';
	import { shortFromId } from '$lib/utils/ids';
	import Button from '$lib/components/ui/Button.svelte';
	import Modal from '$lib/components/ui/Modal.svelte';
	import NodeTag from '$lib/components/ui/NodeTag.svelte';
	import NodeFacts from './NodeFacts.svelte';

	interface Props {
		open: boolean;
		id: string;
		/** Lo que sabe la placa del nodo (`null` si todavía no lo tiene en su base). */
		node: BoardNode | null;
		ondm: (id: string) => void;
		/** Solo administradores: lleva a la pestaña Remoto con este nodo. */
		onadmin?: (id: string) => void;
	}

	let { open = $bindable(false), id, node, ondm, onadmin }: Props = $props();

	const title = $derived(node?.long_name || node?.short_name || id);
</script>

<Modal bind:open {title} description={id} size="lg">
	<div class="adm-stack">
		<div class="who">
			<NodeTag {id} label={node?.short_name || shortFromId(id)} size="md" />
		</div>
		{#if node}
			<NodeFacts {node} />
		{:else}
			<p class="adm-muted">{m.adm_cli_card_unknown()}</p>
		{/if}
		<div class="adm-row end">
			{#if onadmin}
				<Button
					size="sm"
					icon={SlidersHorizontal}
					onclick={() => {
						open = false;
						onadmin(id);
					}}>{m.adm_cli_remote_admin()}</Button
				>
			{/if}
			<Button
				size="sm"
				variant="primary"
				icon={MessageSquare}
				onclick={() => {
					open = false;
					ondm(id);
				}}>{m.adm_cli_dm()}</Button
			>
		</div>
	</div>
</Modal>

<style>
	.who {
		display: flex;
		align-items: center;
		gap: 10px;
	}
</style>
