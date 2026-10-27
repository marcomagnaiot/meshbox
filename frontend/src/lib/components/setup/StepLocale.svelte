<!--
  Paso 2: idioma del sitio (también el de esta página, al instante) y zona horaria (fechas,
  resúmenes diarios y, en un equipo dedicado, la hora del sistema).
-->
<script lang="ts">
	import { problemText } from '$lib/admin/errors';
	import { i18n } from '$lib/i18n/locale.svelte';
	import { m } from '$lib/paraglide/messages';
	import type { Locale } from '$lib/paraglide/runtime';
	import type { Wizard } from '$lib/setup/wizard.svelte';
	import { site } from '$lib/stores/site.svelte';
	import Segmented from '$lib/components/ui/Segmented.svelte';
	import SelectField from '$lib/components/admin/SelectField.svelte';
	import TextField from '$lib/components/admin/TextField.svelte';
	import StepFrame from './StepFrame.svelte';

	interface Props {
		wizard: Wizard;
	}

	let { wizard }: Props = $props();
	const DEFAULT_TZ = 'America/Argentina/Buenos_Aires';
	let language = $state<Locale>(i18n.locale);
	let timezone = $state(site.data.timezone || DEFAULT_TZ);
	let busy = $state(false);
	let error = $state<string | null>(null);

	const zones: string[] = (() => {
		try {
			return Intl.supportedValuesOf('timeZone');
		} catch {
			return [];
		}
	})();
	const zoneOptions = $derived(
		(zones.includes(timezone) ? zones : [timezone, ...zones]).map((z) => ({
			value: z,
			label: z.replaceAll('_', ' ')
		}))
	);

	async function submit(): Promise<void> {
		busy = true;
		error = null;
		try {
			await wizard.post('locale', { language, timezone });
			wizard.complete('locale');
		} catch (err) {
			if (!wizard.handleAuth(err)) error = problemText(err);
		} finally {
			busy = false;
		}
	}
</script>

<StepFrame
	title={m.setup_locale_title()}
	description={m.setup_locale_desc()}
	onsubmit={submit}
	onback={wizard.index > 0 ? () => wizard.back() : undefined}
	{busy}
	{error}
>
	<div class="lang">
		<span class="label" aria-hidden="true">{m.setup_language()}</span>
		<Segmented
			label={m.setup_language()}
			options={[
				{ value: 'es', label: 'Español' },
				{ value: 'en', label: 'English' }
			]}
			value={language}
			onchange={(v) => {
				language = v as Locale;
				i18n.set(language);
			}}
		/>
	</div>
	{#if zoneOptions.length > 1}
		<SelectField
			label={m.adm_net_tz()}
			hint={wizard.state?.mode === 'shared' ? m.adm_net_tz_shared() : m.adm_net_tz_hint()}
			bind:value={timezone}
			options={zoneOptions}
		/>
	{:else}
		<TextField label={m.adm_net_tz()} bind:value={timezone} mono />
	{/if}
</StepFrame>

<style>
	.lang {
		display: flex;
		flex-direction: column;
		gap: 6px;
	}

	.label {
		font-size: 0.8125rem;
		font-weight: 600;
	}
</style>
