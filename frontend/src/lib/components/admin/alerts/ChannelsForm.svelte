<!--
  Canales de notificación (19.2): Web Push, Telegram, webhooks firmados y MQTT. Los secretos
  son de solo escritura; el secreto de un webhook se puede ver a pedido (queda en auditoría).
-->
<script lang="ts">
	import Eye from '@lucide/svelte/icons/eye';
	import Plus from '@lucide/svelte/icons/plus';
	import Send from '@lucide/svelte/icons/send';
	import Trash2 from '@lucide/svelte/icons/trash-2';
	import { untrack } from 'svelte';
	import * as adminApi from '$lib/admin/api';
	import { problemText } from '$lib/admin/errors';
	import { Busy } from '$lib/admin/resource.svelte';
	import type { AlertChannels } from '$lib/admin/types';
	import { m } from '$lib/paraglide/messages';
	import { toasts } from '$lib/stores/ui.svelte';
	import Button from '$lib/components/ui/Button.svelte';
	import Modal from '$lib/components/ui/Modal.svelte';
	import Toggle from '$lib/components/ui/Toggle.svelte';
	import CopyBlock from '../CopyBlock.svelte';
	import Panel from '../Panel.svelte';
	import SecretField from '../SecretField.svelte';
	import TextField from '../TextField.svelte';

	interface Props {
		data: AlertChannels;
		onsaved: (data: AlertChannels) => void;
	}

	let { data, onsaved }: Props = $props();
	const init = untrack(() => data);

	interface Hook {
		id: string | null;
		url: string;
		enabled: boolean;
		secret: string;
		hasSecret: boolean;
	}

	let webpushEnabled = $state(init.webpush.enabled);
	let telegramEnabled = $state(init.telegram.enabled);
	let chatId = $state(init.telegram.chat_id);
	let botToken = $state('');
	let mqttEnabled = $state(init.mqtt.enabled);
	let hooks = $state<Hook[]>(
		init.webhooks.map((h) => ({
			id: h.id,
			url: h.url,
			enabled: h.enabled,
			secret: '',
			hasSecret: h.secret === '********'
		}))
	);
	let saving = $state(false);
	let error = $state<string | null>(null);
	let shown = $state<{ id: string; secret: string } | null>(null);
	let shownOpen = $state(false);
	const busy = new Busy();

	const subs = $derived(
		Object.entries(data.webpush.subscriptions ?? {})
			.map(([scope, n]) => `${scope}: ${n}`)
			.join(' · ')
	);

	async function save(e: Event): Promise<void> {
		e.preventDefault();
		for (const h of hooks) {
			if (!/^https?:\/\//.test(h.url.trim())) {
				error = m.adm_webhook_url_invalid();
				return;
			}
		}
		saving = true;
		error = null;
		try {
			const out = await adminApi.alerts.saveChannels({
				webpush: { enabled: webpushEnabled },
				telegram_enabled: telegramEnabled,
				telegram_chat_id: chatId.trim(),
				telegram_bot_token: botToken || undefined,
				webhooks: hooks.map((h) => ({
					id: h.id,
					url: h.url.trim(),
					enabled: h.enabled,
					secret: h.secret || undefined
				})),
				mqtt_enabled: mqttEnabled
			});
			toasts.show(m.adm_saved(), { kind: 'success' });
			botToken = '';
			onsaved(out);
		} catch (err) {
			error = problemText(err);
		} finally {
			saving = false;
		}
	}

	async function test(channel: string): Promise<void> {
		const r = await busy.run(channel, () => adminApi.alerts.testChannel(channel));
		if (!r) return;
		if (r.ok) toasts.show(m.adm_channel_test_ok(), { kind: 'success' });
		else
			toasts.show(m.adm_channel_test_fail({ error: r.error ?? '' }), {
				kind: 'error',
				timeout: 9000
			});
	}

	async function reveal(id: string): Promise<void> {
		const r = await busy.run(`s-${id}`, () => adminApi.alerts.webhookSecret(id));
		if (r) {
			shown = r;
			shownOpen = true;
		}
	}
</script>

