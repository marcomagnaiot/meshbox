<!--
  Paso 5: cómo llegan los paquetes. MQTT (el Heltec por WiFi al broker del equipo: se crean
  las cuentas y se muestran los comandos para configurarlo) y/o USB (nodo conectado a la Pi:
  se elige el puerto y se prueba la conexión). Se pueden elegir ambos.
-->
<script lang="ts">
	import Search from '@lucide/svelte/icons/search';
	import { onMount } from 'svelte';
	import * as adminApi from '$lib/admin/api';
	import { problemText } from '$lib/admin/errors';
	import type { ConnectorTest, HeltecCommands, SerialPortInfo } from '$lib/admin/types';
	import { m } from '$lib/paraglide/messages';
	import type { Wizard } from '$lib/setup/wizard.svelte';
	import Button from '$lib/components/ui/Button.svelte';
	import Toggle from '$lib/components/ui/Toggle.svelte';
	import JsonView from '$lib/components/admin/JsonView.svelte';
	import SelectField from '$lib/components/admin/SelectField.svelte';
	import TextField from '$lib/components/admin/TextField.svelte';
	import MqttSecretView from '$lib/components/admin/radio/MqttSecretView.svelte';
	import StepFrame from './StepFrame.svelte';

	interface Props {
		wizard: Wizard;
	}

	interface RadioResult {
		mqtt?: { username: string; password: string; root: string; heltec: HeltecCommands };
		usb?: { connector: string; port: string };
	}

	let { wizard }: Props = $props();
	const GW_RE = /^[a-z0-9][a-z0-9_-]{1,20}$/;
	const ROOT_RE = /^[A-Za-z0-9_/-]{3,64}$/;
	let mqtt = $state(false);
	let gateway = $state('interior');
	let root = $state('');
	let serialHint = $state('COM5');
	let usb = $state(false);
	let usbPort = $state('');
	let ports = $state.raw<SerialPortInfo[] | null>(null);
	let portsBusy = $state(false);
	let slug = $state('');
	let busy = $state(false);
	let error = $state<string | null>(null);
	let errors = $state<Record<string, string>>({});
	let result = $state.raw<RadioResult | null>(null);
	let test = $state.raw<ConnectorTest | null>(null);
	let testBusy = $state(false);
	/** Si la persona ya tocó los interruptores, la detección no los cambia. */
	let touched = false;

	onMount(() => {
		adminApi.site
			.get()
			.then((d) => (slug = d.slug))
			.catch(() => {});
		// Con un nodo enchufado lo normal es USB; si no aparece ninguno, el Heltec por WiFi.
		void loadPorts(true).then(() => {
			if (touched) return;
			if (ports?.length) usb = true;
			else mqtt = true;
		});
	});

	async function loadPorts(quiet = false): Promise<void> {
		portsBusy = true;
		try {
			ports = (await adminApi.connectors.serialPorts()).ports;
			if (!usbPort && ports.length) usbPort = ports[0].device;
		} catch (err) {
			if (!quiet) error = problemText(err);
		} finally {
			portsBusy = false;
		}
	}

	async function submit(): Promise<void> {
		if (result) {
			wizard.complete('radio');
			return;
		}
		errors = {
			...(!mqtt || GW_RE.test(gateway) ? {} : { gateway: m.setup_radio_gw_invalid() }),
			...(!mqtt || !root.trim() || ROOT_RE.test(root.trim())
				? {}
				: { root: m.setup_radio_root_invalid() }),
			...(!usb || usbPort.trim() ? {} : { usbPort: m.adm_required() })
		};
		if (!mqtt && !usb) error = m.setup_radio_none();
		else error = null;
		if (Object.keys(errors).length || error) return;
		busy = true;
		try {
			result = await wizard.post<RadioResult>('radio', {
				mqtt,
				gateway_name: gateway,
				root: root.trim() || null,
				usb,
				usb_port: usb ? usbPort.trim() : null,
				serial_port_hint: serialHint.trim() || 'COM5'
			});
		} catch (err) {
			error = problemText(err);
		} finally {
			busy = false;
		}
	}

	async function testUsb(id: string): Promise<void> {
		testBusy = true;
		test = null;
		try {
			test = await adminApi.connectors.test(id);
		} catch (err) {
			test = { ok: false, error: problemText(err) };
		} finally {
			testBusy = false;
		}
	}
