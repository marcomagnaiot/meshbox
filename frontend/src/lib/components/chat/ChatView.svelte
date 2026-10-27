<!--
  Chat del canal público (17.1), solo lectura: separadores de día, respuestas, reacciones,
  búsqueda en lo cargado, paginación hacia atrás y anuncio de mensajes nuevos (aria-live).
-->
<script lang="ts">
	import ArrowDown from '@lucide/svelte/icons/arrow-down';
	import MessageCircle from '@lucide/svelte/icons/message-circle';
	import { tick } from 'svelte';
	import { fmt } from '$lib/i18n/fmt.svelte';
	import { m } from '$lib/paraglide/messages';
	import { buildChatItems, type ChatItem } from '$lib/stores/chat-items';
	import { chat } from '$lib/stores/chat.svelte';
	import { site } from '$lib/stores/site.svelte';
	import { ui } from '$lib/stores/ui.svelte';
	import { shortFromId } from '$lib/utils/ids';
	import { truncate } from '$lib/utils/text';
	import Button from '$lib/components/ui/Button.svelte';
	import EmptyState from '$lib/components/ui/EmptyState.svelte';
	import Skeleton from '$lib/components/ui/Skeleton.svelte';
	import MessageBubble from './MessageBubble.svelte';

	let query = $state('');
	let scroller: HTMLDivElement | undefined = $state();
	let nearBottom = $state(true);
	let unseen = $state(0);
	let announce = $state('');
	let initialScrollDone = false;

	const items = $derived(buildChatItems(chat.messages.values(), (ts) => fmt.dayKey(ts), query));
	const channels = $derived(site.data.public_channels.join(', '));

	$effect(() => {
		void chat.load();
	});

	// Al cargar por primera vez, ir al final (lo más nuevo).
	$effect(() => {
		if (!chat.loaded || initialScrollDone || !scroller) return;
		initialScrollDone = true;
		void tick().then(() => scrollToEnd(false));
	});

	// Mensaje nuevo en vivo: anunciarlo y seguir al final si el lector ya estaba ahí.
	$effect(() => {
		const msg = chat.latestLive;
		if (!msg) return;
		announce = m.chat_new_message({
			name: msg.from_name || shortFromId(msg.from),
			text: truncate(msg.text, 140)
		});
		if (nearBottom) void tick().then(() => scrollToEnd(true));
		else unseen++;
	});

	function scrollToEnd(smooth: boolean) {
		if (!scroller) return;
		scroller.scrollTo({ top: scroller.scrollHeight, behavior: smooth ? 'smooth' : 'auto' });
		unseen = 0;
	}

	function onScroll() {
		if (!scroller) return;
		nearBottom = scroller.scrollHeight - scroller.scrollTop - scroller.clientHeight < 80;
		if (nearBottom) unseen = 0;
	}

	async function loadOlder() {
		if (!scroller) return;
		const before = scroller.scrollHeight;
		await chat.loadOlder();
		await tick();
		// Mantener a la vista lo que se estaba leyendo.
		scroller.scrollTop += scroller.scrollHeight - before;
	}

	function isGrouped(list: ChatItem[], i: number): boolean {
		const cur = list[i];
		const prev = list[i - 1];
		if (cur.kind !== 'message' || !prev || prev.kind !== 'message') return false;
		return (
			prev.message.from === cur.message.from &&
			cur.message.ts - prev.message.ts < 300 &&
			!cur.replyTo
		);
	}
</script>