<form class="adm-stack" onsubmit={save} novalidate>
	<Panel title={m.adm_notify_webpush()} description={m.adm_webpush_desc()}>
		<div class="adm-stack">
			<Toggle label={m.adm_webpush_enable()} bind:checked={webpushEnabled} />
			<p class="adm-muted">
				{data.webpush.available ? m.adm_webpush_available() : m.adm_webpush_unavailable()}
				{#if subs}· {m.adm_webpush_subs({ subs })}{/if}
			</p>
			<div class="adm-row">
				<Button size="sm" icon={Send} loading={busy.is('webpush')} onclick={() => test('webpush')}
					>{m.adm_test()}</Button
				>
			</div>
		</div>
	</Panel>

	<Panel title={m.adm_notify_telegram()} description={m.adm_telegram_desc()}>
		<div class="adm-stack">
			<Toggle label={m.adm_telegram_enable()} bind:checked={telegramEnabled} />
			<div class="adm-grid">
				<SecretField
					label={m.adm_telegram_token()}
					hint={m.adm_telegram_token_hint()}
					bind:value={botToken}
					isSet={data.telegram.bot_token === '********'}
				/>
				<TextField
					label={m.adm_telegram_chat()}
					hint={m.adm_telegram_chat_hint()}
					bind:value={chatId}
					mono
				/>
			</div>
			<div class="adm-row">
				<Button size="sm" icon={Send} loading={busy.is('telegram')} onclick={() => test('telegram')}
					>{m.adm_test()}</Button
				>
			</div>
		</div>
	</Panel>

	<Panel title={m.adm_notify_webhook()} description={m.adm_webhook_desc()}>
		<div class="adm-stack">
			{#each hooks as h, i (i)}
				<fieldset class="adm-fieldset">
					<legend>{h.id ?? m.adm_webhook_new()}</legend>
					<div class="adm-stack">
						<TextField label={m.adm_webhook_url()} type="url" bind:value={h.url} mono required />
						<SecretField
							label={m.adm_webhook_secret()}
							hint={m.adm_webhook_secret_hint()}
							bind:value={h.secret}
							isSet={h.hasSecret}
						/>
						<Toggle label={m.adm_enabled()} bind:checked={h.enabled} />
						<div class="adm-row">
							{#if h.id}
								<Button
									size="sm"
									icon={Send}
									loading={busy.is(`webhook:${h.id}`)}
									onclick={() => test(`webhook:${h.id}`)}>{m.adm_test()}</Button
								>
								{#if h.hasSecret}
									<Button
										size="sm"
										icon={Eye}
										loading={busy.is(`s-${h.id}`)}
										onclick={() => reveal(h.id!)}>{m.adm_webhook_show_secret()}</Button
									>
								{/if}
							{/if}
							<Button
								size="sm"
								variant="ghost"
								icon={Trash2}
								onclick={() => (hooks = hooks.filter((_, j) => j !== i))}>{m.adm_remove()}</Button
							>
						</div>
					</div>
				</fieldset>
			{/each}
			<div class="adm-row">
				<Button
					size="sm"
					icon={Plus}
					disabled={hooks.length >= 10}
					onclick={() =>
						(hooks = [
							...hooks,
							{ id: null, url: 'https://', enabled: true, secret: '', hasSecret: false }
						])}>{m.adm_webhook_add()}</Button
				>
			</div>
		</div>
	</Panel>

	<Panel title={m.adm_notify_mqtt()} description={m.adm_mqtt_alert_desc()}>
		<div class="adm-stack">
			<Toggle label={m.adm_mqtt_alert_enable()} bind:checked={mqttEnabled} />
			<div class="adm-row">
				<Button size="sm" icon={Send} loading={busy.is('mqtt')} onclick={() => test('mqtt')}
					>{m.adm_test()}</Button
				>
			</div>
		</div>
	</Panel>

	<p class="adm-muted">
		{m.adm_alert_stats({
			fired: data.stats.fired,
			resolved: data.stats.resolved,
			ok: data.stats.notifications_ok,
			failed: data.stats.notifications_failed
		})}
	</p>
	{#if error}<p class="adm-note danger" role="alert">{error}</p>{/if}
	<div class="adm-row end">
		<Button type="submit" variant="primary" loading={saving}>{m.adm_save()}</Button>
	</div>
</form>

<Modal bind:open={shownOpen} title={m.adm_webhook_secret_title({ id: shown?.id ?? '' })}>
	{#if shown}
		<div class="adm-stack">
			<p class="adm-muted">{m.adm_webhook_secret_audit()}</p>
			<CopyBlock text={shown.secret} label={m.adm_webhook_secret()} inline />
		</div>
	{/if}
</Modal>
