<!--
  Paso 1 (13.2): código de configuración de un solo uso, mientras no existe ningún usuario.
  Se verifica con el servidor y queda solo en memoria para los pasos siguientes.
-->
<script lang="ts">
	import * as adminApi from '$lib/admin/api';
	import { problemText } from '$lib/admin/errors';
	import { ApiError } from '$lib/api/client';
	import { m } from '$lib/paraglide/messages';
	import type { Wizard } from '$lib/setup/wizard.svelte';
	import TextField from '$lib/components/admin/TextField.svelte';
	import StepFrame from './StepFrame.svelte';

	interface Props {
		wizard: Wizard;
	}

	let { wizard }: Props = $props();
	let code = $state('');
	let busy = $state(false);
	let error = $state<string | null>(null);

	async function submit(): Promise<void> {
		const value = code.replace(/\s+/g, '').toUpperCase();
		if (value.length < 6) {
			error = m.setup_code_short();
			return;
		}
		busy = true;
		error = null;
		try {
			await adminApi.setup.post('code', { code: value });
			wizard.code = value;
			wizard.complete('code');
		} catch (err) {
			error =
				err instanceof ApiError && err.status === 401 ? m.setup_code_wrong() : problemText(err);
		} finally {
			busy = false;
		}
	}
</script>

<StepFrame
	title={m.setup_code_title()}
	description={m.setup_code_desc()}
	onsubmit={submit}
	{busy}
	{error}
>
	<TextField
		label={m.setup_code_label()}
		hint={m.setup_code_hint()}
		bind:value={code}
		required
		maxlength={12}
		autocomplete="one-time-code"
		autocapitalize="characters"
		spellcheck={false}
		mono
	/>
</StepFrame>
