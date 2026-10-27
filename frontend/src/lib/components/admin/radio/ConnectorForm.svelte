<!--
  Alta y edición de un conector (9, 18.2): MQTT, USB, TCP o reproducción. La contraseña MQTT
  es de solo escritura; el id no se cambia al editar.
-->
<script lang="ts">
	import { untrack } from 'svelte';
	import * as adminApi from '$lib/admin/api';
	import type { ConnectorBody } from '$lib/admin/api';
	import { problemFields, problemText } from '$lib/admin/errors';
	import { connectorKindLabel } from '$lib/admin/labels';
	import type { ConnectorConfig, ConnectorKind, Recording, SerialPortInfo } from '$lib/admin/types';
	import { m } from '$lib/paraglide/messages';
	import Button from '$lib/components/ui/Button.svelte';
	import Segmented from '$lib/components/ui/Segmented.svelte';
	import Toggle from '$lib/components/ui/Toggle.svelte';
	import NumberField from '../NumberField.svelte';
	import SecretField from '../SecretField.svelte';
	import SelectField from '../SelectField.svelte';
	import TagsField from '../TagsField.svelte';
	import TextField from '../TextField.svelte';

	interface Props {
		existing: ConnectorConfig | null;
		ports: SerialPortInfo[];
		recordings: Recording[];
		/** Tópico por defecto (raíz del sitio). */
		defaultTopic: string;
		onsaved: () => void;
		oncancel: () => void;
	}

	let { existing, ports, recordings, defaultTopic, onsaved, oncancel }: Props = $props();

	const ID_RE = /^[a-z0-9][a-z0-9_-]{1,31}$/;
	// Valores iniciales: el formulario se crea de nuevo cada vez que se abre.
	const init = untrack(() => existing);
	let kind = $state<ConnectorKind>(init?.kind ?? 'mqtt');
	let id = $state(init?.id ?? '');
	let enabled = $state(init?.enabled ?? true);
	let host = $state(init?.host ?? '127.0.0.1');
	let port = $state<number | null>(init?.port !== undefined ? Number(init.port) || null : null);
	let username = $state(init?.username ?? '');
	let password = $state('');
	let topics = $state<string[]>(init?.topics ?? []);
	let tls = $state(init?.tls ?? false);
	let serialPort = $state(init?.kind === 'serial' ? String(init.port ?? '') : '');
	let file = $state(init?.file ?? '');
	let speed = $state<number | null>(init?.speed ?? 1);
	let loop = $state(init?.loop ?? false);
	let saving = $state(false);
	let errors = $state<Record<string, string>>({});
	let formError = $state<string | null>(null);

	const portOptions = $derived([
		{ value: '', label: m.adm_serial_choose() },
		...ports.map((p) => ({
			value: String(p.stable_path ?? p.device),
			label: [p.device, p.description].filter(Boolean).join(' — ')
		}))
	]);
	const defaultPort = $derived(kind === 'tcp' ? 4403 : 1883);

	function body(): ConnectorBody {
		const base = { id: id.trim(), enabled };
		switch (kind) {
			case 'mqtt':
				return {
					...base,
					kind: 'mqtt',
					host: host.trim(),
					port: port ?? 1883,
					username: username.trim() || null,
					password: password || (existing?.password ? '********' : null),
					topics,
					tls
				};
			case 'serial':
				return { ...base, kind: 'serial', port: serialPort.trim() };
			case 'tcp':
				return { ...base, kind: 'tcp', host: host.trim(), port: port ?? 4403 };
			default:
				return { ...base, kind: 'replay', file: file.trim(), speed: speed ?? 1, loop };
		}
	}

	function validate(): boolean {
		const e: Record<string, string> = {};
		if (!ID_RE.test(id.trim())) e.id = m.adm_connector_id_invalid();
		if ((kind === 'mqtt' || kind === 'tcp') && !host.trim()) e.host = m.adm_required();
		if (port !== null && (port < 1 || port > 65535)) e.port = m.adm_field_invalid();
		if (kind === 'serial' && !serialPort.trim()) e.port = m.adm_required();
		if (kind === 'replay' && !file.trim()) e.file = m.adm_required();
		if (kind === 'replay' && speed !== null && (speed < 0 || speed > 1000))
			e.speed = m.adm_field_invalid();
		errors = e;
		return Object.keys(e).length === 0;
	}

	async function save(ev: Event): Promise<void> {
		ev.preventDefault();
		if (!validate()) return;
		saving = true;
		formError = null;
		try {
			if (existing) await adminApi.connectors.update(existing.id, body());
			else await adminApi.connectors.create(body());
			onsaved();
		} catch (err) {
			errors = problemFields(err);
			formError = problemText(err);
		} finally {
			saving = false;
		}
	}
