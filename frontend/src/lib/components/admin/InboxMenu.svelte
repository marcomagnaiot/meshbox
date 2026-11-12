<!--
  Mensajes nuevos en la barra del panel (ADR 0022): el ícono lleva la cuenta de lo que llegó a
  las placas del Cliente Meshtastic y no se leyó, en cualquier pantalla, y abre la lista por
  conversación. Cada una lleva a la conversación en el Cliente.
-->
<script lang="ts">
	import { Popover } from 'bits-ui';
	import MessageSquare from '@lucide/svelte/icons/message-square';
	import { countLabel, convLabel, inbox, inboxHref, senderLabel } from '$lib/admin/inbox.svelte';
	import { problemText } from '$lib/admin/errors';
	import { fmt } from '$lib/i18n/fmt.svelte';
	import { m } from '$lib/paraglide/messages';
	import { toasts } from '$lib/stores/ui.svelte';
	import NodeTag from '$lib/components/ui/NodeTag.svelte';
	import DeviceNotifications from './DeviceNotifications.svelte';

	let open = $state(false);
	let marking = $state(false);

	const d = $derived(inbox.data);
	const multi = $derived((d?.boards ?? 0) > 1);

	async function markAll(): Promise<void> {
		marking = true;
		try {
			await inbox.markAll();
			toasts.show(m.adm_inbox_marked(), { kind: 'success' });
		} catch (err) {
			toasts.show(problemText(err), { kind: 'error' });
		} finally {
			marking = false;
		}
	}
</script>

{#if d && (d.boards || d.unread)}
	<Popover.Root bind:open>
		<Popover.Trigger
			class="btn-icon inbox-trigger"
			aria-label={m.adm_inbox_button({ n: d.unread })}
			title={m.adm_inbox_button({ n: d.unread })}
		>
			<MessageSquare size={20} aria-hidden="true" />
			{#if d.unread}
				{#key d.unread}<span class="inbox-count" aria-hidden="true">{countLabel(d.unread)}</span
					>{/key}
			{/if}
		</Popover.Trigger>
		<Popover.Portal>
			<Popover.Content
				class="menu-surface inbox-menu"
				side="bottom"
				align="end"
				sideOffset={10}
				collisionPadding={12}
			>
				<div class="head">
					<p class="menu-heading">{m.adm_inbox_title()}</p>
					{#if d.unread}
						<button type="button" class="adm-link mark" disabled={marking} onclick={markAll}
							>{m.adm_inbox_mark_all()}</button
						>
					{/if}
				</div>
				{#if d.conversations.length}
					<ul>
						{#each d.conversations as c (c.key)}
							<li>
								<a class="conv" href={inboxHref(c)} onclick={() => (open = false)}>
									<span class="line">
										{#if c.dm}<NodeTag id={c.peer} label={c.short || c.peer || '?'} />{/if}
										<strong class="name">{convLabel(c)}</strong>
										<span class="unread">{countLabel(c.unread)}</span>
									</span>
									<span class="line sub">
										<span class="text">{c.dm ? '' : `${senderLabel(c.last)}: `}{c.last.text}</span>
										<time datetime={new Date(c.last.ts * 1000).toISOString()}
											>{fmt.relative(c.last.ts)}</time
										>
									</span>
									{#if multi}<span class="boards">{c.boards.join(' · ')}</span>{/if}
								</a>
							</li>
						{/each}
					</ul>
				{:else}
					<p class="adm-muted empty">{m.adm_inbox_none()}</p>
				{/if}
				<a class="adm-link all" href="/admin/cliente?tab=mensajes" onclick={() => (open = false)}
					>{m.adm_inbox_go()}</a
				>
				<DeviceNotifications compact />
			</Popover.Content>
		</Popover.Portal>
	</Popover.Root>
{/if}

<style>
	:global(.inbox-trigger) {
		position: relative;
	}

	.inbox-count {
		position: absolute;
		top: 4px;
		right: 2px;
		min-width: 18px;
		height: 18px;
		padding: 0 5px;
		border-radius: 999px;
		background: var(--accent);
		color: var(--on-accent);
		font-size: 0.6875rem;
		font-weight: 700;
		line-height: 18px;
		text-align: center;
		animation: inbox-pop var(--dur-2) var(--ease);
	}

	@keyframes inbox-pop {
		from {
			transform: scale(0.6);
		}
	}

	:global(.inbox-menu) {
		width: min(360px, calc(100vw - 24px));
	}

	.head {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 8px;
	}

	.mark {
		margin-right: 8px;
		padding: 0;
		border: 0;
		background: none;
		font: inherit;
		font-size: 0.8125rem;
		cursor: pointer;
	}

	ul {
		list-style: none;
		margin: 0;
		padding: 0;
	}

	.conv {
		display: flex;
		flex-direction: column;
		gap: 2px;
		padding: 8px 10px;
		border-radius: var(--r-sm);
		color: inherit;
		text-decoration: none;
	}

	.conv:hover,
	.conv:focus-visible {
		background: var(--fill-1);
	}

	.line {
		display: flex;
		align-items: center;
		gap: 8px;
		min-width: 0;
	}

	.name,
	.text {
		flex: 1;
		min-width: 0;
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}

	.unread {
		min-width: 20px;
		padding: 0 6px;
		border-radius: 999px;
		background: var(--accent);
		color: var(--on-accent);
		font-size: 0.75rem;
		font-weight: 700;
		text-align: center;
	}

	.sub,
	.boards {
		font-size: 0.8125rem;
		color: var(--text-2);
	}

	.sub time {
		flex: none;
		font-variant-numeric: tabular-nums;
	}

	.boards {
		font-size: 0.75rem;
	}

	.empty {
		margin: 4px 10px 8px;
	}

	.all {
		display: block;
		margin: 6px 10px 4px;
		font-size: 0.875rem;
	}

	@media (prefers-reduced-motion: reduce) {
		.inbox-count {
			animation: none;
		}
	}
</style>