<section class="chat" aria-labelledby="chat-title">
	<header class="head">
		<!-- En el celular apaisado la pestaña activa ya dice dónde se está: más alto para el chat. -->
		<h1 id="chat-title" class:sr-only={ui.layout === 'landscape'}>{m.chat_title()}</h1>
		<p class="sub" class:sr-only={ui.layout === 'landscape'}>
			{[channels ? m.chat_channel({ name: channels }) : '', m.chat_readonly()]
				.filter(Boolean)
				.join(' · ')}
		</p>
		<input
			type="search"
			class="search"
			placeholder={m.chat_search()}
			aria-label={m.chat_search()}
			bind:value={query}
		/>
	</header>

	<!-- Región desplazable enfocable con teclado (WCAG 2.1.1; regla scrollable-region-focusable de axe). -->
	<!-- svelte-ignore a11y_no_noninteractive_tabindex -->
	<div
		class="scroller"
		bind:this={scroller}
		onscroll={onScroll}
		role="region"
		tabindex="0"
		aria-label={m.chat_messages_label()}
	>
		{#if chat.loading && !chat.loaded}
			<div class="pad"><Skeleton lines={6} avatar label={m.chat_loading()} /></div>
		{:else if chat.error && !chat.loaded}
			<EmptyState icon={MessageCircle} title={m.error_network()}>
				<Button size="sm" onclick={() => chat.load()}>{m.retry()}</Button>
			</EmptyState>
		{:else}
			{#if chat.next && !query}
				<div class="older">
					<Button size="sm" variant="ghost" loading={chat.loadingOlder} onclick={loadOlder}
						>{m.chat_load_older()}</Button
					>
				</div>
			{/if}
			{#if items.length === 0}
				<EmptyState
					icon={MessageCircle}
					title={query ? m.chat_search_empty() : m.chat_empty()}
					compact
				/>
			{:else}
				<ol class="items">
					{#each items as item, i (item.key)}
						<li>
							{#if item.kind === 'day'}
								<div class="day" role="separator"><span>{fmt.day(item.ts)}</span></div>
							{:else if item.kind === 'reaction'}
								<p class="orphan">
									{m.chat_reacted({
										name: item.message.from_name || shortFromId(item.message.from),
										emoji: item.message.text
									})} · <time>{fmt.time(item.message.ts)}</time>
								</p>
							{:else}
								<MessageBubble
									message={item.message}
									replyTo={item.replyTo}
									reactions={item.reactions}
									grouped={isGrouped(items, i)}
								/>
							{/if}
						</li>
					{/each}
				</ol>
			{/if}
		{/if}
	</div>

	{#if unseen > 0}
		<button type="button" class="jump" onclick={() => scrollToEnd(true)}>
			<ArrowDown size={16} aria-hidden="true" />{m.chat_jump_latest()} ({unseen})
		</button>
	{/if}
	<p class="sr-only" aria-live="polite">{announce}</p>
</section>

<style>
	.chat {
		position: relative;
		display: flex;
		flex-direction: column;
		height: 100%;
		min-height: 0;
	}

	.head {
		flex: none;
		display: flex;
		flex-direction: column;
		gap: 4px;
		padding: 8px 16px 10px;
		border-bottom: 1px solid var(--line);
	}

	h1 {
		margin: 0;
		font-size: 1rem;
		font-weight: 700;
	}

	.sub {
		margin: 0;
		font-size: 0.75rem;
		color: var(--text-2);
	}

	.search {
		margin-top: 6px;
		height: 40px;
		padding: 0 12px;
		border-radius: var(--r-sm);
		border: 1px solid var(--line);
		background: var(--fill-1);
		color: var(--text-1);
		font: inherit;
		font-size: 0.875rem;
	}

	@media (pointer: coarse) {
		.search {
			height: 44px;
		}
	}

	.scroller {
		flex: 1;
		min-height: 0;
		overflow-y: auto;
		overscroll-behavior: contain;
		padding: 8px 12px 16px;
	}

	.items {
		list-style: none;
		margin: 0;
		padding: 0;
		display: flex;
		flex-direction: column;
		gap: 10px;
	}

	.day {
		display: flex;
		justify-content: center;
		margin: 6px 0 2px;
	}

	.day span {
		padding: 2px 10px;
		border-radius: 999px;
		background: var(--fill-1);
		font-size: 0.75rem;
		font-weight: 650;
		color: var(--text-2);
	}

	.orphan {
		margin: 0;
		font-size: 0.75rem;
		color: var(--text-2);
		padding-left: 4px;
	}

	.older {
		display: flex;
		justify-content: center;
		margin-bottom: 8px;
	}

	.pad {
		padding: 8px 4px;
	}

	.jump {
		position: absolute;
		bottom: 16px;
		left: 50%;
		transform: translateX(-50%);
		display: inline-flex;
		align-items: center;
		gap: 6px;
		min-height: 40px;
		padding: 0 14px;
		border-radius: 999px;
		border: 1px solid var(--line);
		background: var(--surface-2);
		color: var(--text-1);
		font: inherit;
		font-size: 0.8125rem;
		font-weight: 650;
		box-shadow: 0 6px 20px oklch(0% 0 0 / 0.35);
	}
</style>
