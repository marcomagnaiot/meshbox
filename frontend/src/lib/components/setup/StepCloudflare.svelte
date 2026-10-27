<!--
  Paso 9 (opcional): publicar el sitio con un túnel de Cloudflare. Se hace desde la sección
  Cloudflare del panel (modo token o API); acá se explica y se puede dejar para después.
-->
<script lang="ts">
	import ExternalLink from '@lucide/svelte/icons/external-link';
	import { problemText } from '$lib/admin/errors';
	import { m } from '$lib/paraglide/messages';
	import type { Wizard } from '$lib/setup/wizard.svelte';
	import Button from '$lib/components/ui/Button.svelte';
	import StepFrame from './StepFrame.svelte';

	interface Props {
		wizard: Wizard;
	}

	let { wizard }: Props = $props();
	let busy = $state(false);
	let error = $state<string | null>(null);

	async function skip(): Promise<void> {
		busy = true;
		error = null;
		try {
			await wizard.post('skip/cloudflare');
			wizard.complete('cloudflare');
		} catch (err) {
			error = problemText(err);
		} finally {
			busy = false;
		}
	}
</script>

<StepFrame
	title={m.setup_cf_title()}
	description={m.setup_cf_desc()}
	onsubmit={skip}
	submitLabel={m.setup_later()}
	onback={() => wizard.back()}
	{busy}
	{error}
>
	<ul class="points">
		<li>{m.setup_cf_point_1()}</li>
		<li>{m.setup_cf_point_2()}</li>
		<li>{m.setup_cf_point_3()}</li>
	</ul>
	<div class="adm-row">
		<Button href="/admin/cloudflare" target="_blank" rel="noopener" icon={ExternalLink}
			>{m.setup_cf_open()}</Button
		>
	</div>
</StepFrame>

<style>
	.points {
		margin: 0;
		padding-left: 20px;
		list-style: disc;
		display: flex;
		flex-direction: column;
		gap: 6px;
		line-height: 1.5;
	}
</style>