</script>

<form class="adm-stack" onsubmit={save} novalidate>
	{#if !existing}
		<Segmented
			label={m.adm_connector_kind()}
			options={(['mqtt', 'serial', 'tcp', 'replay'] as const).map((k) => ({
				value: k,
				label: connectorKindLabel(k)
			}))}
			value={kind}
			onchange={(v) => (kind = v)}
		/>
	{/if}
	<p class="adm-muted">
		{kind === 'mqtt'
			? m.adm_connector_mqtt_help()
			: kind === 'serial'
				? m.adm_connector_serial_help()
				: kind === 'tcp'
					? m.adm_connector_tcp_help()
					: m.adm_connector_replay_help()}
	</p>
	<div class="adm-grid">
		<TextField
			label={m.adm_connector_id()}
			hint={m.adm_connector_id_hint()}
			bind:value={id}
			required
			disabled={Boolean(existing)}
			error={errors.id}
			mono
			autocomplete="off"
		/>
		<Toggle label={m.adm_enabled()} bind:checked={enabled} />
	</div>

	{#if kind === 'mqtt' || kind === 'tcp'}
		<div class="adm-grid">
			<TextField label={m.adm_host()} bind:value={host} required error={errors.host} mono />
			<NumberField
				label={m.adm_port_number()}
				bind:value={port}
				min={1}
				max={65535}
				placeholder={String(defaultPort)}
				error={errors.port}
			/>
		</div>
	{/if}
	{#if kind === 'mqtt'}
		<div class="adm-grid">
			<TextField label={m.adm_mqtt_username()} bind:value={username} autocomplete="off" mono />
			<SecretField
				label={m.admin_password()}
				bind:value={password}
				isSet={existing?.password === '********'}
				error={errors.password}
			/>
		</div>
		<TagsField
			label={m.adm_mqtt_topics()}
			hint={m.adm_mqtt_topics_hint({ topic: defaultTopic })}
			bind:values={topics}
			max={10}
			noComma
			mono
			error={errors.topics}
		/>
		<Toggle label={m.adm_mqtt_tls()} hint={m.adm_mqtt_tls_hint()} bind:checked={tls} />
	{/if}
	{#if kind === 'serial'}
		<div class="adm-grid">
			<SelectField
				label={m.adm_serial_detected()}
				options={portOptions}
				bind:value={serialPort}
				hint={ports.length ? undefined : m.adm_serial_none()}
			/>
			<TextField
				label={m.adm_serial_port()}
				hint={m.adm_serial_port_hint()}
				bind:value={serialPort}
				required
				error={errors.port}
				mono
			/>
		</div>
	{/if}
	{#if kind === 'replay'}
		<div class="adm-grid">
			{#if recordings.length}
				<SelectField
					label={m.adm_recordings()}
					options={[
						{ value: '', label: m.adm_choose() },
						...recordings.map((r) => ({ value: r.name, label: r.name }))
					]}
					bind:value={file}
				/>
			{/if}
			<TextField
				label={m.adm_replay_file()}
				hint={m.adm_replay_file_hint()}
				bind:value={file}
				required
				error={errors.file}
				mono
			/>
			<NumberField
				label={m.adm_replay_speed()}
				hint={m.adm_replay_speed_hint()}
				bind:value={speed}
				min={0}
				max={1000}
				step="any"
				error={errors.speed}
			/>
			<Toggle label={m.adm_replay_loop()} bind:checked={loop} />
		</div>
	{/if}
	{#if formError}<p class="adm-note danger" role="alert">{formError}</p>{/if}
	<div class="adm-row end">
		<Button onclick={oncancel}>{m.adm_cancel()}</Button>
		<Button type="submit" variant="primary" loading={saving}>{m.adm_save()}</Button>
	</div>
</form>
