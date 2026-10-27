<!--
  Respaldo (11.6, 18.2): respaldos diarios y manuales, descargar, restaurar (valida con
  integrity_check y guarda antes una copia de seguridad), subir un .db.gz, y exportar o
  importar la configuración (los secretos solo cifrados con contraseña).
-->
<script lang="ts">
	import ArchiveRestore from '@lucide/svelte/icons/archive-restore';
	import Download from '@lucide/svelte/icons/download';
	import FileUp from '@lucide/svelte/icons/file-up';
	import Plus from '@lucide/svelte/icons/plus';
	import Upload from '@lucide/svelte/icons/upload';
	import { onMount } from 'svelte';
	import * as adminApi from '$lib/admin/api';
	import { problemText } from '$lib/admin/errors';
	import { Busy, Resource } from '$lib/admin/resource.svelte';
	import type { BackupFile } from '$lib/admin/types';
	import { fmt } from '$lib/i18n/fmt.svelte';
	import { m } from '$lib/paraglide/messages';
	import { toasts } from '$lib/stores/ui.svelte';
	import { saveBlob } from '$lib/utils/download';
	import Button from '$lib/components/ui/Button.svelte';
	import Skeleton from '$lib/components/ui/Skeleton.svelte';
	import Toggle from '$lib/components/ui/Toggle.svelte';
	import ConfirmAction from '$lib/components/admin/ConfirmAction.svelte';
	import DataTable from '$lib/components/admin/DataTable.svelte';
	import PageHeader from '$lib/components/admin/PageHeader.svelte';
	import Panel from '$lib/components/admin/Panel.svelte';
	import ProblemNote from '$lib/components/admin/ProblemNote.svelte';
	import SecretField from '$lib/components/admin/SecretField.svelte';
	import type { Column } from '$lib/components/admin/types';

	const list = new Resource(() => adminApi.backups.list());
	const busy = new Busy();
	let restoring = $state<BackupFile | null>(null);
	let restoreOpen = $state(false);
	let uploadFile = $state<File | null>(null);
	let uploadOpen = $state(false);
	let uploadInput: HTMLInputElement | null = $state(null);
	let includeSecrets = $state(false);
	let exportPassword = $state('');
	let exportError = $state<string | null>(null);
	let importData = $state<Record<string, unknown> | null>(null);
	let importName = $state('');
	let importPassword = $state('');
	let importOpen = $state(false);
	let importInput: HTMLInputElement | null = $state(null);
	let importError = $state<string | null>(null);
	let lastResult = $state<string | null>(null);

	onMount(() => {
		void list.load();
	});

	const dbTotal = $derived(
		list.data ? list.data.db.db + list.data.db.db_wal + list.data.db.db_shm : null
	);
	const importHasSecrets = $derived(Boolean(importData && 'secrets_encrypted' in importData));

	async function createNow(): Promise<void> {
		const b = await busy.run('create', () => adminApi.backups.create(), {
			success: m.adm_backup_created()
		});
		if (b) void list.load();
	}

	async function exportConfig(): Promise<void> {
		exportError = null;
		if (includeSecrets && exportPassword.length < 10) {
			exportError = m.adm_export_password_short();
			return;
		}
		const out = await busy.run('export', () =>
			adminApi.backups.exportConfig(includeSecrets, includeSecrets ? exportPassword : undefined)
		);
		if (out) {
			saveBlob(out.blob, out.filename);
			exportPassword = '';
		}
	}

	async function pickImport(file: File): Promise<void> {
		importError = null;
		try {
			const data = JSON.parse(await file.text()) as Record<string, unknown>;
			if (data.format !== 'meshbox-config') throw new Error(m.adm_import_not_meshbox());
			importData = data;
			importName = file.name;
		} catch (err) {
			importData = null;
			importError = err instanceof SyntaxError ? m.adm_import_not_json() : problemText(err);
		} finally {
			if (importInput) importInput.value = '';
		}
	}

	const columns: Column<BackupFile>[] = [
		{ key: 'name', label: m.adm_backup_name(), width: 'minmax(260px, 2fr)', cell: nameCell },
		{
			key: 'size',
			label: m.adm_tiles_size(),
			width: '110px',
			align: 'end',
			text: (b) => fmt.bytes(b.size)
		},
		{
			key: 'mtime',
			label: m.adm_when(),
			width: '170px',
			text: (b) => fmt.dateTime(b.mtime),
			sort: (a, b) => a.mtime - b.mtime
		},
		{ key: 'act', label: m.adm_actions(), width: '260px', align: 'end', cell: actionsCell }
	];
</script>

