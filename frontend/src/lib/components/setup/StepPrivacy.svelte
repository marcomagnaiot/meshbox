<!--
  Paso 7: privacidad (ignorar nodos que llegan solo por MQTT, posiciones tal cual o con
  precisión reducida) y aviso del sitio. La retención se ajusta después en el panel.
-->
<script lang="ts">
	import { problemText } from '$lib/admin/errors';
	import { m } from '$lib/paraglide/messages';
	import type { Wizard } from '$lib/setup/wizard.svelte';
	import Toggle from '$lib/components/ui/Toggle.svelte';
	import NumberField from '$lib/components/admin/NumberField.svelte';
	import SelectField from '$lib/components/admin/SelectField.svelte';
	import TextArea from '$lib/components/admin/TextArea.svelte';
	import StepFrame from './StepFrame.svelte';

	interface Props {
		wizard: Wizard;
	}

	let { wizard }: Props = $props();
	let ignoreViaMqtt = $state(true);
	let policy = $state<'as_received' | 'degrade'>('as_received');
	let degradeMeters = $state<number | null>(500);
	let notice = $state('');
	let busy = $state(false);
	let error = $state<string | null>(null);

	async function submit(): Promise<void> {
		busy = true;
		error = null;
		try {
			await wizard.post('privacy', {
				ignore_via_mqtt: ignoreViaMqtt,
				position_policy: policy,
				degrade_meters: Math.min(50_000, Math.max(50, degradeMeters ?? 500)),
				notice_md: notice.trim() || null
			});
			wizard.complete('privacy');
		} catch (err) {
			error = problemText(err);
		} finally {
			busy = false;
		}
	}
</script>

<StepFrame
	title={m.setup_privacy_title()}
	description={m.setup_privacy_desc()}
	onsubmit={submit}
	onback={() => wizard.back()}
	{busy}
	{error}
>
	<Toggle
		label={m.setup_privacy_ignore_mqtt()}
		hint={m.setup_privacy_ignore_mqtt_hint()}
		bind:checked={ignoreViaMqtt}
	/>
	<div class="adm-grid two">
		<SelectField
			label={m.setup_privacy_positions()}
			bind:value={policy}
			options={[
				{ value: 'as_received', label: m.setup_privacy_as_received() },
				{ value: 'degrade', label: m.setup_privacy_degrade() }
			]}
		/>
		{#if policy === 'degrade'}
			<NumberField
				label={m.setup_privacy_meters()}
				bind:value={degradeMeters}
				min={50}
				max={50000}
				step={50}
				unit="m"
			/>
		{/if}
	</div>
	<TextArea
		label={m.setup_privacy_notice()}
		hint={m.setup_privacy_notice_hint()}
		bind:value={notice}
		rows={4}
		maxlength={20000}
	/>
	<p class="adm-muted">{m.setup_privacy_retention()}</p>
</StepFrame>
