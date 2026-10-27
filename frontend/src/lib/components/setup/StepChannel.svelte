<!--
  Paso 6: canal público de la zona (el que usan los nodos de la red) con su clave. AQ== es la
  clave por defecto de Meshtastic; con ella los mensajes del canal se muestran en el sitio.
-->
<script lang="ts">
	import { problemText } from '$lib/admin/errors';
	import { m } from '$lib/paraglide/messages';
	import type { Wizard } from '$lib/setup/wizard.svelte';
	import TextField from '$lib/components/admin/TextField.svelte';
	import StepFrame from './StepFrame.svelte';

	interface Props {
		wizard: Wizard;
	}

	let { wizard }: Props = $props();
	const PRESETS = [
		'LongFast',
		'LongModerate',
		'LongSlow',
		'MediumFast',
		'MediumSlow',
		'ShortFast',
		'ShortSlow',
		'ShortTurbo'
	];
	let name = $state('MediumFast');
	let key = $state('AQ==');
	let busy = $state(false);
	let error = $state<string | null>(null);
	let errors = $state<Record<string, string>>({});

	async function submit(): Promise<void> {
		errors = {
			...(name.trim() && name.trim().length <= 11 ? {} : { name: m.setup_channel_name_invalid() }),
			...(key.trim() ? {} : { key: m.adm_required() })
		};
		if (Object.keys(errors).length) return;
		busy = true;
		error = null;
		try {
			await wizard.post('channel', { name: name.trim(), key: key.trim() });
			wizard.complete('channel');
		} catch (err) {
			error = problemText(err);
		} finally {
			busy = false;
		}
	}
</script>

<StepFrame
	title={m.setup_channel_title()}
	description={m.setup_channel_desc()}
	onsubmit={submit}
	onback={() => wizard.back()}
	{busy}
	{error}
>
	<div class="adm-grid two">
		<TextField
			label={m.setup_channel_name()}
			hint={m.setup_channel_name_hint()}
			bind:value={name}
			list="setup-presets"
			required
			maxlength={11}
			autocomplete="off"
			error={errors.name}
		/>
		<TextField
			label={m.setup_channel_key()}
			hint={m.setup_channel_key_hint()}
			bind:value={key}
			required
			maxlength={64}
			mono
			autocomplete="off"
			spellcheck={false}
			error={errors.key}
		/>
	</div>
	<datalist id="setup-presets">
		{#each PRESETS as p (p)}<option value={p}></option>{/each}
	</datalist>
	<p class="adm-note">{m.setup_channel_note()}</p>
</StepFrame>