{#snippet nameCell(b: BackupFile)}
	<span class="adm-mono">{b.name}</span>
	{#if b.daily}<span class="adm-badge">{m.adm_backup_daily()}</span>{/if}
{/snippet}

{#snippet actionsCell(b: BackupFile)}
	<span class="adm-row">
		<Button size="sm" icon={Download} href={adminApi.backups.downloadUrl(b.name)} download={b.name}
			>{m.adm_download()}</Button
		>
		<Button
			size="sm"
			icon={ArchiveRestore}
			onclick={() => {
				restoring = b;
				restoreOpen = true;
			}}>{m.adm_restore()}</Button
		>
	</span>
{/snippet}

<PageHeader slug="respaldo">
	{#snippet actions()}
		<Button size="sm" variant="primary" icon={Plus} loading={busy.is('create')} onclick={createNow}
			>{m.adm_backup_create()}</Button
		>
	{/snippet}
</PageHeader>

<div class="adm-stack">
	{#if lastResult}<p class="adm-note ok" role="status">{lastResult}</p>{/if}
	<Panel
		title={m.adm_backups()}
		description={dbTotal !== null ? m.adm_backups_desc({ size: fmt.bytes(dbTotal) }) : undefined}
		flush
	>
		{#if list.error && !list.data}
			<div class="pad"><ProblemNote error={list.error} onretry={() => list.load()} /></div>
		{:else if !list.data}
			<div class="pad"><Skeleton lines={4} label={m.loading()} /></div>
		{:else}
			<DataTable
				rows={list.data.backups}
				{columns}
				rowKey={(b) => b.name}
				label={m.adm_backups()}
				height="auto"
				rowHeight={52}
				minWidth="820px"
				sortKey="mtime"
				sortDir="desc"
			>
				{#snippet empty()}<p class="adm-muted">{m.adm_backups_empty()}</p>{/snippet}
			</DataTable>
		{/if}
	</Panel>

	<Panel title={m.adm_upload_restore()} description={m.adm_upload_restore_desc()} tone="danger">
		<input
			bind:this={uploadInput}
			class="sr-only"
			type="file"
			accept=".gz,application/gzip"
			aria-label={m.adm_upload_restore()}
			onchange={(e) => {
				const f = e.currentTarget.files?.[0];
				if (f) {
					uploadFile = f;
					uploadOpen = true;
				}
			}}
		/>
		<Button icon={Upload} onclick={() => uploadInput?.click()}>{m.adm_upload_pick()}</Button>
	</Panel>

	<div class="adm-grid two">
		<Panel title={m.adm_export()} description={m.adm_export_desc()}>
			<div class="adm-stack">
				<Toggle
					label={m.adm_export_secrets()}
					hint={m.adm_export_secrets_hint()}
					bind:checked={includeSecrets}
				/>
				{#if includeSecrets}
					<SecretField
						label={m.adm_export_password()}
						hint={m.adm_export_password_hint()}
						bind:value={exportPassword}
						autocomplete="new-password"
					/>
				{/if}
				{#if exportError}<p class="adm-note danger" role="alert">{exportError}</p>{/if}
				<div class="adm-row">
					<Button icon={Download} loading={busy.is('export')} onclick={exportConfig}
						>{m.adm_export_action()}</Button
					>
				</div>
			</div>
		</Panel>

		<Panel title={m.adm_import()} description={m.adm_import_desc()}>
			<div class="adm-stack">
				<input
					bind:this={importInput}
					class="sr-only"
					type="file"
					accept=".json,application/json"
					aria-label={m.adm_import()}
					onchange={(e) => {
						const f = e.currentTarget.files?.[0];
						if (f) void pickImport(f);
					}}
				/>
				<div class="adm-row">
					<Button icon={FileUp} onclick={() => importInput?.click()}>{m.adm_import_pick()}</Button>
				</div>
				{#if importData}
					<p class="adm-muted">
						{m.adm_import_file({
							name: importName,
							version: String(importData.meshbox ?? '?'),
							when:
								typeof importData.exported_at === 'number'
									? fmt.dateTime(importData.exported_at)
									: '?'
						})}
					</p>
					{#if importHasSecrets}
						<SecretField
							label={m.adm_import_password()}
							hint={m.adm_import_password_hint()}
							bind:value={importPassword}
							autocomplete="off"
						/>
					{/if}
					<div class="adm-row">
						<Button variant="danger" onclick={() => (importOpen = true)}
							>{m.adm_import_action()}</Button
						>
					</div>
				{/if}
				{#if importError}<p class="adm-note danger" role="alert">{importError}</p>{/if}
			</div>
		</Panel>
	</div>
</div>

{#if restoring}
	<ConfirmAction
		bind:open={restoreOpen}
		title={m.adm_restore_title({ name: restoring.name })}
		description={m.adm_restore_desc()}
		confirmLabel={m.adm_restore()}
		danger
		requireText={m.adm_restore_word()}
		action={() => adminApi.backups.restore(restoring!.name)}
		onsuccess={(r) => {
			const out = r as { restored: string; safety_backup?: string };
			lastResult = m.adm_restore_done({ name: out.restored, safety: out.safety_backup ?? '—' });
			void list.load();
		}}
	/>
{/if}

<ConfirmAction
	bind:open={uploadOpen}
	title={m.adm_upload_title({ name: uploadFile?.name ?? '' })}
	description={m.adm_restore_desc()}
	confirmLabel={m.adm_restore()}
	danger
	requireText={m.adm_restore_word()}
	action={() => adminApi.backups.uploadAndRestore(uploadFile!)}
	onsuccess={(r) => {
		lastResult = m.adm_restore_done({ name: (r as { restored: string }).restored, safety: '—' });
		uploadFile = null;
		if (uploadInput) uploadInput.value = '';
		void list.load();
	}}
/>

<ConfirmAction
	bind:open={importOpen}
	title={m.adm_import_title()}
	description={m.adm_import_confirm()}
	confirmLabel={m.adm_import_action()}
	danger
	action={() => adminApi.backups.importConfig(importData ?? {}, importPassword || undefined)}
	onsuccess={(r) => {
		const out = r as { restart_recommended?: boolean };
		lastResult = out.restart_recommended ? m.adm_import_done_restart() : m.adm_import_done();
		importData = null;
		importPassword = '';
		toasts.show(m.adm_import_done(), { kind: 'success' });
	}}
/>

<style>
	.pad {
		padding: 0 16px 16px;
	}
</style>
