<!--
  Transmisión (22): solo si `[tx] enabled` y con un nodo conectado por USB o por la red (TCP, ADR 0012). Enviar un mensaje
  de texto o pedir un traceroute, siempre en dos pasos (vista previa y confirmación). El
  servidor limita a 1 envío cada 30 s y 20 por hora (429 con Retry-After); todo queda en la
  auditoría.
-->
<script lang="ts">
	import Eye from '@lucide/svelte/icons/eye';
	import Route from '@lucide/svelte/icons/route';
	import Send from '@lucide/svelte/icons/send';
	import { onDestroy, onMount } from 'svelte';
	import * as adminApi from '$lib/admin/api';
	import type { TxPreview } from '$lib/admin/api';
	import { problemText } from '$lib/admin/errors';
	import { connectorStateLabel } from '$lib/admin/labels';
	import { Resource } from '$lib/admin/resource.svelte';
	import { ApiError } from '$lib/api/client';
	import { fmt } from '$lib/i18n/fmt.svelte';
	import { m } from '$lib/paraglide/messages';
	import { toasts } from '$lib/stores/ui.svelte';
	import Button from '$lib/components/ui/Button.svelte';
	import KeyValue from '$lib/components/admin/KeyValue.svelte';
	import NumberField from '$lib/components/admin/NumberField.svelte';
	import PageHeader from '$lib/components/admin/PageHeader.svelte';
	import Panel from '$lib/components/admin/Panel.svelte';
	import ProblemNote from '$lib/components/admin/ProblemNote.svelte';
	import SelectField from '$lib/components/admin/SelectField.svelte';
	import TextArea from '$lib/components/admin/TextArea.svelte';
	import TextField from '$lib/components/admin/TextField.svelte';

	const NODE_RE = /^!?[0-9a-fA-F]{1,8}$|^\d{1,10}$/;
	const conns = new Resource(() => adminApi.connectors.list());
	const nodes = new Resource(() => adminApi.nodes.list());

	let text = $state('');
	let textChannel = $state(0);
	let textPreview = $state.raw<Record<string, unknown> | null>(null);
	let textError = $state<string | null>(null);
	let textBusy = $state(false);

	let node = $state('');
	let hopLimit = $state<number | null>(3);
	let traceChannel = $state(0);
	let tracePreview = $state.raw<Record<string, unknown> | null>(null);
	let traceError = $state<string | null>(null);
	let traceBusy = $state(false);
	let traceNote = $state<string | null>(null);

	/** Fin de la espera por el límite de envíos (ms epoch). */
	let waitUntil = $state(0);
	let now = $state(Date.now());
	let tick: ReturnType<typeof setInterval> | null = null;

	const waitS = $derived(Math.max(0, Math.ceil((waitUntil - now) / 1000)));
	// El backend transmite con el primer conector USB o TCP (misma API del nodo): se prefiere uno conectado.
	const nodeConns = $derived(
		conns.data?.connectors.filter((c) => c.kind === 'serial' || c.kind === 'tcp') ?? []
	);
	const serial = $derived(
		nodeConns.find((c) => c.status.state === 'connected') ?? nodeConns[0] ?? null
	);
	const usbReady = $derived(serial?.status.state === 'connected');
	const textBytes = $derived(new TextEncoder().encode(text).length);
	const channelOptions = Array.from({ length: 8 }, (_, i) => ({
		value: i,
		label: i === 0 ? m.adm_tx_channel_primary() : m.adm_tx_channel_n({ n: i })
	}));
	const nodeSuggestions = $derived(
		(nodes.data?.nodes ?? []).slice(0, 400).map((n) => ({
			value: n.id,
			label: n.long_name || n.short_name || n.id
		}))
	);

	onMount(() => {
		void conns.load();
		void nodes.load();
		tick = setInterval(() => (now = Date.now()), 1000);
	});

	onDestroy(() => {
		if (tick) clearInterval(tick);
	});

	/** Error de transmisión: texto y, si es el límite, la espera. */
	function txError(err: unknown): string {
		if (err instanceof ApiError && err.status === 429 && err.retryAfter) {
			waitUntil = Date.now() + err.retryAfter * 1000;
		}
		return problemText(err);
	}

	async function previewText(e: SubmitEvent): Promise<void> {
		e.preventDefault();
		if (!text.trim() || text.length > 200) return;
		textBusy = true;
		textError = null;
		try {
			const out = await adminApi.tx.text(text, textChannel, false);
			textPreview = 'preview' in out ? (out as TxPreview).preview : null;
		} catch (err) {
			textError = txError(err);
		} finally {
			textBusy = false;
		}
	}

	async function sendText(): Promise<void> {
		textBusy = true;
		textError = null;
		try {
			const out = (await adminApi.tx.text(text, textChannel, true)) as {
				ok: boolean;
				packet_id?: number;
			};
			if (out.ok) {
				toasts.show(m.adm_tx_sent({ id: out.packet_id ?? '' }), { kind: 'success' });
				text = '';
				textPreview = null;
				waitUntil = Date.now() + 30_000;
			}
		} catch (err) {
			textError = txError(err);
		} finally {
			textBusy = false;
		}
	}

	async function previewTrace(e: SubmitEvent): Promise<void> {
		e.preventDefault();
		if (!NODE_RE.test(node.trim()) || !hopLimit) return;
		traceBusy = true;
		traceError = null;
		traceNote = null;
		try {
			const out = await adminApi.tx.traceroute(node.trim(), hopLimit, traceChannel, false);
			tracePreview = 'preview' in out ? (out as TxPreview).preview : null;
		} catch (err) {
			traceError = txError(err);
		} finally {
			traceBusy = false;
		}
	}

	async function sendTrace(): Promise<void> {
		if (!hopLimit) return;
		traceBusy = true;
		traceError = null;
		try {
			const out = (await adminApi.tx.traceroute(node.trim(), hopLimit, traceChannel, true)) as {
				ok: boolean;
				note?: string;
				error?: string;
			};
			tracePreview = null;
			waitUntil = Date.now() + 30_000;
			if (out.ok) traceNote = out.note ?? m.adm_tx_trace_sent();
			else traceError = out.error ?? m.error_generic();
		} catch (err) {
			traceError = txError(err);
		} finally {
			traceBusy = false;
		}
	}
