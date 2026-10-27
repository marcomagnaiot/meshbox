<!--
  Mensajes de la placa como en la app: una conversación por canal configurado y una por cada
  nodo con el que hubo mensajes directos. El historial queda en la base de la Pi (ADR 0016):
  llega aunque nadie tenga el panel abierto y se ve igual desde cualquier dispositivo; lo leído
  también se guarda allá, por usuario. Se consulta lo nuevo cada 3 s. Enviar transmite por radio
  en dos pasos y respeta el límite de la sección 22 (1 cada 30 s, 20 por hora).
-->
<script lang="ts">
	import Send from '@lucide/svelte/icons/send';
	import { onMount, tick, untrack } from 'svelte';
	import { problemText } from '$lib/admin/errors';
	import History from '@lucide/svelte/icons/history';
	import Trash2 from '@lucide/svelte/icons/trash-2';
	import {
		pskKind,
		radioApi,
		unreadCount,
		type BoardMessage,
		type BoardNode,
		type BoardStatus
	} from '$lib/admin/radio';
	import { ApiError } from '$lib/api/client';
	import { fmt } from '$lib/i18n/fmt.svelte';
	import { m } from '$lib/paraglide/messages';
	import { toasts } from '$lib/stores/ui.svelte';
	import { shortFromId } from '$lib/utils/ids';
	import { nodeColorStyle } from '$lib/utils/node-color';
	import Button from '$lib/components/ui/Button.svelte';
	import NodeTag from '$lib/components/ui/NodeTag.svelte';
	import ConfirmAction from '$lib/components/admin/ConfirmAction.svelte';
	import ProblemNote from '$lib/components/admin/ProblemNote.svelte';
	import TextArea from '$lib/components/admin/TextArea.svelte';

	interface Props {
		cid: string;
		status: BoardStatus;
		isAdmin: boolean;
		nodes: BoardNode[];
		/** Conversación directa pedida desde la pestaña Nodos. */
		dm?: string | null;
	}

	let { cid, status, isAdmin, nodes, dm = $bindable(null) }: Props = $props();

	const POLL_MS = 3000;
	const PENDING_S = 120;

	let msgs = $state.raw<BoardMessage[]>([]);
	let lastSeq = 0;
	/** Lo leído por este usuario en cada conversación (se guarda en la Pi). */
	let reads = $state<Record<string, number>>({});
	let more = $state(false);
	let retentionDays = $state<number | null>(null);
	let loadingOlder = $state(false);
	let clearOpen = $state(false);
	let loadError = $state.raw<unknown>(null);
	let loaded = $state(false);
	let active = $state('ch:0');
	/** Último mensaje al que se bajó el hilo (para no saltar al cargar anteriores). */
	let scrolledTo = '';

	let text = $state('');
	let confirming = $state(false);
	let sending = $state(false);
	let sendError = $state<string | null>(null);
	let waitUntil = $state(0);
	let now = $state(Date.now());
	let threadEl: HTMLDivElement | undefined = $state();

	const byId = $derived(new Map(nodes.filter((n) => n.id).map((n) => [n.id as string, n])));
	const channels = $derived(status.channels.filter((c) => c.role !== 'DISABLED'));

	function peerOf(x: BoardMessage): string {
		return (x.direction === 'out' ? x.to : x.from) ?? '?';
	}

	/** Quién lo mandó: los propios, la placa. */
	function senderOf(x: BoardMessage): string | null {
		return x.direction === 'out' ? (status.gateway_id ?? x.from) : x.from;
	}

	function shortOf(id: string | null): string {
		if (!id) return '?';
		return byId.get(id)?.short_name || shortFromId(id);
	}

	function nodeName(id: string | null): string {
		if (!id) return '?';
		const n = byId.get(id);
		if (!n) return id;
		return n.long_name ? `${n.long_name}${n.short_name ? ` (${n.short_name})` : ''}` : id;
	}

	const peers = $derived.by(() => {
		const set = new Set<string>();
		for (const x of msgs) if (x.dm) set.add(peerOf(x));
		if (dm) set.add(dm);
		return [...set];
	});
	const thread = $derived(msgs.filter((x) => x.conv === active));
	const activeChannel = $derived(
		active.startsWith('ch:') ? channels.find((c) => `ch:${c.index}` === active) : undefined
	);
	const dmPeer = $derived(active.startsWith('dm:') ? active.slice(3) : null);
	const isPublic = $derived(activeChannel ? pskKind(activeChannel) !== 'private' : false);
	const textBytes = $derived(new TextEncoder().encode(text).length);
	const waitS = $derived(Math.max(0, Math.ceil((waitUntil - now) / 1000)));
	const canSend = $derived(isAdmin && status.tx_enabled && status.node.tx_enabled);

	function unread(key: string): number {
		return unreadCount(msgs, reads, key);
	}

	function merge(items: BoardMessage[]): void {
		if (!items.length) return;
		const bySeq = new Map(msgs.map((x) => [x.seq, x]));
		for (const it of items) bySeq.set(it.seq, it);
		msgs = [...bySeq.values()].sort((a, b) => a.seq - b.seq);
		lastSeq = Math.max(lastSeq, ...items.map((i) => i.seq));
	}

	/** Lo leído en otro dispositivo también cuenta (solo avanza). */
	function mergeReads(server: Record<string, number>): void {
		let changed = false;
		const next = { ...reads };
		for (const [k, v] of Object.entries(server)) {
			if (v > (next[k] ?? 0)) {
				next[k] = v;
				changed = true;
			}
		}
		if (changed) reads = next;
	}

	async function load(): Promise<void> {
		try {
			const out = await radioApi.messages(cid, {});
			msgs = [];
			lastSeq = 0;
			merge(out.messages);
			more = out.more;
			reads = { ...out.reads };
			retentionDays = out.retention_days;
			loaded = true;
			loadError = null;
		} catch (err) {
			loadError = err;
		}
	}

	async function poll(): Promise<void> {
		if (!loaded) return load();
		// Los enviados hace poco se vuelven a pedir para ver su acuse.
		const recent = Date.now() / 1000 - PENDING_S;
		const pending = msgs.find(
			(x) =>
				x.direction === 'out' &&
				x.ts > recent &&
				(x.status === 'enviado' || (x.dm && x.status === 'retransmitido'))
		);
		try {
			const out = await radioApi.messages(cid, { after: pending ? pending.seq - 1 : lastSeq });
			merge(out.messages);
			mergeReads(out.reads);
			loadError = null;
		} catch (err) {
			loadError = err;
		}
	}

	async function loadOlder(): Promise<void> {
		if (!msgs.length) return;
		loadingOlder = true;
		try {
			const out = await radioApi.messages(cid, { before: msgs[0].seq });
			merge(out.messages);
			more = out.more;
		} catch (err) {
			toasts.show(problemText(err), { kind: 'error' });
		} finally {
			loadingOlder = false;
		}
	}

	onMount(() => {
		if (dm) active = `dm:${dm}`;
		void load();
		const timer = setInterval(() => {
			if (document.visibilityState === 'visible') void poll();
		}, POLL_MS);
		const clock = setInterval(() => (now = Date.now()), 1000);
		return () => {
			clearInterval(timer);
			clearInterval(clock);
		};
	});

	$effect(() => {
		// La conversación abierta, con la pestaña a la vista: leída hasta el último y abajo de todo.
		const key = active;
		const last = thread.length ? thread[thread.length - 1].seq : 0;
		untrack(() => {
			if (last && last > (reads[key] ?? 0) && document.visibilityState === 'visible') {
				reads = { ...reads, [key]: last };
				radioApi.markRead(cid, key, last).catch(() => {
					// sin red: se vuelve a marcar con el próximo mensaje
				});
			}
			const mark = `${key}:${last}`;
			if (mark !== scrolledTo) {
				scrolledTo = mark;
				void tick().then(() => threadEl?.scrollTo({ top: threadEl.scrollHeight }));
			}
		});
	});

	function cleared(): void {
		msgs = [];
		lastSeq = 0;
		reads = {};
		more = false;
		toasts.show(m.adm_cli_cleared(), { kind: 'success' });
	}

	function select(key: string): void {
		active = key;
		confirming = false;
		sendError = null;
		if (!key.startsWith('dm:')) dm = null;
	}

	function review(e: SubmitEvent): void {
		e.preventDefault();
		if (!text.trim() || textBytes > 200) return;
		sendError = null;
		confirming = true;
	}

	async function send(): Promise<void> {
		sending = true;
		sendError = null;
		try {
			const channel = dmPeer ? (byId.get(dmPeer)?.channel ?? 0) : (activeChannel?.index ?? 0);
			await radioApi.send(cid, text.trim(), channel, dmPeer);
			text = '';
			confirming = false;
			waitUntil = Date.now() + 30_000;
			await poll();
		} catch (err) {
			if (err instanceof ApiError && err.status === 429 && err.retryAfter) {
				waitUntil = Date.now() + err.retryAfter * 1000;
			}
			sendError = problemText(err);
		} finally {
			sending = false;
		}
	}

	function statusText(s: string | null): string {
		if (!s) return '';
		if (s === 'enviado') return m.adm_cli_st_sent();
		if (s === 'retransmitido') return m.adm_cli_st_relayed();
		if (s === 'entregado') return m.adm_cli_st_delivered();
		return m.adm_cli_st_error({ reason: s.replace(/^error:\s*/, '') });
	}
