<!--
  Paso 8: mapa base sin internet. Descarga del extracto de la región (caja sobre el mapa, zoom
  máximo y progreso) con el mismo panel que Sitio y mapa; se puede omitir y hacer después.
-->
<script lang="ts">
	import { onMount } from 'svelte';
	import * as adminApi from '$lib/admin/api';
	import { problemText } from '$lib/admin/errors';
	import { m } from '$lib/paraglide/messages';
	import type { Wizard } from '$lib/setup/wizard.svelte';
	import TilesPanel from '$lib/components/admin/site/TilesPanel.svelte';
	import StepFrame from './StepFrame.svelte';

	interface Props {
		wizard: Wizard;
	}

	let { wizard }: Props = $props();
	let bounds = $state<number[] | null>(null);
	let ready = $state(false);
	let busy = $state(false);
	let error = $state<string | null>(null);

	onMount(async () => {
		try {
			bounds = (await adminApi.site.get()).site.bounds;
		} catch {
			bounds = null;
		}
		ready = true;
	});

	async function skip(): Promise<void> {
		busy = true;
		error = null;
		try {
			await wizard.post('skip/tiles');
			wizard.complete('tiles');
		} catch (err) {
			error = problemText(err);
		} finally {
			busy = false;
		}
	}
</script>

<StepFrame
	title={m.setup_tiles_title()}
	description={m.setup_tiles_desc()}
	onsubmit={() => wizard.complete('tiles')}
	onback={() => wizard.back()}
	onskip={skip}
	skipLabel={m.setup_later()}
	{busy}
	{error}
>
	{#if ready}
		<TilesPanel siteBounds={bounds} />
	{/if}
	<p class="adm-muted">{m.setup_tiles_note()}</p>
</StepFrame>
