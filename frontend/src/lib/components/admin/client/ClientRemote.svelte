<!--
  Administración remota de nodos propios por la malla (ADR 0017), como en la app Meshtastic:
  configuración sección por sección, nombre, posición fija y reinicio. El nodo acepta solo si
  tiene cargada la clave pública de esta placa. Cada pedido viaja por radio (con varios saltos
  tarda decenas de segundos), así que las secciones se leen de a una y a pedido.
-->
<script lang="ts">
	import Download from '@lucide/svelte/icons/download';
	import MapPin from '@lucide/svelte/icons/map-pin';
	import Pencil from '@lucide/svelte/icons/pencil';
	import RadioTower from '@lucide/svelte/icons/radio-tower';
	import RotateCcw from '@lucide/svelte/icons/rotate-ccw';
	import Save from '@lucide/svelte/icons/save';
	import Undo2 from '@lucide/svelte/icons/undo-2';
	import { untrack } from 'svelte';
	import { problemText } from '$lib/admin/errors';
	import {
		changedValues,
		radioApi,
		sectionValues,
		type BoardNode,
		type RemoteInfo,
		type RemoteProbe,
		type RemoteSection
	} from '$lib/admin/radio';
	import { Busy } from '$lib/admin/resource.svelte';
	import { fmt } from '$lib/i18n/fmt.svelte';
	import { m } from '$lib/paraglide/messages';
	import { toasts } from '$lib/stores/ui.svelte';
	import Button from '$lib/components/ui/Button.svelte';
	import Skeleton from '$lib/components/ui/Skeleton.svelte';
	import ConfirmAction from '$lib/components/admin/ConfirmAction.svelte';
	import CopyBlock from '$lib/components/admin/CopyBlock.svelte';
	import KeyValue from '$lib/components/admin/KeyValue.svelte';
	import Panel from '$lib/components/admin/Panel.svelte';
	import ProblemNote from '$lib/components/admin/ProblemNote.svelte';
	import SelectField from '$lib/components/admin/SelectField.svelte';
	import ConfigField from './ConfigField.svelte';
	import DangerConfirm from './DangerConfirm.svelte';
	import { DangerGate } from './danger.svelte';
	import { sectionLabel } from './labels';
	import OwnerDialog from './OwnerDialog.svelte';
	import PositionDialog from './PositionDialog.svelte';

	interface Props {
		cid: string;
		nodes: BoardNode[];
		/** Clave pública de la placa conectada (la que se carga en cada nodo). */
		publicKey: string | null;
		/** Panel abierto desde internet: los cambios peligrosos no se permiten. */
		remote: boolean;
		/** Nodo elegido (también llega desde Nodos o Mensajes). */
		node?: string | null;
	}

	let { cid, nodes, publicKey, remote, node = $bindable(null) }: Props = $props();

	const busy = new Busy();
	const gate = new DangerGate();
	let info = $state.raw<RemoteInfo | null>(null);
	let infoError = $state.raw<unknown>(null);
	let probe = $state.raw<RemoteProbe | null>(null);
	let probeError = $state<string | null>(null);
	let probing = $state(false);
	let sectionName = $state('lora');
	let section = $state.raw<RemoteSection | null>(null);
	let reading = $state(false);
	let readError = $state<string | null>(null);
	let original = $state.raw<Record<string, unknown>>({});
	let draft = $state<Record<string, unknown>>({});
	let saving = $state(false);
	let saveError = $state<string | null>(null);
	let ownerOpen = $state(false);
	let fixOpen = $state(false);
	let rebootOpen = $state(false);

	const candidates = $derived(
		nodes
			.filter((n) => !n.is_self && n.id)
			.sort((a, b) => (b.last_heard ?? 0) - (a.last_heard ?? 0))
	);
	const known = $derived(candidates.find((n) => n.id === node) ?? null);
	const nodeOptions = $derived([
		{ value: '', label: m.adm_cli_remote_pick() },
		...candidates.map((n) => ({
			value: n.id as string,
			label: `${n.long_name || n.short_name || n.id} · ${n.id}`
		}))
	]);
	const sectionOptions = $derived(
		(info?.sections ?? []).map((s) => ({
			value: s.name,
			label: `${s.kind === 'config' ? m.adm_cli_kind_config() : m.adm_cli_kind_module()} · ${sectionLabel(s.name)}`
		}))
	);
	const shown = $derived(section && section.name === sectionName ? section : null);
	const changes = $derived(shown ? changedValues(shown.fields, original, draft) : {});
	const dirty = $derived(Object.keys(changes).length > 0);
	const waiting = $derived(probing || reading || saving || busy.any);
	const title = $derived(
		info?.long_name || info?.short_name || known?.long_name || node || m.adm_cli_remote_node()
	);

	$effect(() => {
		// Otro nodo: se olvida lo leído del anterior y se pide lo que sabe la placa de este.
		const id = node;
		untrack(() => {
			info = null;
			infoError = null;
			probe = null;
			probeError = null;
			section = null;
			readError = null;
			saveError = null;
		});
		if (!id) return;
		const ctrl = new AbortController();
		radioApi
			.remoteInfo(cid, id, ctrl.signal)
			.then((d) => (info = d))
			.catch((err) => {
				if (!ctrl.signal.aborted) infoError = err;
			});
		return () => ctrl.abort();
	});

	function show(s: RemoteSection): void {
		section = s;
		original = sectionValues(s.fields);
		draft = { ...original };
		saveError = null;
	}

	async function runProbe(): Promise<void> {
		if (!node) return;
		const id = node;
		probing = true;
		probe = null;
		probeError = null;
		try {
			const out = await radioApi.remoteProbe(cid, id);
			if (node === id) probe = out;
		} catch (err) {
			if (node === id) probeError = problemText(err);
		} finally {
			probing = false;
		}
	}

	async function read(): Promise<void> {
		if (!node) return;
		const id = node;
		const target = sectionName;
		reading = true;
		readError = null;
		try {
			const out = await radioApi.remoteRead(cid, id, target);
			if (node === id) show(out);
		} catch (err) {
			if (node === id) readError = problemText(err);
		} finally {
			reading = false;
		}
	}

	async function save(): Promise<void> {
		if (!node || !shown || !dirty) return;
		const id = node;
		const target = shown.name;
		const values = changes;
		saving = true;
		saveError = null;
		try {
			await gate.run(
				() => radioApi.remoteWrite(cid, id, target, values),
				() => radioApi.remoteWrite(cid, id, target, values, true),
				(r) => {
					if (!r.changed.length) {
						toasts.show(m.adm_cli_no_changes(), { kind: 'info' });
					} else if (r.verified === true) {
						toasts.show(m.adm_cli_remote_verified(), { kind: 'success' });
					} else if (r.verified === null) {
						toasts.show(m.adm_cli_remote_unverified(), { kind: 'info', timeout: 10_000 });
					} else {
						toasts.show(m.adm_cli_remote_mismatch({ fields: r.mismatch.join(', ') }), {
							kind: 'warning',
							timeout: 10_000
						});
					}
					if (r.section) show(r.section);
					else original = { ...draft };
				}
			);
		} catch (err) {
			saveError = problemText(err);
		} finally {
			saving = false;
		}
	}

	async function saveOwner(longName: string, shortName: string): Promise<boolean> {
		if (!node) return false;
		const id = node;
		const out = await busy.run('owner', () => radioApi.remoteOwner(cid, id, longName, shortName), {
			success: m.adm_cli_remote_owner_saved()
		});
		if (out && info) info = { ...info, long_name: out.long_name, short_name: out.short_name };
		return Boolean(out);
	}

	async function saveFix(lat: number, lon: number, alt: number): Promise<boolean> {
		if (!node) return false;
		const id = node;
		const out = await busy.run('fix', () => radioApi.remotePosition(cid, id, lat, lon, alt), {
			success: m.adm_cli_remote_fix_saved()
		});
		return Boolean(out);
	}
