<!-- Segundo paso de un cambio peligroso: lista lo que cambia y pide escribir la palabra. -->
<script lang="ts">
	import { m } from '$lib/paraglide/messages';
	import ConfirmAction from '$lib/components/admin/ConfirmAction.svelte';
	import type { DangerGate } from './danger.svelte';

	interface Props {
		gate: DangerGate;
		remote?: boolean;
	}

	let { gate, remote = false }: Props = $props();
</script>

<ConfirmAction
	bind:open={gate.open}
	title={m.adm_cli_danger_title()}
	description={remote ? m.adm_cli_danger_remote() : m.adm_cli_danger_desc()}
	confirmLabel={m.adm_cli_danger_apply()}
	danger
	requireText={m.adm_cli_danger_word()}
	action={gate.confirm}
>
	<ul class="fields">
		{#each gate.fields as f (f)}
			<li><code class="adm-code">{f}</code></li>
		{/each}
	</ul>
	<p class="adm-muted">{m.adm_cli_danger_backup()}</p>
</ConfirmAction>

<style>
	.fields {
		margin: 0 0 8px;
		padding-left: 18px;
		display: flex;
		flex-direction: column;
		gap: 4px;
	}
</style>
