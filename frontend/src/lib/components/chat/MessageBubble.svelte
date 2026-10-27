<!--
  Burbuja de mensaje (17.1): chip del nodo (enlace a su ficha), hora, respuesta citada y
  reacciones como chips. El texto viene de la radio: se muestra siempre como texto. Cada nodo
  tiene su color (el de la app de Meshtastic): en el chip y, suavizado, de fondo de la burbuja.
-->
<script lang="ts">
	import CornerDownRight from '@lucide/svelte/icons/corner-down-right';
	import type { Message } from '$lib/api/types';
	import { fmt } from '$lib/i18n/fmt.svelte';
	import { m } from '$lib/paraglide/messages';
	import { clock } from '$lib/stores/clock.svelte';
	import { live } from '$lib/stores/live.svelte';
	import { site } from '$lib/stores/site.svelte';
	import type { Reaction } from '$lib/stores/chat-items';
	import { nodeHref, shortFromId } from '$lib/utils/ids';
	import { nodeColorStyle } from '$lib/utils/node-color';
	import { shortName } from '$lib/utils/nodes';
	import { classify } from '$lib/utils/status';
	import { truncate } from '$lib/utils/text';
	import NodeTag from '$lib/components/ui/NodeTag.svelte';
	import StatusGlyph from '$lib/components/ui/StatusGlyph.svelte';

	interface Props {
		message: Message;
		replyTo?: Message | null;
		reactions?: Reaction[];
		/** Burbuja seguida del mismo emisor: sin repetir el chip. */
		grouped?: boolean;
	}

	let { message, replyTo, reactions = [], grouped = false }: Props = $props();

	const node = $derived(live.node(message.from));
	const sender = $derived(
		message.from_name ||
			(node ? node.long_name || node.short_name : null) ||
			m.chat_unknown_sender()
	);
	const chip = $derived(node ? shortName(node) : shortFromId(message.from));
	const status = $derived(
		node ? classify(node.last_heard, clock.now, site.data.thresholds) : 'inactive'
	);
	const replyName = $derived(replyTo ? replyTo.from_name || shortFromId(replyTo.from) : null);
	const tint = $derived(nodeColorStyle(message.from));

	function names(list: Message[]): string {
		return list.map((r) => r.from_name || shortFromId(r.from)).join(', ');
	}
</script>

<div class="msg" class:grouped id="msg-{message.pk}">
	{#if !grouped}
		<div class="who">
			<a class="chip" href={nodeHref(message.from)} title={m.chat_open_node({ name: sender })}>
				<StatusGlyph {status} infra={node?.is_infra} fixed={node?.is_fixed} size={14} />
				<NodeTag id={message.from} label={chip} />
			</a>
			<span class="sender">{sender}</span>
		</div>
	{/if}
	<div class="bubble" class:colored={Boolean(tint)} style={tint}>
		{#if replyTo !== undefined}
			<a class="reply" href={replyTo ? `#msg-${replyTo.pk}` : undefined}>
				<CornerDownRight size={14} aria-hidden="true" />
				{#if replyTo}
					<span class="reply-text"
						><span class="reply-name">{m.chat_reply_to({ name: replyName ?? '' })}:</span>
						{truncate(replyTo.text, 80)}</span
					>
				{:else}
					<span class="reply-text">{m.chat_reply_unknown()}</span>
				{/if}
			</a>
		{/if}
		<p class="text">{message.text}</p>
		<time class="time" datetime={new Date(message.ts * 1000).toISOString()}
			>{fmt.time(message.ts)}</time
		>
	</div>
	{#if reactions.length}
		<ul class="reactions" aria-label={m.chat_reactions()}>
			{#each reactions as r (r.emoji)}
				<li
					class="reaction"
					title={m.chat_reaction_label({ emoji: r.emoji, names: names(r.from) })}
				>
					<span aria-hidden="true">{r.emoji}</span>
					{#if r.from.length > 1}<span class="n tabular" aria-hidden="true">{r.from.length}</span
						>{/if}
					<span class="sr-only"
						>{m.chat_reaction_label({ emoji: r.emoji, names: names(r.from) })}</span
					>
				</li>
			{/each}
		</ul>
	{/if}
</div>

<style>
	.msg {
		display: flex;
		flex-direction: column;
		align-items: flex-start;
		gap: 4px;
		max-width: min(560px, 92%);
		scroll-margin: 80px;
	}

	.msg:target .bubble {
		outline: 2px solid var(--accent);
	}

	.msg.grouped {
		margin-top: -4px;
	}

	.who {
		display: flex;
		align-items: center;
		gap: 8px;
		min-width: 0;
		max-width: 100%;
	}

	.chip {
		display: inline-flex;
		align-items: center;
		gap: 4px;
		min-height: 28px;
		padding: 2px 0;
		border-radius: 999px;
		color: var(--text-1);
		text-decoration: none;
		font-size: 0.75rem;
		font-weight: 700;
		position: relative;
	}

	.chip::after {
		content: '';
		position: absolute;
		inset: -8px -4px;
	}

	.sender {
		font-size: 0.75rem;
		color: var(--text-2);
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}

	.bubble {
		position: relative;
		padding: 8px 12px 6px;
		border-radius: 4px var(--r-md) var(--r-md) var(--r-md);
		background: var(--fill-2);
		min-width: 80px;
	}

	/* Fondo con el tono del nodo y el brillo del tema (tokens --node-bubble-* en app.css). */
	.bubble.colored {
		background: oklch(
			var(--node-bubble-l) calc(var(--node-c) * var(--node-bubble-k)) var(--node-h)
		);
	}

	.reply {
		display: flex;
		align-items: flex-start;
		gap: 6px;
		margin: 0 0 6px;
		padding: 4px 8px;
		border-left: 3px solid var(--accent);
		border-radius: 4px;
		background: var(--fill-1);
		color: var(--text-2);
		font-size: 0.75rem;
		text-decoration: none;
	}

	.reply-name {
		font-weight: 650;
		color: var(--text-1);
	}

	.text {
		margin: 0;
		font-size: 0.9375rem;
		line-height: 1.45;
		white-space: pre-wrap;
		overflow-wrap: anywhere;
	}

	.time {
		display: block;
		margin-top: 2px;
		text-align: right;
		font-size: 0.75rem;
		color: var(--text-2);
	}

	.reactions {
		list-style: none;
		margin: -10px 0 0 8px;
		padding: 0;
		display: flex;
		flex-wrap: wrap;
		gap: 4px;
	}

	.reaction {
		display: inline-flex;
		align-items: center;
		gap: 3px;
		min-height: 24px;
		padding: 0 8px;
		border-radius: 999px;
		background: var(--surface-3);
		border: 1px solid var(--line);
		font-size: 0.875rem;
	}

	.n {
		font-size: 0.75rem;
		font-weight: 650;
	}
</style>