</script>

<div class="chat">
	<nav class="convos" aria-label={m.adm_cli_conversations()}>
		<p class="group">{m.adm_cli_channels()}</p>
		{#each channels as c (c.index)}
			{@const key = `ch:${c.index}`}
			{@const n = unread(key)}
			<button type="button" class="convo" class:on={active === key} onclick={() => select(key)}>
				<span class="label"># {c.name || m.adm_cli_channel_n({ n: c.index })}</span>
				<span class="adm-badge {pskKind(c) === 'private' ? 'ok' : 'warn'}"
					>{pskKind(c) === 'private' ? m.adm_cli_private() : m.adm_cli_public()}</span
				>
				{#if n}<span class="count" aria-label={m.adm_cli_unread({ n })}>{n}</span>{/if}
			</button>
		{/each}
		{#if peers.length}
			<p class="group">{m.adm_cli_direct()}</p>
			{#each peers as p (p)}
				{@const key = `dm:${p}`}
				{@const n = unread(key)}
				<button type="button" class="convo" class:on={active === key} onclick={() => select(key)}>
					<NodeTag id={p} label={shortOf(p)} />
					<span class="label">{nodeName(p)}</span>
					{#if n}<span class="count" aria-label={m.adm_cli_unread({ n })}>{n}</span>{/if}
				</button>
			{/each}
		{/if}
	</nav>

	<section class="pane" aria-label={dmPeer ? nodeName(dmPeer) : (activeChannel?.name ?? '')}>
		{#if loadError && !loaded}
			<ProblemNote error={loadError} onretry={poll} />
		{/if}
		<div class="thread" bind:this={threadEl} aria-live="polite">
			{#if more}
				<div class="older">
					<Button
						size="sm"
						variant="ghost"
						icon={History}
						loading={loadingOlder}
						onclick={loadOlder}>{m.adm_cli_load_older()}</Button
					>
				</div>
			{/if}
			{#if loaded && !thread.length}
				<p class="adm-muted empty">{m.adm_cli_no_messages()}</p>
			{/if}
			{#each thread as x (x.seq)}
				{@const sender = senderOf(x)}
				{@const tint = nodeColorStyle(sender)}
				<article class="msg {x.direction}" class:colored={Boolean(tint)} style={tint}>
					<header>
						<span class="who">
							<NodeTag id={sender} label={shortOf(sender)} />
							<strong>{x.direction === 'out' ? m.adm_cli_me() : nodeName(x.from)}</strong>
						</span>
						<time datetime={new Date(x.ts * 1000).toISOString()}>{fmt.time(x.ts)}</time>
					</header>
					<p class="body">{x.text}</p>
					<footer class="adm-muted">
						{#if x.direction === 'out'}
							{statusText(x.status)}
						{:else}
							{[
								x.hops === null
									? null
									: x.hops === 0
										? m.adm_cli_direct_rx()
										: m.adm_cli_hops({ n: x.hops }),
								x.snr === null ? null : `SNR ${fmt.db(x.snr)}`,
								x.rssi === null ? null : `RSSI ${fmt.dbm(x.rssi)}`
							]
								.filter(Boolean)
								.join(' · ')}
						{/if}
					</footer>
				</article>
			{/each}
		</div>

		{#if retentionDays}
			<div class="history">
				<p class="adm-muted">{m.adm_cli_history_note({ days: retentionDays })}</p>
				{#if isAdmin}
					<Button size="sm" variant="ghost" icon={Trash2} onclick={() => (clearOpen = true)}
						>{m.adm_cli_clear_history()}</Button
					>
				{/if}
			</div>
		{/if}

		{#if !isAdmin}
			<p class="adm-muted">{m.adm_cli_read_only()}</p>
		{:else if !status.tx_enabled}
			<p class="adm-note warn" role="note">{m.adm_tx_disabled()}</p>
		{:else if !status.node.tx_enabled}
			<p class="adm-note warn" role="note">{m.adm_cli_radio_tx_off()}</p>
		{:else}
			<form class="compose" onsubmit={review}>
				{#if isPublic && !dmPeer}
					<p class="adm-note warn" role="note">{m.adm_cli_public_warn()}</p>
				{/if}
				<TextArea
					label={dmPeer
						? m.adm_cli_to_node({ name: nodeName(dmPeer) })
						: m.adm_cli_to_channel({ name: activeChannel?.name ?? '' })}
					hint={m.adm_tx_text_count({ chars: text.length, bytes: textBytes })}
					bind:value={text}
					rows={2}
					maxlength={200}
					oninput={() => (confirming = false)}
				/>
				{#if sendError}<p class="adm-note danger" role="alert">{sendError}</p>{/if}
				{#if waitS > 0}<p class="adm-muted" role="status">
						{m.adm_tx_wait({ seconds: waitS })}
					</p>{/if}
				{#if confirming}
					<div class="sendbox" role="group" aria-label={m.adm_tx_preview()}>
						<p>
							{dmPeer
								? m.adm_cli_confirm_dm({ name: nodeName(dmPeer) })
								: m.adm_cli_confirm_channel({ name: activeChannel?.name ?? '' })}
						</p>
						<div class="adm-row end">
							<Button size="sm" variant="ghost" onclick={() => (confirming = false)}
								>{m.adm_cancel()}</Button
							>
							<Button
								size="sm"
								variant="primary"
								icon={Send}
								loading={sending}
								disabled={waitS > 0}
								onclick={send}>{m.adm_tx_send()}</Button
							>
						</div>
					</div>
				{:else}
					<div class="adm-row end">
						<Button
							type="submit"
							size="sm"
							icon={Send}
							disabled={!text.trim() || waitS > 0 || !canSend}>{m.adm_cli_send()}</Button
						>
					</div>
				{/if}
			</form>
		{/if}
	</section>
</div>

<ConfirmAction
	bind:open={clearOpen}
	title={m.adm_cli_clear_title()}
	description={m.adm_cli_clear_desc()}
	confirmLabel={m.adm_cli_clear_history()}
	danger
	requireText={m.adm_cli_clear_word()}
	action={() => radioApi.clearMessages(cid)}
	onsuccess={cleared}
/>

<style>
	.chat {
		display: grid;
		grid-template-columns: 240px minmax(0, 1fr);
		gap: 16px;
		min-height: 420px;
	}

	.convos {
		display: flex;
		flex-direction: column;
		gap: 4px;
		min-width: 0;
	}

	.group {
		margin: 8px 0 2px;
		font-size: 0.75rem;
		font-weight: 650;
		text-transform: uppercase;
		letter-spacing: 0.04em;
		color: var(--text-2);
	}

	.convo {
		display: flex;
		align-items: center;
		gap: 8px;
		padding: 8px 10px;
		border-radius: var(--r-sm);
		border: 1px solid transparent;
		background: none;
		color: inherit;
		font: inherit;
		text-align: start;
		cursor: pointer;
		min-width: 0;
	}

	.convo:hover {
		background: var(--fill-1);
	}

	.convo.on {
		background: var(--fill-2);
		border-color: var(--line);
	}

	.convo .label {
		flex: 1;
		min-width: 0;
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}

	.count {
		min-width: 20px;
		padding: 0 6px;
		border-radius: 999px;
		background: var(--accent);
		color: var(--on-accent);
		font-size: 0.75rem;
		font-weight: 700;
		text-align: center;
	}

	.pane {
		display: flex;
		flex-direction: column;
		gap: 10px;
		min-width: 0;
	}

	.thread {
		display: flex;
		flex-direction: column;
		gap: 8px;
		height: min(56vh, 520px);
		overflow-y: auto;
		padding: 10px;
		border: 1px solid var(--line);
		border-radius: var(--r-sm);
		background: var(--fill-1);
	}

	.empty {
		margin: auto;
	}

	.older {
		display: flex;
		justify-content: center;
	}

	.history {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 8px 12px;
		flex-wrap: wrap;
	}

	.history p {
		margin: 0;
		font-size: 0.8125rem;
	}

	.msg {
		max-width: min(80%, 520px);
		padding: 8px 10px;
		border-radius: 12px;
		background: var(--surface-1);
		border: 1px solid var(--line);
		display: flex;
		flex-direction: column;
		gap: 2px;
	}

	.msg.out {
		align-self: flex-end;
		background: var(--accent-soft);
	}

	/* Cada nodo con su tono (el de la app de Meshtastic), con el brillo del tema. */
	.msg.colored {
		background: oklch(
			var(--node-bubble-l) calc(var(--node-c) * var(--node-bubble-k)) var(--node-h)
		);
	}

	.who {
		display: flex;
		align-items: center;
		gap: 6px;
		min-width: 0;
	}

	.msg header {
		display: flex;
		justify-content: space-between;
		gap: 12px;
		font-size: 0.8125rem;
	}

	.msg time {
		color: var(--text-2);
		font-variant-numeric: tabular-nums;
	}

	.body {
		margin: 0;
		white-space: pre-wrap;
		overflow-wrap: anywhere;
	}

	.msg footer {
		font-size: 0.75rem;
	}

	.compose {
		display: flex;
		flex-direction: column;
		gap: 8px;
	}

	.sendbox {
		padding: 10px 12px;
		border-radius: var(--r-sm);
		border: 1px solid var(--line);
		background: var(--fill-1);
	}

	.sendbox p {
		margin: 0 0 8px;
	}

	@media (max-width: 760px) {
		.chat {
			grid-template-columns: 1fr;
		}

		.convos {
			flex-direction: row;
			overflow-x: auto;
			scrollbar-width: none;
			padding-bottom: 4px;
		}

		.group {
			display: none;
		}

		.convo {
			flex: none;
			max-width: 240px;
		}
	}
</style>
