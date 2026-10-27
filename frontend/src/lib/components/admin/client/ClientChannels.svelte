<!--
  Canales de la placa (los 8 lugares del firmware). Cambiar el nombre o la clave deja de
  entenderse con los demás nodos del canal, y la bajada por MQTT abre una vía de inyección:
  esos cambios piden doble confirmación. Antes de cada cambio se guarda una copia de la placa.
-->
<script lang="ts">
	import Pencil from '@lucide/svelte/icons/pencil';
	import Plus from '@lucide/svelte/icons/plus';
	import Trash2 from '@lucide/svelte/icons/trash-2';
	import { problemText } from '$lib/admin/errors';
	import { pskKind, radioApi, type BoardChannel, type ChannelBody } from '$lib/admin/radio';
	import { m } from '$lib/paraglide/messages';
	import { toasts } from '$lib/stores/ui.svelte';
	import Button from '$lib/components/ui/Button.svelte';
	import Modal from '$lib/components/ui/Modal.svelte';
	import Toggle from '$lib/components/ui/Toggle.svelte';
	import ConfirmAction from '$lib/components/admin/ConfirmAction.svelte';
	import NumberField from '$lib/components/admin/NumberField.svelte';
	import Panel from '$lib/components/admin/Panel.svelte';
	import SelectField from '$lib/components/admin/SelectField.svelte';
	import TextField from '$lib/components/admin/TextField.svelte';
	import DangerConfirm from './DangerConfirm.svelte';
	import { DangerGate } from './danger.svelte';

	interface Props {
		cid: string;
		channels: BoardChannel[];
		remote: boolean;
		onchange: () => void;
	}

	let { cid, channels, remote, onchange }: Props = $props();

	type KeyMode = 'keep' | 'random' | 'default' | 'none' | 'custom';
	const gate = new DangerGate();
	const used = $derived(channels.filter((c) => c.role !== 'DISABLED'));
	const free = $derived(channels.some((c) => c.role === 'DISABLED' && c.index > 0));

	let formOpen = $state(false);
	let editing = $state<BoardChannel | null>(null);
	let name = $state('');
	let keyMode = $state<KeyMode>('keep');
	let customKey = $state('');
	let uplink = $state(false);
	let downlink = $state(false);
	let precision = $state<number | null>(0);
	let muted = $state(false);
	let saving = $state(false);
	let formError = $state<string | null>(null);
	let deleting = $state<BoardChannel | null>(null);
	let deleteOpen = $state(false);

	const nameBytes = $derived(new TextEncoder().encode(name).length);

	function openForm(ch: BoardChannel | null): void {
		editing = ch;
		name = ch ? (ch.custom_name ? ch.name : '') : '';
		keyMode = ch ? 'keep' : 'random';
		customKey = '';
		uplink = ch?.uplink ?? false;
		downlink = ch?.downlink ?? false;
		precision = ch?.position_precision ?? 0;
		muted = ch?.muted ?? false;
		formError = null;
		formOpen = true;
	}

	function body(): ChannelBody | null {
		if (nameBytes > 11) {
			formError = m.adm_max_length({ max: 11 });
			return null;
		}
		if (!editing && !name.trim()) {
			formError = m.adm_cli_channel_name_required();
			return null;
		}
		if (keyMode === 'custom' && !/^[A-Za-z0-9+/]+={0,2}$/.test(customKey.trim())) {
			formError = m.adm_channel_key_invalid();
			return null;
		}
		const out: ChannelBody = {
			uplink,
			downlink,
			position_precision: precision ?? 0,
			muted
		};
		// El primario sin nombre usa el del preset: solo se manda si se escribió uno.
		if (!editing || name.trim() || editing.custom_name) out.name = name.trim();
		if (keyMode !== 'keep') out.psk = keyMode === 'custom' ? customKey.trim() : keyMode;
		return out;
	}

	function saved(changed: string[] | null, backup: string | null): void {
		formOpen = false;
		toasts.show(changed && !changed.length ? m.adm_cli_no_changes() : m.adm_cli_saved_backup(), {
			kind: 'success'
		});
		if (backup) onchange();
	}

	async function save(e: SubmitEvent): Promise<void> {
		e.preventDefault();
		formError = null;
		const b = body();
		if (!b) return;
		saving = true;
		try {
			if (editing) {
				const index = editing.index;
				await gate.run(
					() => radioApi.writeChannel(cid, index, b),
					() => radioApi.writeChannel(cid, index, b, true),
					(r) => saved(r.changed, r.backup)
				);
			} else {
				const r = await radioApi.addChannel(cid, b);
				saved(null, r.backup);
			}
		} catch (err) {
			formError = problemText(err);
		} finally {
			saving = false;
		}
	}

	function keyLabel(c: BoardChannel): string {
		const k = pskKind(c);
		return k === 'private'
			? m.adm_cli_private()
			: k === 'open'
				? m.adm_cli_open()
				: m.adm_cli_public();
	}
</script>

