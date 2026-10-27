<!--
  Cliente Meshtastic (ADR 0015): lo que ofrece la app del teléfono, para cada placa conectada
  por USB o por la red. Estado y batería, mensajes de los canales y directos, nodos que conoce
  la placa, canales, configuración completa y copias. Los operadores solo miran; escribir y
  transmitir es de administradores. Antes de cada cambio se guarda una copia de la placa.
-->
<script lang="ts">
	import RefreshCw from '@lucide/svelte/icons/refresh-cw';
	import { onMount } from 'svelte';
	import { connectorStateLabel } from '$lib/admin/labels';
	import { radioApi } from '$lib/admin/radio';
	import { Resource } from '$lib/admin/resource.svelte';
	import { m } from '$lib/paraglide/messages';
	import { admin } from '$lib/stores/admin.svelte';
	import Button from '$lib/components/ui/Button.svelte';
	import Segmented from '$lib/components/ui/Segmented.svelte';
	import Skeleton from '$lib/components/ui/Skeleton.svelte';
	import PageHeader from '$lib/components/admin/PageHeader.svelte';
	import Panel from '$lib/components/admin/Panel.svelte';
	import ProblemNote from '$lib/components/admin/ProblemNote.svelte';
	import ClientBackups from '$lib/components/admin/client/ClientBackups.svelte';
	import ClientChannels from '$lib/components/admin/client/ClientChannels.svelte';
	import ClientConfig from '$lib/components/admin/client/ClientConfig.svelte';
	import ClientMessages from '$lib/components/admin/client/ClientMessages.svelte';
	import ClientNodes from '$lib/components/admin/client/ClientNodes.svelte';
	import ClientStatus from '$lib/components/admin/client/ClientStatus.svelte';

	type Tab = 'status' | 'messages' | 'nodes' | 'channels' | 'config' | 'backups';

	const isAdmin = $derived(admin.session?.role === 'admin');
	const boards = new Resource(() => radioApi.boards());
	const status = new Resource((signal) => radioApi.status(cid ?? '', signal));
	const nodes = new Resource((signal) => radioApi.nodes(cid ?? '', signal));

	let cid = $state<string | null>(null);
	let tab = $state<Tab>('status');
	let dm = $state<string | null>(null);

	const id = $derived(cid ?? '');
	const board = $derived(boards.data?.boards.find((b) => b.id === cid) ?? null);
	const connected = $derived(board?.state === 'connected');
	const tabs = $derived([
		{ value: 'status' as Tab, label: m.adm_cli_tab_status() },
		{ value: 'messages' as Tab, label: m.adm_cli_tab_messages() },
		{ value: 'nodes' as Tab, label: m.adm_cli_tab_nodes() },
		...(isAdmin
			? [
					{ value: 'channels' as Tab, label: m.adm_cli_tab_channels() },
					{ value: 'config' as Tab, label: m.adm_cli_tab_config() },
					{ value: 'backups' as Tab, label: m.adm_cli_tab_backups() }
				]
			: [])
	]);

	onMount(() => {
		void boards.load().then((d) => {
			if (!d || cid) return;
			cid = (d.boards.find((b) => b.state === 'connected') ?? d.boards[0])?.id ?? null;
		});
		boards.poll(30_000);
		return () => {
			boards.dispose();
			status.dispose();
			nodes.dispose();
		};
	});

	$effect(() => {
		// Cada placa: estado cada 30 s y nodos cada 60 s mientras esté conectada.
		if (!cid || !connected) return;
		void status.load();
		void nodes.load();
		status.poll(30_000);
		nodes.poll(60_000);
		return () => {
			status.stopPolling();
			nodes.stopPolling();
		};
	});

	function pick(next: string): void {
		if (next === cid) return;
		status.data = null;
		nodes.data = null;
		dm = null;
		cid = next;
	}

	function refresh(): void {
		void boards.load();
		if (connected) {
			void status.load();
			void nodes.load();
		}
	}
</script>

<PageHeader slug="cliente">
	{#snippet actions()}
		<Button size="sm" variant="ghost" icon={RefreshCw} loading={status.loading} onclick={refresh}
			>{m.adm_reload()}</Button
		>
	{/snippet}
</PageHeader>

<div class="adm-stack">
	{#if boards.error && !boards.data}
		<ProblemNote error={boards.error} onretry={() => boards.load()} />
	{:else if !boards.data}
		<Skeleton lines={6} label={m.loading()} />
	{:else if !boards.data.boards.length}
		<Panel>
			<p class="adm-muted">
				{m.adm_cli_no_boards()}
				<a class="adm-link" href="/admin/radio">{m.admin_section_radio()}</a>
			</p>
		</Panel>
	{:else}
		{#if boards.data.boards.length > 1}
			<Segmented
				label={m.adm_cli_board()}
				options={boards.data.boards.map((b) => ({
					value: b.id,
					label: `${b.short_name || b.long_name || b.id} · ${b.via}`
				}))}
				value={id}
				onchange={pick}
			/>
		{/if}

		{#if board && !connected}
			<p class="adm-note warn" role="alert">
				{m.adm_cli_not_connected({
					id: board.id,
					state: connectorStateLabel(board.state).toLowerCase()
				})}
				<a class="adm-link" href="/admin/radio">{m.admin_section_radio()}</a>
			</p>
		{:else if status.error && !status.data}
			<ProblemNote error={status.error} onretry={() => status.load()} />
		{:else if !status.data}
			<Skeleton lines={8} label={m.loading()} />
		{:else}
			<Segmented label={m.adm_cli_sections()} options={tabs} bind:value={tab} />
			{#key cid}
				{#if tab === 'status'}
					<ClientStatus cid={id} status={status.data} {isAdmin} onchange={() => status.load()} />
				{:else if tab === 'messages'}
					<ClientMessages
						cid={id}
						status={status.data}
						{isAdmin}
						nodes={nodes.data?.nodes ?? []}
						bind:dm
					/>
				{:else if tab === 'nodes'}
					{#if nodes.error && !nodes.data}
						<ProblemNote error={nodes.error} onretry={() => nodes.load()} />
					{:else if !nodes.data}
						<Skeleton lines={8} label={m.loading()} />
					{:else}
						<ClientNodes
							cid={id}
							nodes={nodes.data.nodes}
							canTx={isAdmin && status.data.tx_enabled && status.data.node.tx_enabled}
							onmessage={(node) => {
								dm = node;
								tab = 'messages';
							}}
						/>
					{/if}
				{:else if tab === 'channels' && isAdmin}
					<ClientChannels
						cid={id}
						channels={status.data.channels}
						remote={status.data.remote}
						onchange={() => status.load()}
					/>
				{:else if tab === 'config' && isAdmin}
					<ClientConfig cid={id} remote={status.data.remote} onchange={() => status.load()} />
				{:else if tab === 'backups' && isAdmin}
					<ClientBackups cid={id} remote={status.data.remote} onchange={() => status.load()} />
				{/if}
			{/key}
		{/if}
	{/if}
</div>