</script>

<PageHeader slug="transmision" />

<div class="adm-stack">
	<p class="adm-note" role="note">{m.adm_tx_intro()}</p>

	{#if conns.error}
		<ProblemNote error={conns.error} onretry={() => conns.load()} />
	{:else if conns.data}
		{#if usbReady && serial}
			<p class="adm-note ok">{m.adm_tx_usb_ready({ id: serial.id })}</p>
		{:else}
			<p class="adm-note warn" role="alert">
				{serial
					? m.adm_tx_usb_state({ id: serial.id, state: connectorStateLabel(serial.status.state) })
					: m.adm_tx_no_usb()}
				<a class="adm-link" href="/admin/radio">{m.admin_section_radio()}</a>
			</p>
		{/if}
	{/if}

	{#if waitS > 0}
		<p class="adm-note warn" role="status">{m.adm_tx_wait({ seconds: waitS })}</p>
	{/if}

	<div class="adm-grid two">
		<Panel title={m.adm_tx_text_title()} description={m.adm_tx_text_desc()}>
			<form class="adm-stack" onsubmit={previewText}>
				<SelectField
					label={m.adm_channel()}
					bind:value={textChannel}
					options={channelOptions}
					onchange={() => (textPreview = null)}
				/>
				<TextArea
					label={m.adm_tx_text()}
					hint={m.adm_tx_text_count({ chars: text.length, bytes: textBytes })}
					bind:value={text}
					rows={4}
					maxlength={200}
					required
					oninput={() => (textPreview = null)}
				/>
				{#if textError}<p class="adm-note danger" role="alert">{textError}</p>{/if}
				{#if textPreview}
					<div class="preview" aria-live="polite">
						<h3>{m.adm_tx_preview()}</h3>
						<KeyValue
							columns={1}
							items={[
								{ label: m.adm_channel(), value: String(textPreview.channel ?? textChannel) },
								{ label: m.adm_tx_text(), value: String(textPreview.text ?? '') },
								{ label: m.adm_tx_bytes(), value: fmt.number(Number(textPreview.bytes ?? 0), 0) }
							]}
						/>
						<div class="adm-row end">
							<Button size="sm" variant="ghost" onclick={() => (textPreview = null)}
								>{m.adm_cancel()}</Button
							>
							<Button
								size="sm"
								variant="primary"
								icon={Send}
								loading={textBusy}
								disabled={waitS > 0}
								onclick={sendText}>{m.adm_tx_send()}</Button
							>
						</div>
					</div>
				{:else}
					<div class="adm-row end">
						<Button
							type="submit"
							size="sm"
							icon={Eye}
							loading={textBusy}
							disabled={!text.trim() || waitS > 0 || !usbReady}>{m.adm_tx_review()}</Button
						>
					</div>
				{/if}
			</form>
		</Panel>

		<Panel title={m.adm_tx_trace_title()} description={m.adm_tx_trace_desc()}>
			<form class="adm-stack" onsubmit={previewTrace}>
				<TextField
					label={m.adm_tx_node()}
					hint={m.adm_tx_node_hint()}
					bind:value={node}
					mono
					list="tx-nodes"
					required
					autocomplete="off"
					oninput={() => (tracePreview = null)}
				/>
				<datalist id="tx-nodes">
					{#each nodeSuggestions as o (o.value)}
						<option value={o.value}>{o.label}</option>
					{/each}
				</datalist>
				<div class="adm-grid">
					<NumberField
						label={m.adm_tx_hops()}
						bind:value={hopLimit}
						min={1}
						max={7}
						step={1}
						required
					/>
					<SelectField label={m.adm_channel()} bind:value={traceChannel} options={channelOptions} />
				</div>
				{#if traceError}<p class="adm-note danger" role="alert">{traceError}</p>{/if}
				{#if traceNote}
					<p class="adm-note ok" role="status">
						{traceNote} <a class="adm-link" href="/admin/paquetes">{m.admin_section_packets()}</a>
					</p>
				{/if}
				{#if tracePreview}
					<div class="preview" aria-live="polite">
						<h3>{m.adm_tx_preview()}</h3>
						<KeyValue
							columns={1}
							items={[
								{ label: m.adm_tx_node(), value: String(tracePreview.node ?? node), mono: true },
								{ label: m.adm_tx_hops(), value: String(tracePreview.hop_limit ?? hopLimit) }
							]}
						/>
						<div class="adm-row end">
							<Button size="sm" variant="ghost" onclick={() => (tracePreview = null)}
								>{m.adm_cancel()}</Button
							>
							<Button
								size="sm"
								variant="primary"
								icon={Route}
								loading={traceBusy}
								disabled={waitS > 0}
								onclick={sendTrace}>{m.adm_tx_trace_send()}</Button
							>
						</div>
					</div>
				{:else}
					<div class="adm-row end">
						<Button
							type="submit"
							size="sm"
							icon={Eye}
							loading={traceBusy}
							disabled={!NODE_RE.test(node.trim()) || !hopLimit || waitS > 0 || !usbReady}
							>{m.adm_tx_review()}</Button
						>
					</div>
				{/if}
			</form>
		</Panel>
	</div>
</div>

<style>
	.preview {
		padding: 12px 14px;
		border-radius: var(--r-sm);
		border: 1px solid var(--line);
		background: var(--fill-1);
		display: flex;
		flex-direction: column;
		gap: 10px;
	}

	.preview h3 {
		margin: 0;
		font-size: 0.875rem;
	}
</style>
