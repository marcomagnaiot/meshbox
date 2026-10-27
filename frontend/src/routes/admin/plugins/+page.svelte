<!--
  Plugins (18.2, 21): los incluidos y los de terceros de la carpeta de plugins, con sus
  permisos, capas, estado, ajustes (formulario desde `settings_schema`, 18.3) y registros.
  Activar un plugin de terceros pide confirmación: corre dentro del servicio.
-->
<script lang="ts">
	import FileText from '@lucide/svelte/icons/file-text';
	import RefreshCw from '@lucide/svelte/icons/refresh-cw';
	import { onMount } from 'svelte';
	import * as adminApi from '$lib/admin/api';
	import { Busy, Resource } from '$lib/admin/resource.svelte';
	import { clean, fieldKind, resolve, validate, withDefaults } from '$lib/admin/schema';
	import type { PluginInfo } from '$lib/admin/types';
	import { fmt } from '$lib/i18n/fmt.svelte';
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
	import SchemaForm from '$lib/components/admin/SchemaForm.svelte';

	const SECRET_MASK = '********';

	interface FormState {
		value: Record<string, unknown>;
		errors: Record<string, string>;
		/** Secretos ya guardados (el campo vacío los conserva). */
		secrets: string[];
		/** Falta algún ajuste obligatorio: el formulario empieza abierto. */
		incomplete: boolean;
	}

	const list = new Resource(() => adminApi.plugins.list());
	const busy = new Busy();
	let forms = $state<Record<string, FormState>>({});
	let confirmPlugin = $state<PluginInfo | null>(null);
	let confirmOpen = $state(false);
	let logsPlugin = $state<PluginInfo | null>(null);
	let logsOpen = $state(false);
	let logs = $state.raw<{ ts: number; level: string; msg: string }[] | null>(null);
	let logsError = $state<unknown>(null);

	onMount(() => {
		void reload();
	});

	async function reload(): Promise<void> {
		const d = await list.load();
		if (!d) return;
		const next: Record<string, FormState> = {};
		for (const p of d.plugins) next[p.id] = forms[p.id] ?? initForm(p);
		forms = next;
	}

	function initForm(p: PluginInfo): FormState {
		const schema = p.settings_schema;
		if (!schema) return { value: {}, errors: {}, secrets: [], incomplete: false };
		const value: Record<string, unknown> = { ...p.settings };
		const secrets: string[] = [];
		for (const [key, prop] of Object.entries(resolve(schema, schema).schema.properties ?? {})) {
			if (fieldKind(prop, schema) !== 'secret') continue;
			if (value[key] === SECRET_MASK) secrets.push(key);
			value[key] = '';
		}
		const full = withDefaults(schema, value);
		const missing = validate(schema, full, schema, '', {
			secretsSet: (path) => secrets.includes(path)
		});
		return { value: full, errors: {}, secrets, incomplete: Object.keys(missing).length > 0 };
	}

	function replace(p: PluginInfo): void {
		if (!list.data) return;
		list.data = { ...list.data, plugins: list.data.plugins.map((x) => (x.id === p.id ? p : x)) };
		forms[p.id] = initForm(p);
	}

	async function setEnabled(p: PluginInfo, enabled: boolean): Promise<void> {
		const out = await busy.run(`enable:${p.id}`, () => adminApi.plugins.update(p.id, { enabled }));
		if (out) {
			replace(out);
			if (out.error) return;
			toasts.show(
				enabled ? m.adm_plugin_enabled({ name: p.name }) : m.adm_plugin_disabled({ name: p.name }),
				{ kind: 'success' }
			);
		}
	}

	function askEnable(p: PluginInfo, enabled: boolean): void {
		if (enabled && !p.builtin) {
			confirmPlugin = p;
			confirmOpen = true;
			return;
		}
		void setEnabled(p, enabled);
	}

	async function save(p: PluginInfo): Promise<void> {
		const schema = p.settings_schema;
		const f = forms[p.id];
		if (!schema || !f) return;
		const errors = validate(schema, f.value, schema, '', {
			secretsSet: (path) => f.secrets.includes(path)
		});
		f.errors = errors;
		if (Object.keys(errors).length) return;
		const out = await busy.run(
			`save:${p.id}`,
			() => adminApi.plugins.update(p.id, { settings: clean(schema, f.value) }),
			{ success: m.adm_saved() }
		);
		if (out) replace(out);
	}

	async function openLogs(p: PluginInfo): Promise<void> {
		logsPlugin = p;
		logs = null;
		logsError = null;
		logsOpen = true;
		try {
			const out = await adminApi.plugins.logs(p.id);
			logs = [...out.logs].reverse();
		} catch (err) {
			logsError = err;
		}
	}

	function permissionLabel(perm: string): string {
		switch (perm) {
			case 'events.read':
				return m.adm_perm_events_read();
			case 'http.outbound':
				return m.adm_perm_http_outbound();
			case 'alerts.raise':
				return m.adm_perm_alerts_raise();
			case 'map.layers':
				return m.adm_perm_map_layers();
			case 'mqtt.publish':
				return m.adm_perm_mqtt_publish();
			case 'nodes.read':
				return m.adm_perm_nodes_read();
			default:
				return perm;
		}
	}

	function levelTone(level: string): string {
		if (level === 'ERROR' || level === 'CRITICAL') return 'danger';
		if (level === 'WARNING') return 'warn';
		return '';
	}