</script>

<div class="adm-stack">
	<p class="adm-note" role="note">{m.adm_cli_remote_intro()}</p>

	<Panel title={m.adm_cli_remote_key_title()} description={m.adm_cli_remote_key_desc()}>
		<div class="adm-stack">
			{#if publicKey}
				<CopyBlock text={publicKey} label={m.adm_cli_remote_key_title()} inline />
			{:else}
				<p class="adm-note warn" role="note">{m.adm_cli_remote_no_key()}</p>
			{/if}
			<ol class="steps">
				<li>{m.adm_cli_remote_step1()}</li>
				<li>{m.adm_cli_remote_step2()}</li>
				<li>{m.adm_cli_remote_step3()}</li>
			</ol>
		</div>
	</Panel>

	<SelectField
		label={m.adm_cli_remote_node()}
		value={node ?? ''}
		options={nodeOptions}
		onchange={(v) => (node = v || null)}
	/>

	{#if node}
		{#if infoError && !info}
			<ProblemNote error={infoError} />
		{:else if !info}
			<Skeleton lines={4} label={m.loading()} />
		{:else}
			<Panel {title} description={info.node}>
				{#snippet actions()}
					<Button size="sm" icon={RadioTower} loading={probing} onclick={runProbe}
						>{m.adm_cli_remote_probe()}</Button
					>
				{/snippet}
				<div class="adm-stack">
					<KeyValue
						columns={3}
						items={[
							{ label: m.adm_cli_hw(), value: info.hw_model ?? '—' },
							{ label: m.adm_role(), value: info.role, mono: true },
							{ label: m.adm_last_heard(), value: fmt.relative(info.last_heard) },
							{
								label: m.adm_cli_hops_col(),
								value:
									info.hops === null ? '—' : info.hops === 0 ? m.adm_cli_direct_rx() : info.hops
							},
							{ label: 'SNR', value: fmt.db(info.snr) },
							{
								label: m.adm_cli_remote_node_key(),
								value: info.has_pki ? m.adm_cli_remote_key_known() : m.adm_cli_remote_key_missing()
							}
						]}
					/>
					{#if !info.has_pki}
						<p class="adm-note warn" role="note">{m.adm_cli_remote_no_pki()}</p>
					{/if}
					{#if probe}
						<p class="adm-note ok" role="status">
							{m.adm_cli_remote_probe_ok({
								seconds: fmt.number(probe.seconds, 1),
								firmware: probe.firmware,
								role: String(probe.role)
							})}
						</p>
					{/if}
					{#if probeError}<p class="adm-note danger" role="alert">{probeError}</p>{/if}
					<div class="adm-row">
						<Button size="sm" icon={Pencil} onclick={() => (ownerOpen = true)}
							>{m.adm_cli_rename()}</Button
						>
						<Button size="sm" icon={MapPin} onclick={() => (fixOpen = true)}
							>{m.adm_cli_fix_position()}</Button
						>
						<Button size="sm" icon={RotateCcw} onclick={() => (rebootOpen = true)}
							>{m.adm_cli_remote_reboot()}</Button
						>
					</div>
				</div>
			</Panel>

			<Panel title={m.adm_cli_remote_config()} tone={shown?.danger ? 'danger' : 'default'}>
				<div class="adm-stack">
					<div class="adm-row pick">
						<SelectField
							label={m.adm_cli_section()}
							bind:value={sectionName}
							options={sectionOptions}
						/>
						<Button icon={Download} loading={reading} onclick={read}
							>{m.adm_cli_remote_read()}</Button
						>
					</div>
					{#if readError}<p class="adm-note danger" role="alert">{readError}</p>{/if}
					{#if shown}
						<p class="adm-muted">{m.adm_cli_remote_read_at({ time: fmt.time(shown.read_at) })}</p>
						{#if !shown.writable}
							<p class="adm-note" role="note">{m.adm_cli_remote_readonly()}</p>
						{:else if shown.name === 'lora'}
							<p class="adm-note" role="note">{m.adm_cli_remote_lora_locked()}</p>
						{/if}
						{#if shown.danger}
							<p class="adm-note warn" role="note">{m.adm_cli_section_danger()}</p>
						{/if}
						{#key shown}
							<div class="fields">
								{#each shown.fields as f (f.name)}
									<ConfigField
										field={f}
										path={f.name}
										get={(p) => draft[p]}
										set={(p, v) => (draft[p] = v)}
										disabled={!shown.writable}
									/>
								{/each}
							</div>
						{/key}
						{#if saveError}<p class="adm-note danger" role="alert">{saveError}</p>{/if}
						{#if shown.writable}
							<p class="adm-muted">{m.adm_cli_remote_backup_note()}</p>
							<div class="adm-row end">
								<Button
									size="sm"
									variant="ghost"
									icon={Undo2}
									disabled={!dirty || saving}
									onclick={() => (draft = { ...original })}>{m.adm_cli_discard()}</Button
								>
								<Button
									size="sm"
									variant="primary"
									icon={Save}
									loading={saving}
									disabled={!dirty}
									onclick={save}>{m.adm_save()}</Button
								>
							</div>
						{/if}
					{:else if !readError}
						<p class="adm-muted">{m.adm_cli_remote_read_hint()}</p>
					{/if}
				</div>
			</Panel>
		{/if}
	{/if}

	{#if waiting}
		<p class="adm-muted" role="status">{m.adm_cli_remote_waiting()}</p>
	{/if}
</div>

<DangerConfirm {gate} {remote} node />

<OwnerDialog
	bind:open={ownerOpen}
	title={m.adm_cli_remote_rename_title({ name: title })}
	initial={{ long_name: info?.long_name ?? null, short_name: info?.short_name ?? null }}
	note={m.adm_cli_remote_slow()}
	onsave={saveOwner}
/>

<PositionDialog
	bind:open={fixOpen}
	title={m.adm_cli_remote_fix_title({ name: title })}
	description={m.adm_cli_remote_fix_desc()}
	initial={{ lat: known?.lat ?? null, lon: known?.lon ?? null, alt: 0 }}
	note={m.adm_cli_remote_slow()}
	onsave={saveFix}
/>

<ConfirmAction
	bind:open={rebootOpen}
	title={m.adm_cli_remote_reboot_title({ name: title })}
	description={m.adm_cli_remote_reboot_desc()}
	confirmLabel={m.adm_cli_remote_reboot()}
	action={() => radioApi.remoteReboot(cid, node ?? '')}
	onsuccess={() => toasts.show(m.adm_cli_remote_rebooting(), { kind: 'success' })}
/>

<style>
	.steps {
		margin: 0;
		padding-left: 20px;
		list-style: decimal;
		display: flex;
		flex-direction: column;
		gap: 6px;
		font-size: 0.875rem;
		color: var(--text-2);
	}

	.pick {
		align-items: flex-end;
	}

	.pick > :global(:first-child) {
		flex: 1 1 260px;
	}

	.fields {
		display: grid;
		grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
		gap: 14px 18px;
		align-items: start;
	}

	.fields :global(.adm-fieldset) {
		grid-column: 1 / -1;
	}
</style>
