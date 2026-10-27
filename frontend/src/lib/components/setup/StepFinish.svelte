<!--
  Paso 10: resumen y verificación. Se espera a que llegue al menos un paquete (puede tardar
  unos minutos tras configurar el Heltec) y se confirma que el sitio responde. Al terminar,
  enlaces al mapa y al panel.
-->
<script lang="ts">
	import CircleCheck from '@lucide/svelte/icons/circle-check';
	import LoaderCircle from '@lucide/svelte/icons/loader-circle';
	import CircleMinus from '@lucide/svelte/icons/circle-minus';
	import { onMount } from 'svelte';
	import * as adminApi from '$lib/admin/api';
	import { problemText } from '$lib/admin/errors';
	import { connectorStateLabel } from '$lib/admin/labels';
	import { Resource } from '$lib/admin/resource.svelte';
	import { fmt } from '$lib/i18n/fmt.svelte';
	import { m } from '$lib/paraglide/messages';
	import type { Wizard } from '$lib/setup/wizard.svelte';
	import Button from '$lib/components/ui/Button.svelte';
	import ProblemNote from '$lib/components/admin/ProblemNote.svelte';
	import StepFrame from './StepFrame.svelte';

	interface Props {
		wizard: Wizard;
	}

	let { wizard }: Props = $props();
	const verify = new Resource(() => adminApi.setup.verify());
	let busy = $state(false);
	let error = $state<string | null>(null);
	let finished = $state(false);

	onMount(() => {
		void verify.load();
		const stop = verify.poll(5000);
		return () => {
			stop();
			verify.dispose();
		};
	});

	const v = $derived(verify.data);

	async function finish(): Promise<void> {
		busy = true;
		error = null;
		try {
			await wizard.post('finish');
			finished = true;
			verify.stopPolling();
		} catch (err) {
			error = problemText(err);
		} finally {
			busy = false;
		}
	}
</script>

{#snippet check(ok: boolean | null, label: string, detail?: string)}
	<li class:ok={ok === true} class:wait={ok === null}>
		{#if ok === true}
			<CircleCheck size={20} aria-hidden="true" />
		{:else if ok === null}
			<LoaderCircle size={20} class="animate-spin" aria-hidden="true" />
		{:else}
			<CircleMinus size={20} aria-hidden="true" />
		{/if}
		<span class="what">
			<span>{label}</span>
			{#if detail}<span class="adm-muted">{detail}</span>{/if}
		</span>
	</li>
{/snippet}

{#if finished}
	<section class="done adm-stack" aria-labelledby="step-title">
		<CircleCheck size={40} aria-hidden="true" />
		<h2 id="step-title" tabindex="-1">{m.setup_done_title()}</h2>
		<p class="adm-muted">{m.setup_done_desc()}</p>
		<div class="adm-row">
			<Button href="/" variant="primary" data-sveltekit-reload>{m.setup_done_map()}</Button>
			<Button href="/admin">{m.setup_done_admin()}</Button>
		</div>
	</section>
{:else}
	<StepFrame
		title={m.setup_finish_title()}
		description={m.setup_finish_desc()}
		onsubmit={finish}
		submitLabel={m.setup_finish()}
		onback={() => wizard.back()}
		{busy}
		{error}
	>
		{#if verify.error && !v}
			<ProblemNote error={verify.error} onretry={() => verify.load()} />
		{:else if v}
			<ul class="checks" aria-live="polite">
				{@render check(
					v.packet_received ? true : null,
					v.packet_received ? m.setup_check_packets_ok() : m.setup_check_packets_wait(),
					v.last_packet_at
						? m.setup_check_packets_detail({
								count: v.packets_total,
								when: fmt.relative(v.last_packet_at)
							})
						: m.setup_check_packets_hint()
				)}
				{@render check(
					v.connectors.some((c) => c.state === 'connected'),
					m.setup_check_connectors(),
					v.connectors.map((c) => `${c.id}: ${connectorStateLabel(c.state)}`).join(' · ') ||
						m.setup_check_no_connectors()
				)}
				{@render check(v.nodes > 0, m.setup_check_nodes({ count: v.nodes }))}
				{@render check(
					v.public_channels.length > 0,
					m.setup_check_channels(),
					v.public_channels.join(', ') || m.adm_none()
				)}
				{@render check(v.site_ok, m.setup_check_site())}
				{@render check(v.tiles, v.tiles ? m.setup_check_tiles_ok() : m.setup_check_tiles_none())}
			</ul>
			{#if !v.packet_received}
				<p class="adm-note">{m.setup_finish_wait()}</p>
			{/if}
		{/if}
	</StepFrame>
{/if}

<style>
	.checks {
		list-style: none;
		margin: 0;
		padding: 0;
		display: flex;
		flex-direction: column;
		gap: 10px;
	}

	.checks li {
		display: flex;
		align-items: flex-start;
		gap: 10px;
		color: var(--text-2);
	}

	.checks li.ok {
		color: var(--success);
	}

	.checks li.wait {
		color: var(--accent);
	}

	.what {
		display: flex;
		flex-direction: column;
		gap: 2px;
		color: var(--text-1);
	}

	.what .adm-muted {
		font-size: 0.8125rem;
	}

	.done {
		align-items: flex-start;
		color: var(--success);
	}

	.done h2 {
		margin: 0;
		color: var(--text-1);
		font-size: 1.5rem;
		font-weight: 650;
	}

	.done h2:focus {
		outline: none;
	}
</style>
