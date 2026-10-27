<!--
  Copias de la configuración de la placa: se hace una sola antes de cada cambio (las últimas 30)
  y se puede hacer a mano. Incluyen las claves de los canales y de la placa: descargarlas o
  restaurarlas solo se permite desde la red local.
-->
<script lang="ts">
	import Download from '@lucide/svelte/icons/download';
	import History from '@lucide/svelte/icons/history';
	import Plus from '@lucide/svelte/icons/plus';
	import { onMount } from 'svelte';
	import { radioApi, type BoardBackup } from '$lib/admin/radio';
	import { Busy, Resource } from '$lib/admin/resource.svelte';
	import { fmt } from '$lib/i18n/fmt.svelte';
	import { m } from '$lib/paraglide/messages';
	import { toasts } from '$lib/stores/ui.svelte';
	import Button from '$lib/components/ui/Button.svelte';
	import Skeleton from '$lib/components/ui/Skeleton.svelte';
	import ConfirmAction from '$lib/components/admin/ConfirmAction.svelte';
	import Panel from '$lib/components/admin/Panel.svelte';
	import ProblemNote from '$lib/components/admin/ProblemNote.svelte';

	interface Props {
		cid: string;
		remote: boolean;
		onchange: () => void;
	}

	let { cid, remote, onchange }: Props = $props();

	const list = new Resource(() => radioApi.backups(cid));
	const busy = new Busy();
	let restoring = $state<BoardBackup | null>(null);
	let restoreOpen = $state(false);

	onMount(() => {
		void list.load();
		return () => list.dispose();
	});

	/** `0a0b0c0d-20261025-101500-antes-de-lora.json` → `antes de lora`. */
	function reason(name: string): string {
		const parts = name.replace(/\.json$/, '').split('-');
		return parts.slice(3).join(' ') || '—';
	}

	async function create(): Promise<void> {
		const out = await busy.run('create', () => radioApi.createBackup(cid), {
			success: m.adm_cli_backup_done()
		});
		if (out) void list.load();
	}
</script>

<div class="adm-stack">
	<p class="adm-note" role="note">{m.adm_cli_backups_intro()}</p>
	{#if remote}<p class="adm-note warn" role="note">{m.adm_cli_backups_remote()}</p>{/if}

	<Panel title={m.adm_cli_backups()} flush>
		{#snippet actions()}
			<Button size="sm" icon={Plus} loading={busy.is('create')} onclick={create}
				>{m.adm_cli_backup_now()}</Button
			>
		{/snippet}
		{#if list.error && !list.data}
			<div class="pad"><ProblemNote error={list.error} onretry={() => list.load()} /></div>
		{:else if !list.data}
			<div class="pad"><Skeleton lines={4} label={m.loading()} /></div>
		{:else if !list.data.backups.length}
			<p class="adm-muted pad">{m.adm_cli_no_backups()}</p>
		{:else}
			<ul class="list">
				{#each list.data.backups as b (b.name)}
					<li>
						<div class="info">
							<strong>{fmt.dateTime(b.created)}</strong>
							<span class="adm-muted">{reason(b.name)} · {fmt.bytes(b.size)}</span>
						</div>
						<div class="adm-row">
							{#if remote}
								<Button size="sm" variant="ghost" icon={Download} disabled
									>{m.adm_download()}</Button
								>
							{:else}
								<Button
									size="sm"
									variant="ghost"
									icon={Download}
									href={radioApi.backupUrl(cid, b.name)}
									download={b.name}>{m.adm_download()}</Button
								>
							{/if}
							<Button
								size="sm"
								variant="ghost"
								icon={History}
								disabled={remote}
								onclick={() => {
									restoring = b;
									restoreOpen = true;
								}}>{m.adm_cli_restore()}</Button
							>
						</div>
					</li>
				{/each}
			</ul>
		{/if}
	</Panel>
</div>

{#if restoring}
	<ConfirmAction
		bind:open={restoreOpen}
		title={m.adm_cli_restore_title({ when: fmt.dateTime(restoring.created) })}
		description={m.adm_cli_restore_desc()}
		confirmLabel={m.adm_cli_restore()}
		danger
		requireText={m.adm_restore_word()}
		action={() => radioApi.restore(cid, restoring?.name ?? '')}
		onsuccess={(r) => {
			const out = r as { sections: string[]; channels: number[]; owner: boolean };
			toasts.show(
				m.adm_cli_restored({
					sections: out.sections.length,
					channels: out.channels.length
				}),
				{ kind: 'success', timeout: 8000 }
			);
			void list.load();
			onchange();
		}}
	/>
{/if}

<style>
	.pad {
		padding: 14px 16px;
	}

	.list {
		list-style: none;
		margin: 0;
		padding: 0;
	}

	.list li {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 12px;
		padding: 10px 16px;
		border-top: 1px solid var(--line);
		flex-wrap: wrap;
	}

	.list li:first-child {
		border-top: none;
	}

	.info {
		display: flex;
		flex-direction: column;
		gap: 2px;
		min-width: 0;
	}
</style>