</script>

<StepFrame
	title={m.setup_radio_title()}
	description={m.setup_radio_desc()}
	onsubmit={submit}
	onback={result ? undefined : () => wizard.back()}
	submitLabel={result ? m.setup_next() : m.setup_radio_create()}
	{busy}
	{error}
>
	{#if !result}
		<fieldset class="adm-fieldset">
			<legend>{m.setup_radio_usb()}</legend>
			<Toggle
				label={m.setup_radio_usb_use()}
				hint={m.setup_radio_usb_hint()}
				bind:checked={usb}
				onchange={(v) => {
					touched = true;
					if (v && ports === null) void loadPorts();
				}}
			/>
			{#if usb}
				<div class="usb">
					{#if ports && ports.length}
						<SelectField
							label={m.setup_radio_port()}
							bind:value={usbPort}
							options={ports.map((p) => ({
								value: p.device,
								label: p.description ? `${p.device} — ${p.description}` : p.device
							}))}
							error={errors.usbPort}
						/>
					{:else}
						<TextField
							label={m.setup_radio_port()}
							hint={ports ? m.setup_radio_no_ports() : undefined}
							bind:value={usbPort}
							placeholder="/dev/ttyUSB0"
							mono
							error={errors.usbPort}
						/>
					{/if}
					<Button size="sm" icon={Search} loading={portsBusy} onclick={() => loadPorts()}
						>{m.setup_radio_detect()}</Button
					>
				</div>
			{/if}
		</fieldset>

		<fieldset class="adm-fieldset">
			<legend>{m.setup_radio_mqtt()}</legend>
			<Toggle
				label={m.setup_radio_mqtt_use()}
				hint={m.setup_radio_mqtt_hint()}
				bind:checked={mqtt}
				onchange={() => (touched = true)}
			/>
			{#if mqtt}
				<div class="adm-grid">
					<TextField
						label={m.setup_radio_gateway()}
						hint={m.setup_radio_gateway_hint({ user: `gw-${gateway || 'interior'}` })}
						bind:value={gateway}
						required
						maxlength={21}
						mono
						error={errors.gateway}
					/>
					<TextField
						label={m.adm_mqtt_root()}
						hint={m.setup_radio_root_hint({ root: `msh/AR/${slug || '…'}` })}
						bind:value={root}
						placeholder={`msh/AR/${slug || '…'}`}
						maxlength={64}
						mono
						error={errors.root}
					/>
					<TextField
						label={m.adm_mqtt_serial()}
						hint={m.adm_mqtt_serial_hint()}
						bind:value={serialHint}
						maxlength={40}
						mono
					/>
				</div>
			{/if}
		</fieldset>
	{:else}
		{#if result.usb}
			<h3 class="sub">{m.setup_radio_usb_ready({ port: result.usb.port })}</h3>
			<div class="adm-row">
				<Button loading={testBusy} onclick={() => testUsb(result!.usb!.connector)}
					>{m.setup_radio_test()}</Button
				>
			</div>
			{#if test}
				{#if test.ok && 'node' in test}
					<p class="adm-note ok" role="status">{m.setup_radio_test_ok()}</p>
					<JsonView value={test.node} summary={m.setup_radio_node()} open />
				{:else if test.ok}
					<p class="adm-note ok" role="status">{m.setup_radio_test_ok()}</p>
				{:else}
					<p class="adm-note danger" role="alert">
						{'error' in test ? test.error : m.setup_radio_test_fail()}
					</p>
				{/if}
			{/if}
		{/if}
		{#if result.mqtt}
			<h3 class="sub">{m.setup_radio_mqtt_ready()}</h3>
			<MqttSecretView
				secret={{
					username: result.mqtt.username,
					password: result.mqtt.password,
					heltec: result.mqtt.heltec
				}}
				root={result.mqtt.root}
			/>
		{/if}
	{/if}
</StepFrame>

<style>
	.usb {
		display: flex;
		flex-wrap: wrap;
		align-items: flex-end;
		gap: 10px;
		margin-top: 12px;
	}

	.usb > :global(:first-child) {
		flex: 1 1 260px;
	}

	.adm-grid {
		margin-top: 12px;
	}

	.sub {
		margin: 8px 0 0;
		font-size: 1rem;
	}
</style>
