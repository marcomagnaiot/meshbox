<!--
  Canales (18.2): nombre, clave (solo escritura) y si es público. Solo lo que llega por un
  canal público se muestra en el sitio; la clave sirve para descifrar los paquetes.
-->
<script lang="ts">
	import Pencil from '@lucide/svelte/icons/pencil';
	import Plus from '@lucide/svelte/icons/plus';
	import Trash2 from '@lucide/svelte/icons/trash-2';
	import { onMount } from 'svelte';
	import * as adminApi from '$lib/admin/api';
	import { problemFields, problemText } from '$lib/admin/errors';
	import { Resource } from '$lib/admin/resource.svelte';
	import type { RadioChannel } from '$lib/admin/types';
	import { m } from '$lib/paraglide/messages';
	import { toasts } from '$lib/stores/ui.svelte';
	import Button from '$lib/components/ui/Button.svelte';
	import Modal from '$lib/components/ui/Modal.svelte';
	import Skeleton from '$lib/components/ui/Skeleton.svelte';
	import Toggle from '$lib/components/ui/Toggle.svelte';
	import ConfirmAction from '$lib/components/admin/ConfirmAction.svelte';
	import PageHeader from '$lib/components/admin/PageHeader.svelte';
	import Panel from '$lib/components/admin/Panel.svelte';
	import ProblemNote from '$lib/components/admin/ProblemNote.svelte';
	import SecretField from '$lib/components/admin/SecretField.svelte';
	import TextField from '$lib/components/admin/TextField.svelte';

	const list = new Resource(() => adminApi.channels.list());
	let formOpen = $state(false);
	let editing = $state<RadioChannel | null>(null);
	let name = $state('');
	let key = $state('');
	let isPublic = $state(false);
	let saving = $state(false);
	let fieldErrors = $state<Record<string, string>>({});
	let formError = $state<string | null>(null);
	let deleting = $state<RadioChannel | null>(null);
	let deleteOpen = $state(false);

	onMount(() => {
		void list.load();
		return () => list.dispose();
	});

	function openForm(ch: RadioChannel | null): void {
		editing = ch;
		name = ch?.name ?? '';
		key = '';
		isPublic = ch?.is_public ?? false;
		fieldErrors = {};
		formError = null;
		formOpen = true;
	}

	function validate(): boolean {
		const errs: Record<string, string> = {};
		if (!name.trim()) errs.name = m.adm_required();
		else if (name.length > 11) errs.name = m.adm_max_length({ max: 11 });
		if (key && !/^[A-Za-z0-9+/]+={0,2}$/.test(key.trim())) errs.key = m.adm_channel_key_invalid();
		fieldErrors = errs;
		return Object.keys(errs).length === 0;
	}

	async function save(e: Event): Promise<void> {
		e.preventDefault();
		if (!validate()) return;
		saving = true;
		formError = null;
		const body = { name: name.trim(), key: key.trim() || undefined, is_public: isPublic };
		try {
			if (editing) await adminApi.channels.update(editing.id, body);
			else await adminApi.channels.create(body);
			toasts.show(m.adm_saved(), { kind: 'success' });
			formOpen = false;
			await list.load();
		} catch (err) {
			fieldErrors = problemFields(err);
			formError = problemText(err);
		} finally {
			saving = false;
		}
	}
</script>

<PageHeader slug="canales">
	{#snippet actions()}
		<Button size="sm" variant="primary" icon={Plus} onclick={() => openForm(null)}
			>{m.adm_channel_add()}</Button
		>
	{/snippet}
</PageHeader>

<div class="adm-stack">
	<p class="adm-note">{m.adm_channels_intro()}</p>
	{#if list.error && !list.data}
		<ProblemNote error={list.error} onretry={() => list.load()} />
	{:else if !list.data}
		<Skeleton lines={4} label={m.loading()} />
	{:else if list.data.channels.length === 0}
		<Panel><p class="adm-muted">{m.adm_channels_empty()}</p></Panel>
	{:else}
		<ul class="cards">
			{#each list.data.channels as ch (ch.id)}
				<li>
					<Panel title={ch.name}>
						{#snippet actions()}
							<Button
								size="sm"
								icon={Pencil}
								onclick={() => openForm(ch)}
								aria-label="{m.adm_edit()} {ch.name}">{m.adm_edit()}</Button
							>
							<Button
								size="sm"
								variant="ghost"
								icon={Trash2}
								aria-label="{m.adm_delete()} {ch.name}"
								onclick={() => {
									deleting = ch;
									deleteOpen = true;
								}}>{m.adm_delete()}</Button
							>
						{/snippet}
						<div class="adm-row">
							{#if ch.is_public}
								<span class="adm-badge ok">{m.adm_channel_public()}</span>
							{:else}
								<span class="adm-badge">{m.adm_channel_private()}</span>
							{/if}
							<span class="adm-badge {ch.has_key ? '' : 'warn'}"
								>{ch.has_key ? m.adm_channel_has_key() : m.adm_channel_no_key()}</span
							>
							{#if ch.hash !== null}<span class="adm-muted adm-mono">hash {ch.hash}</span>{/if}
						</div>
					</Panel>
				</li>
			{/each}
		</ul>
	{/if}
</div>

<Modal
	bind:open={formOpen}
	title={editing ? m.adm_channel_edit_title({ name: editing.name }) : m.adm_channel_add()}
>
	<form id="channel-form" class="adm-stack" onsubmit={save} novalidate>
		<TextField
			label={m.adm_name()}
			hint={m.adm_channel_name_hint()}
			bind:value={name}
			maxlength={11}
			required
			error={fieldErrors.name}
			autocomplete="off"
		/>
		<SecretField
			label={m.adm_channel_key()}
			hint={m.adm_channel_key_hint()}
			bind:value={key}
			isSet={Boolean(editing?.has_key)}
			error={fieldErrors.key}
		/>
		<Toggle
			label={m.adm_channel_public()}
			hint={m.adm_channel_public_hint()}
			bind:checked={isPublic}
		/>
		{#if formError}<p class="adm-note danger" role="alert">{formError}</p>{/if}
	</form>
	{#snippet footer()}
		<Button onclick={() => (formOpen = false)}>{m.adm_cancel()}</Button>
		<Button type="submit" form="channel-form" variant="primary" loading={saving}
			>{m.adm_save()}</Button
		>
	{/snippet}
</Modal>

{#if deleting}
	<ConfirmAction
		bind:open={deleteOpen}
		title={m.adm_channel_delete_title({ name: deleting.name })}
		description={m.adm_channel_delete_desc()}
		confirmLabel={m.adm_delete()}
		danger
		action={() => adminApi.channels.remove(deleting!.id)}
		onsuccess={() => {
			toasts.show(m.adm_deleted(), { kind: 'success' });
			void list.load();
		}}
	/>
{/if}

<style>
	.cards {
		list-style: none;
		margin: 0;
		padding: 0;
		display: grid;
		grid-template-columns: repeat(auto-fill, minmax(min(100%, 320px), 1fr));
		gap: 16px;
	}
</style>
