<!--
  Configuración completa de la placa, sección por sección como en la app, armada desde los
  descriptores que manda el servidor. Se envía solo lo que cambió; antes de escribir se guarda
  una copia de la placa y los campos que pueden dejarla fuera de la red piden doble
  confirmación (desde internet no se permiten).
-->
<script lang="ts">
	import RotateCcw from '@lucide/svelte/icons/rotate-ccw';
	import Save from '@lucide/svelte/icons/save';
	import { onMount } from 'svelte';
	import { problemText } from '$lib/admin/errors';
	import { changedValues, radioApi, sectionValues, type ConfigSection } from '$lib/admin/radio';
	import { Resource } from '$lib/admin/resource.svelte';
	import { m } from '$lib/paraglide/messages';
	import { toasts } from '$lib/stores/ui.svelte';
	import Button from '$lib/components/ui/Button.svelte';
	import Skeleton from '$lib/components/ui/Skeleton.svelte';
	import Panel from '$lib/components/admin/Panel.svelte';
	import ProblemNote from '$lib/components/admin/ProblemNote.svelte';
	import SelectField from '$lib/components/admin/SelectField.svelte';
	import ConfigField from './ConfigField.svelte';
	import DangerConfirm from './DangerConfirm.svelte';
	import { DangerGate } from './danger.svelte';
	import { sectionLabel } from './labels';

	interface Props {
		cid: string;
		remote: boolean;
		onchange: () => void;
	}

	let { cid, remote, onchange }: Props = $props();

	const config = new Resource(() => radioApi.config(cid));
	const gate = new DangerGate();
	let name = $state('lora');
	let original = $state.raw<Record<string, unknown>>({});
	let draft = $state<Record<string, unknown>>({});
	let saving = $state(false);
	let error = $state<string | null>(null);

	const sections = $derived(config.data?.sections ?? []);
	const section = $derived<ConfigSection | undefined>(sections.find((s) => s.name === name));
	const changes = $derived(section ? changedValues(section.fields, original, draft) : {});
	const dirty = $derived(Object.keys(changes).length > 0);
	const options = $derived(
		sections.map((s) => ({
			value: s.name,
			label: `${s.kind === 'config' ? m.adm_cli_kind_config() : m.adm_cli_kind_module()} · ${sectionLabel(s.name)}`
		}))
	);

	onMount(() => {
		void config.load();
		return () => config.dispose();
	});

	$effect.pre(() => {
		// Al cambiar de sección o recargar, el borrador vuelve a lo que tiene la placa.
		if (!section) return;
		const values = sectionValues(section.fields);
		original = values;
		draft = { ...values };
		error = null;
	});

	const get = (path: string) => draft[path];
	const set = (path: string, value: unknown) => (draft[path] = value);

	async function save(): Promise<void> {
		if (!section || !dirty) return;
		const values = changes;
		const target = section.name;
		saving = true;
		error = null;
		try {
			await gate.run(
				() => radioApi.writeSection(cid, target, values),
				() => radioApi.writeSection(cid, target, values, true),
				(r) => {
					toasts.show(r.changed.length ? m.adm_cli_saved_backup() : m.adm_cli_no_changes(), {
						kind: 'success'
					});
					void config.load();
					onchange();
				}
			);
		} catch (err) {
			error = problemText(err);
		} finally {
			saving = false;
		}
	}
</script>

<div class="adm-stack">
	<p class="adm-note" role="note">{m.adm_cli_config_intro()}</p>
	{#if remote}<p class="adm-note warn" role="note">{m.adm_cli_remote_limits()}</p>{/if}

	{#if config.error && !config.data}
		<ProblemNote error={config.error} onretry={() => config.load()} />
	{:else if !config.data}
		<Skeleton lines={8} label={m.loading()} />
	{:else}
		<SelectField label={m.adm_cli_section()} bind:value={name} {options} />
		{#if section}
			<Panel
				title={sectionLabel(section.name)}
				description={section.writable ? undefined : m.adm_cli_section_readonly()}
				tone={section.danger ? 'danger' : 'default'}
			>
				<div class="adm-stack">
					{#if section.danger}
						<p class="adm-note warn" role="note">{m.adm_cli_section_danger()}</p>
					{/if}
					{#key section}
						<div class="fields">
							{#each section.fields as f (f.name)}
								<ConfigField field={f} path={f.name} {get} {set} disabled={!section.writable} />
							{/each}
						</div>
					{/key}
					{#if error}<p class="adm-note danger" role="alert">{error}</p>{/if}
					{#if section.writable}
						<p class="adm-muted">{m.adm_cli_backup_note()} {m.adm_cli_reboot_note()}</p>
						<div class="adm-row end">
							<Button
								size="sm"
								variant="ghost"
								icon={RotateCcw}
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
				</div>
			</Panel>
		{/if}
	{/if}
</div>

<DangerConfirm {gate} {remote} />

<style>
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
