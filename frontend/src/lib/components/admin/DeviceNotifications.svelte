<!--
  Avisos en este equipo (ADR 0023): elegir si el teléfono o la computadora avisa los mensajes
  que llegan a las placas del Cliente (solo directos o también canales) y las alertas, aunque
  el panel esté cerrado. Con el panel sin instalar, ofrece instalarlo. `compact` es la versión
  del menú de mensajes nuevos (sin alertas ni prueba).
-->
<script lang="ts">
	import BellRing from '@lucide/svelte/icons/bell-ring';
	import Download from '@lucide/svelte/icons/download';
	import { onMount } from 'svelte';
	import type { MessageAlerts } from '$lib/admin/api';
	import { devicePush } from '$lib/admin/devicePush.svelte';
	import { problemText } from '$lib/admin/errors';
	import { m } from '$lib/paraglide/messages';
	import { toasts } from '$lib/stores/ui.svelte';
	import Button from '$lib/components/ui/Button.svelte';
	import Segmented from '$lib/components/ui/Segmented.svelte';
	import Toggle from '$lib/components/ui/Toggle.svelte';

	interface Props {
		compact?: boolean;
	}

	let { compact = false }: Props = $props();
	let testing = $state(false);
	const s = devicePush;

	onMount(() => {
		void s.refresh();
	});

	const options = $derived<{ value: MessageAlerts; label: string }[]>([
		{ value: 'off', label: m.adm_dev_msg_off() },
		{ value: 'dm', label: m.adm_dev_msg_dm() },
		{ value: 'all', label: m.adm_dev_msg_all() }
	]);

	async function save(messages: MessageAlerts, alerts: boolean): Promise<void> {
		const before = { messages: s.messages, alerts: s.alerts };
		try {
			await s.save(messages, alerts);
			toasts.show(messages === 'off' && !alerts ? m.adm_dev_saved_off() : m.adm_dev_saved(), {
				kind: 'success'
			});
		} catch (err) {
			s.messages = before.messages;
			s.alerts = before.alerts;
			const denied = err instanceof Error && err.message === 'denied';
			toasts.show(denied ? m.adm_dev_denied() : problemText(err), { kind: 'error' });
		}
	}

	async function test(): Promise<void> {
		testing = true;
		try {
			await s.test();
			toasts.show(m.adm_dev_test_sent(), { kind: 'success' });
		} catch (err) {
			toasts.show(problemText(err), { kind: 'error' });
		} finally {
			testing = false;
		}
	}
</script>

<div class="dev" class:compact>
	{#if !compact}
		<p class="adm-muted lead">{m.adm_dev_desc()}</p>
	{/if}
	{#if s.canInstall && !s.installed}
		<div class="install">
			<Button size="sm" icon={Download} onclick={() => void s.install()}
				>{m.adm_dev_install()}</Button
			>
			{#if !compact}<span class="adm-muted">{m.adm_dev_install_hint()}</span>{/if}
		</div>
	{/if}
	{#if s.state === 'checking'}
		<p class="adm-muted">{m.loading()}</p>
	{:else if s.state === 'needs-install'}
		<p class="note">{m.adm_dev_ios()}</p>
	{:else if s.state === 'unsupported'}
		<p class="note">{m.adm_dev_unsupported()}</p>
	{:else if s.state === 'unavailable'}
		<p class="note">{m.adm_dev_unavailable()}</p>
	{:else}
		{#if s.state === 'denied'}<p class="note">{m.adm_dev_blocked()}</p>{/if}
		<div class="row">
			<span class="label" id="dev-msg-label"
				><BellRing size={16} aria-hidden="true" />{m.adm_dev_messages()}</span
			>
			<Segmented
				label={m.adm_dev_messages()}
				size="sm"
				{options}
				value={s.messages}
				onchange={(v) => void save(v, s.alerts)}
			/>
		</div>
		{#if !compact}
			<Toggle
				label={m.adm_dev_alerts()}
				hint={m.adm_dev_alerts_hint()}
				checked={s.alerts && s.subscribed}
				disabled={s.busy || s.state === 'denied'}
				onchange={(v) => void save(s.messages, v)}
			/>
			{#if s.subscribed}
				<div>
					<Button size="sm" variant="ghost" loading={testing} onclick={test}
						>{m.adm_dev_test()}</Button
					>
				</div>
			{/if}
		{/if}
	{/if}
</div>

<style>
	.dev {
		display: flex;
		flex-direction: column;
		gap: 12px;
	}

	.dev.compact {
		gap: 8px;
		padding: 8px 10px 4px;
		border-top: 1px solid var(--line);
		margin-top: 6px;
	}

	.lead,
	.note {
		margin: 0;
		font-size: 0.875rem;
		line-height: 1.5;
	}

	.note {
		color: var(--text-2);
	}

	.row {
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		justify-content: space-between;
		gap: 8px;
	}

	.label {
		display: inline-flex;
		align-items: center;
		gap: 6px;
		font-size: 0.875rem;
		font-weight: 600;
	}

	.install {
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		gap: 10px;
		font-size: 0.8125rem;
	}
</style>