<div class="adm-stack">
	<p class="adm-note" role="note">{m.adm_cli_channels_intro()}</p>
	{#if remote}<p class="adm-note warn" role="note">{m.adm_cli_remote_limits()}</p>{/if}

	<Panel title={m.adm_cli_channels()} flush>
		{#snippet actions()}
			<Button size="sm" icon={Plus} disabled={!free} onclick={() => openForm(null)}
				>{m.adm_cli_add_channel()}</Button
			>
		{/snippet}
		<ul class="list">
			{#each used as c (c.index)}
				<li>
					<div class="info">
						<strong>{c.index}. {c.name || '—'}</strong>
						<span class="badges">
							<span class="adm-badge"
								>{c.role === 'PRIMARY' ? m.adm_cli_primary() : m.adm_cli_secondary()}</span
							>
							<span class="adm-badge {pskKind(c) === 'private' ? 'ok' : 'warn'}">{keyLabel(c)}</span
							>
							{#if c.uplink}<span class="adm-badge accent">{m.adm_cli_uplink()}</span>{/if}
							{#if c.downlink}<span class="adm-badge danger">{m.adm_cli_downlink()}</span>{/if}
							<span class="adm-badge"
								>{c.position_precision
									? m.adm_cli_precision_n({ n: c.position_precision })
									: m.adm_cli_no_position()}</span
							>
							{#if c.muted}<span class="adm-badge">{m.adm_cli_muted()}</span>{/if}
						</span>
					</div>
					<div class="adm-row">
						<Button size="sm" variant="ghost" icon={Pencil} onclick={() => openForm(c)}
							>{m.adm_edit()}</Button
						>
						{#if c.role !== 'PRIMARY'}
							<Button
								size="sm"
								variant="ghost"
								icon={Trash2}
								disabled={remote}
								onclick={() => {
									deleting = c;
									deleteOpen = true;
								}}>{m.adm_delete()}</Button
							>
						{/if}
					</div>
				</li>
			{/each}
		</ul>
	</Panel>
</div>

<Modal
	bind:open={formOpen}
	title={editing ? m.adm_cli_edit_channel({ n: editing.index }) : m.adm_cli_add_channel()}
>
	<form class="adm-stack" onsubmit={save}>
		<TextField
			label={m.adm_name()}
			hint={editing?.role === 'PRIMARY'
				? m.adm_cli_primary_name_hint()
				: m.adm_cli_channel_name_hint({ bytes: nameBytes })}
			bind:value={name}
			maxlength={11}
		/>
		<SelectField
			label={m.adm_cli_key()}
			bind:value={keyMode}
			options={[
				...(editing ? [{ value: 'keep' as KeyMode, label: m.adm_cli_key_keep() }] : []),
				{ value: 'random', label: m.adm_cli_key_random() },
				{ value: 'default', label: m.adm_cli_key_default() },
				{ value: 'none', label: m.adm_cli_key_none() },
				{ value: 'custom', label: m.adm_cli_key_custom() }
			]}
		/>
		{#if keyMode === 'custom'}
			<TextField label={m.adm_cli_key_base64()} bind:value={customKey} mono autocomplete="off" />
		{/if}
		<NumberField
			label={m.adm_cli_precision()}
			hint={m.adm_cli_precision_hint()}
			bind:value={precision}
			min={0}
			max={32}
			step={1}
		/>
		<Toggle label={m.adm_cli_uplink()} hint={m.adm_cli_uplink_hint()} bind:checked={uplink} />
		<Toggle label={m.adm_cli_downlink()} hint={m.adm_cli_downlink_hint()} bind:checked={downlink} />
		<Toggle label={m.adm_cli_muted()} hint={m.adm_cli_muted_hint()} bind:checked={muted} />
		{#if formError}<p class="adm-note danger" role="alert">{formError}</p>{/if}
		<p class="adm-muted">{m.adm_cli_backup_note()}</p>
		<div class="adm-row end">
			<Button variant="ghost" onclick={() => (formOpen = false)}>{m.adm_cancel()}</Button>
			<Button type="submit" variant="primary" loading={saving}>{m.adm_save()}</Button>
		</div>
	</form>
</Modal>

<DangerConfirm {gate} {remote} />

{#if deleting}
	<ConfirmAction
		bind:open={deleteOpen}
		title={m.adm_cli_delete_channel({ name: deleting.name })}
		description={m.adm_cli_delete_channel_desc()}
		confirmLabel={m.adm_delete()}
		danger
		requireText={deleting.name || String(deleting.index)}
		action={() => radioApi.deleteChannel(cid, deleting?.index ?? -1)}
		onsuccess={() => {
			toasts.show(m.adm_cli_saved_backup(), { kind: 'success' });
			onchange();
		}}
	/>
{/if}

<style>
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
		padding: 12px 16px;
		border-top: 1px solid var(--line);
		flex-wrap: wrap;
	}

	.list li:first-child {
		border-top: none;
	}

	.info {
		display: flex;
		flex-direction: column;
		gap: 6px;
		min-width: 0;
	}

	.badges {
		display: flex;
		flex-wrap: wrap;
		gap: 6px;
	}
</style>