</script>

<PageHeader slug="plugins">
	{#snippet actions()}
		<Button size="sm" icon={RefreshCw} loading={list.loading} onclick={reload}
			>{m.adm_reload()}</Button
		>
	{/snippet}
</PageHeader>

{#if list.error && !list.data}
	<ProblemNote error={list.error} onretry={reload} />
{:else if !list.data}
	<Skeleton lines={6} label={m.loading()} />
{:else}
	<div class="adm-stack">
		<div class="adm-note warn" role="note">
			<p>{list.data.warning}</p>
			<p class="dir">
				{m.adm_plugins_dir()} <code class="adm-mono path">{list.data.user_dir}</code>
			</p>
		</div>

		{#if list.data.plugins.length === 0}
			<p class="adm-muted">{m.adm_plugins_empty()}</p>
		{/if}

		{#each list.data.plugins as p (p.id)}
			{@const f = forms[p.id]}
			<Panel title={p.name} description={p.description ?? undefined}>
				{#snippet actions()}
					<div class="enable">
						<Toggle
							label={m.adm_plugin_active()}
							disabled={busy.is(`enable:${p.id}`)}
							bind:checked={() => p.enabled, (v) => askEnable(p, v)}
						/>
					</div>
				{/snippet}
				<div class="adm-stack">
					<div class="adm-row badges">
						<span class="adm-badge adm-mono">v{p.version}</span>
						<span class="adm-badge {p.builtin ? 'accent' : 'warn'}"
							>{p.builtin ? m.adm_plugin_builtin() : m.adm_plugin_third_party()}</span
						>
						{#if p.error}
							<span class="adm-badge danger">{m.adm_plugin_state_error()}</span>
						{:else if p.running}
							<span class="adm-badge ok">{m.adm_plugin_state_running()}</span>
						{:else}
							<span class="adm-badge">{m.adm_plugin_state_stopped()}</span>
						{/if}
						<span class="adm-muted adm-mono">{p.id}</span>
					</div>

					{#if p.error}
						<p class="adm-note danger" role="alert">{p.error}</p>
					{/if}

					<div class="meta">
						<div>
							<h3>{m.adm_plugin_permissions()}</h3>
							{#if p.permissions.length}
								<ul class="perms">
									{#each p.permissions as perm (perm)}
										<li>
											<span>{permissionLabel(perm)}</span> <code class="adm-muted">{perm}</code>
										</li>
									{/each}
								</ul>
							{:else}
								<p class="adm-muted">{m.adm_plugin_no_permissions()}</p>
							{/if}
						</div>
						{#if p.layers.length}
							<div>
								<h3>{m.adm_plugin_layers()}</h3>
								<ul class="perms">
									{#each p.layers as layer (layer.id)}
										<li>
											{layer.name} <span class="adm-muted">({layer.geometry ?? 'point'})</span>
										</li>
									{/each}
								</ul>
							</div>
						{/if}
					</div>

					{#if p.settings_schema && f}
						<details class="settings" open={f.incomplete || undefined}>
							<summary>{m.adm_plugin_settings()}</summary>
							<form
								class="adm-stack"
								onsubmit={(e) => {
									e.preventDefault();
									void save(p);
								}}
								novalidate
							>
								<SchemaForm
									schema={p.settings_schema}
									bind:value={f.value}
									errors={f.errors}
									secretsSet={(path) => f.secrets.includes(path)}
								/>
								<div class="adm-row end">
									<Button
										type="submit"
										variant="primary"
										size="sm"
										loading={busy.is(`save:${p.id}`)}>{m.adm_save()}</Button
									>
								</div>
							</form>
						</details>
					{/if}

					<div class="adm-row">
						<Button size="sm" variant="ghost" icon={FileText} onclick={() => openLogs(p)}
							>{m.adm_plugin_logs()}</Button
						>
					</div>
				</div>
			</Panel>
		{/each}
	</div>
{/if}

<ConfirmAction
	bind:open={confirmOpen}
	title={m.adm_plugin_enable_title({ name: confirmPlugin?.name ?? '' })}
	description={m.adm_plugin_enable_desc()}
	confirmLabel={m.adm_plugin_enable()}
	danger
	action={async () => {
		const p = confirmPlugin;
		if (!p) return null;
		const out = await adminApi.plugins.update(p.id, { enabled: true });
		replace(out);
		return out;
	}}
>
	{#if confirmPlugin}
		<ul class="perms">
			{#each confirmPlugin.permissions as perm (perm)}
				<li>{permissionLabel(perm)}</li>
			{/each}
		</ul>
	{/if}
</ConfirmAction>

<Modal
	bind:open={logsOpen}
	title={m.adm_plugin_logs_title({ name: logsPlugin?.name ?? '' })}
	description={m.adm_plugin_logs_desc()}
	size="lg"
>
	{#if logsError}
		<ProblemNote error={logsError} onretry={() => logsPlugin && openLogs(logsPlugin)} />
	{:else if !logs}
		<Skeleton lines={4} label={m.loading()} />
	{:else if logs.length === 0}
		<p class="adm-muted">{m.adm_plugin_logs_empty()}</p>
	{:else}
		<ol class="log-list">
			{#each logs as entry, i (i)}
				<li>
					<span class="adm-muted adm-mono">{fmt.dateTime(entry.ts)}</span>
					<span class="adm-badge {levelTone(entry.level)}">{entry.level}</span>
					<span class="adm-mono msg">{entry.msg}</span>
				</li>
			{/each}
		</ol>
	{/if}
	{#if logsError === null && logs && logs.length}
		<p class="adm-muted count">{m.adm_log_count({ count: logs.length })}</p>
	{/if}
</Modal>

<style>
	.dir {
		margin: 6px 0 0;
	}

	.path {
		overflow-wrap: anywhere;
	}

	.adm-note p {
		margin: 0;
	}

	.enable :global(.toggle) {
		gap: 10px;
	}

	.badges {
		gap: 6px;
	}

	.meta {
		display: grid;
		grid-template-columns: repeat(auto-fit, minmax(min(100%, 240px), 1fr));
		gap: 12px 24px;
	}

	h3 {
		margin: 0 0 6px;
		font-size: 0.8125rem;
		font-weight: 650;
		color: var(--text-2);
	}

	.perms {
		margin: 0;
		padding-left: 18px;
		list-style: disc;
		display: flex;
		flex-direction: column;
		gap: 4px;
		font-size: 0.875rem;
	}

	.perms code {
		font-size: 0.75rem;
	}

	.settings summary {
		cursor: pointer;
		padding: 8px 0;
		font-weight: 650;
	}

	.settings form {
		padding-top: 8px;
	}

	.log-list {
		list-style: none;
		margin: 0;
		padding: 0;
		display: flex;
		flex-direction: column;
		gap: 6px;
		max-height: 60vh;
		overflow: auto;
	}

	.log-list li {
		display: grid;
		grid-template-columns: auto auto minmax(0, 1fr);
		gap: 8px;
		align-items: baseline;
		font-size: 0.8125rem;
	}

	.msg {
		white-space: pre-wrap;
		overflow-wrap: anywhere;
	}

	.count {
		margin: 10px 0 0;
	}
</style>
