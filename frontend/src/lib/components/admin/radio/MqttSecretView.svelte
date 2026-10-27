<!--
  Credenciales de una cuenta MQTT recién creada o rotada (se muestran una sola vez) y los
  comandos para configurar el Heltec con la CLI de meshtastic (25.1), con botón copiar.
  Lo usan Broker MQTT y el asistente de primer uso.
-->
<script lang="ts">
	import type { MqttSecret } from '$lib/admin/types';
	import { m } from '$lib/paraglide/messages';
	import CopyBlock from '../CopyBlock.svelte';
	import KeyValue from '../KeyValue.svelte';

	interface Props {
		secret: MqttSecret;
		/** Raíz del tópico, si se conoce (asistente). */
		root?: string | null;
	}

	let { secret, root = null }: Props = $props();
</script>

<div class="adm-stack">
	<p class="adm-note warn" role="alert">{m.adm_mqtt_secret_once()}</p>
	<KeyValue
		items={[
			{ label: m.adm_mqtt_user(), value: secret.username, mono: true },
			...(root ? [{ label: m.adm_mqtt_root(), value: root, mono: true }] : [])
		]}
	/>
	<CopyBlock text={secret.password} label={m.admin_password()} inline />
	{#if secret.heltec}
		<h3 class="sub">{m.adm_mqtt_heltec()}</h3>
		<p class="adm-muted">{m.adm_mqtt_heltec_desc()}</p>
		{#each secret.heltec.commands as cmd, i (i)}
			<CopyBlock text={cmd} label={m.adm_mqtt_command({ n: i + 1 })} />
		{/each}
		<details>
			<summary class="adm-muted">{m.adm_mqtt_optional()}</summary>
			<CopyBlock text={secret.heltec.optional_gateway_only} label={m.adm_mqtt_optional()} />
		</details>
		<ul class="notes">
			{#each secret.heltec.notes as n, i (i)}<li>{n}</li>{/each}
		</ul>
	{/if}
</div>

<style>
	.sub {
		margin: 8px 0 0;
		font-size: 1rem;
	}

	.notes {
		margin: 0;
		padding-left: 18px;
		list-style: disc;
		font-size: 0.8125rem;
		color: var(--text-2);
		display: flex;
		flex-direction: column;
		gap: 4px;
	}

	details summary {
		cursor: pointer;
		padding: 6px 0;
	}
</style>
