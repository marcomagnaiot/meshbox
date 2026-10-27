<!--
  Paso 0, solo con el punto de acceso de configuración (24.3): la red WiFi de la casa. Antes de
  cambiar se explica cómo seguir, porque al conectar el punto de acceso se apaga y esta página
  deja de responder.
-->
<script lang="ts">
	import { problemText } from '$lib/admin/errors';
	import { m } from '$lib/paraglide/messages';
	import type { Wizard } from '$lib/setup/wizard.svelte';
	import SecretField from '$lib/components/admin/SecretField.svelte';
	import TextField from '$lib/components/admin/TextField.svelte';
	import StepFrame from './StepFrame.svelte';

	interface Props {
		wizard: Wizard;
	}

	let { wizard }: Props = $props();
	let ssid = $state('');
	let psk = $state('');
	let busy = $state(false);
	let error = $state<string | null>(null);
	let errors = $state<Record<string, string>>({});
	let sent = $state<string | null>(null);

	async function submit(): Promise<void> {
		errors = {
			...(ssid.trim() ? {} : { ssid: m.adm_required() }),
			...(psk.length >= 8 && psk.length <= 63 ? {} : { psk: m.adm_net_psk_hint() })
		};
		if (Object.keys(errors).length) return;
		busy = true;
		error = null;
		try {
			await wizard.post('wifi', { ssid: ssid.trim(), psk });
			sent = ssid.trim();
			psk = '';
		} catch (err) {
			if (!wizard.handleAuth(err)) error = problemText(err);
		} finally {
			busy = false;
		}
	}
</script>

{#if sent}
	<section class="sent adm-stack" aria-labelledby="step-title">
		<h2 id="step-title" tabindex="-1">{m.setup_wifi_sent_title({ ssid: sent })}</h2>
		<ol class="howto">
			<li>{m.setup_wifi_how_1()}</li>
			<li>{m.setup_wifi_how_2()}</li>
			<li>{m.setup_wifi_how_3()}</li>
			<li>{m.setup_wifi_how_4()}</li>
		</ol>
		<p class="adm-note warn">{m.setup_wifi_fallback()}</p>
	</section>
{:else}
	<StepFrame
		title={m.setup_wifi_title()}
		description={m.setup_wifi_desc()}
		onsubmit={submit}
		submitLabel={m.setup_wifi_connect()}
		{busy}
		{error}
	>
		<TextField
			label={m.setup_wifi_ssid()}
			bind:value={ssid}
			required
			maxlength={32}
			autocomplete="off"
			error={errors.ssid}
		/>
		<SecretField
			label={m.adm_net_psk()}
			hint={m.adm_net_psk_hint()}
			bind:value={psk}
			required
			minlength={8}
			maxlength={63}
			autocomplete="off"
			error={errors.psk}
		/>
		<div class="adm-note">
			<p class="lead">{m.setup_wifi_before()}</p>
			<ol class="howto">
				<li>{m.setup_wifi_how_1()}</li>
				<li>{m.setup_wifi_how_2()}</li>
				<li>{m.setup_wifi_how_3()}</li>
			</ol>
		</div>
	</StepFrame>
{/if}

<style>
	h2 {
		margin: 0;
		font-size: 1.375rem;
		font-weight: 650;
	}

	h2:focus {
		outline: none;
	}

	.lead {
		margin: 0 0 6px;
		font-weight: 650;
	}

	.howto {
		margin: 0;
		padding-left: 20px;
		list-style: decimal;
		display: flex;
		flex-direction: column;
		gap: 6px;
		line-height: 1.5;
	}
</style>
