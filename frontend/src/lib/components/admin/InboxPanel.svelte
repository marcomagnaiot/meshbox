<!--
  Mensajes en el Panel (ADR 0022): los últimos que recibieron las placas del Cliente
  Meshtastic, de todos los canales y los directos, con los sin leer marcados. Cada uno lleva a
  su conversación.
-->
<script lang="ts">
	import CheckCheck from '@lucide/svelte/icons/check-check';
	import { problemText } from '$lib/admin/errors';
	import { convLabel, countLabel, inbox, inboxHref, senderLabel } from '$lib/admin/inbox.svelte';
	import { fmt } from '$lib/i18n/fmt.svelte';
	import { m } from '$lib/paraglide/messages';
	import { toasts } from '$lib/stores/ui.svelte';
	import Button from '$lib/components/ui/Button.svelte';
	import NodeTag from '$lib/components/ui/NodeTag.svelte';
	import Panel from './Panel.svelte';

	const d = $derived(inbox.data);
	const multi = $derived((d?.boards ?? 0) > 1);
	let marking = $state(false);

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

{#if d && (d.boards || d.latest.length)}
	<Panel
		title={m.adm_inbox_panel()}
		description={d.unread ? m.adm_inbox_unread_n({ n: countLabel(d.unread) }) : m.adm_inbox_none()}
	>
		{#snippet actions()}
			{#if d.unread}
				<Button size="sm" variant="ghost" icon={CheckCheck} loading={marking} onclick={markAll}
					>{m.adm_inbox_mark_all()}</Button
				>
			{/if}
			<a class="adm-link" href="/admin/cliente?tab=mensajes">{m.adm_inbox_go()}</a>
		{/snippet}
		{#if d.latest.length}
			<ul class="msgs">
				{#each d.latest as x (`${x.cid}:${x.seq}`)}
					<li>
						<a class="msg" class:unread={x.unread} href={inboxHref(x)}>
							<span class="dot" aria-hidden="true"></span>
							{#if x.unread}<span class="sr">{m.adm_inbox_unread()}</span>{/if}
							<time datetime={new Date(x.ts * 1000).toISOString()} title={fmt.dateTime(x.ts)}
								>{fmt.relative(x.ts)}</time
							>
							<span class="conv">{convLabel(x)}{multi ? ` · ${x.boards.join(' · ')}` : ''}</span>
							<span class="body">
								<NodeTag id={x.from} label={senderLabel(x)} />
								<span class="text">{x.text}</span>
							</span>
						</a>
					</li>
				{/each}
			</ul>
		{:else}
			<p class="adm-muted">{m.adm_inbox_empty()}</p>
		{/if}
	</Panel>
{/if}

<style>
	.msgs {
		list-style: none;
		margin: 0;
		padding: 0;
		display: flex;
		flex-direction: column;
	}

	.msg {
		position: relative;
		display: grid;
		grid-template-columns: 10px 92px minmax(120px, 200px) minmax(0, 1fr);
		align-items: center;
		gap: 4px 12px;
		padding: 8px 10px;
		border-radius: var(--r-sm);
		color: inherit;
		text-decoration: none;
	}

	.msg:hover,
	.msg:focus-visible {
		background: var(--fill-1);
	}

	.dot {
		width: 8px;
		height: 8px;
		border-radius: 50%;
	}

	.unread .dot {
		background: var(--accent);
	}

	.unread .text,
	.unread .conv {
		font-weight: 650;
	}

	time,
	.conv {
		color: var(--text-2);
		font-size: 0.8125rem;
		white-space: nowrap;
		overflow: hidden;
		text-overflow: ellipsis;
	}

	time {
		font-variant-numeric: tabular-nums;
	}

	.unread .conv {
		color: var(--text-1);
	}

	.body {
		display: flex;
		align-items: center;
		gap: 8px;
		min-width: 0;
	}

	.text {
		min-width: 0;
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}

	.sr {
		position: absolute;
		width: 1px;
		height: 1px;
		overflow: hidden;
		clip-path: inset(50%);
		white-space: nowrap;
	}

	@media (max-width: 640px) {
		.msg {
			grid-template-columns: 10px auto minmax(0, 1fr);
		}

		.body {
			grid-column: 2 / -1;
		}
	}
</style>
