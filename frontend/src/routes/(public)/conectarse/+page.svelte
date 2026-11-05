<!--
  Cómo conectarse: los parámetros de radio de la red para quien llega, con el QR y el enlace del
  canal para la app de Meshtastic. Los carga quien administra en Sitio y mapa.
-->
<script lang="ts">
	import Copy from '@lucide/svelte/icons/copy';
	import ExternalLink from '@lucide/svelte/icons/external-link';
	import Phone from '@lucide/svelte/icons/phone';
	import { i18n } from '$lib/i18n/locale.svelte';
	import { formatMhz, phoneHref } from '$lib/join';
	import { m } from '$lib/paraglide/messages';
	import { site } from '$lib/stores/site.svelte';
	import { toasts } from '$lib/stores/ui.svelte';
	import NoticeBlocks from '$lib/components/notice/NoticeBlocks.svelte';
	import QrCode from '$lib/components/join/QrCode.svelte';

	const s = $derived(site.data);
	const j = $derived(s.join ?? null);
	const tel = $derived(j?.contact ? phoneHref(j.contact) : null);

	async function copy(text: string): Promise<void> {
		try {
			await navigator.clipboard.writeText(text);
			toasts.show(m.join_copied(), { kind: 'success' });
		} catch {
			toasts.show(m.join_copy_failed(), { kind: 'error' });
		}
	}
</script>

<svelte:head><title>{m.join_title()} · {s.name}</title></svelte:head>

<div class="page-scroll page-pad join">
	<h1 class="page-title">{m.join_title()}</h1>

	{#if !j}
		<p class="muted">{m.join_empty()}</p>
	{:else}
		<p class="lead">{m.join_intro({ name: s.name })}</p>

		<section aria-labelledby="j-params" class="card params">
			<h2 id="j-params" class="section-title">{m.join_params()}</h2>
			<dl>
				{#if j.region}
					<dt>{m.join_region()}</dt>
					<dd><strong>{j.region}</strong></dd>
				{/if}
				{#if j.preset}
					<dt>{m.join_preset()}</dt>
					<dd><strong>{j.preset_name}</strong></dd>
				{/if}
				{#if j.frequency_mhz || j.slot}
					<dt>{m.join_frequency()}</dt>
					<dd>
						{#if j.frequency_mhz}<strong>{formatMhz(j.frequency_mhz, i18n.locale)} MHz</strong>{/if}
						{#if j.slot}<span class="muted">
								{j.frequency_mhz
									? `(${m.join_slot({ slot: j.slot })})`
									: m.join_slot({ slot: j.slot })}</span
							>{/if}
					</dd>
				{/if}
				<dt>{m.join_channel()}</dt>
				<dd>
					<strong>{j.channel_name || j.preset_name}</strong>
					<span class="muted">
						{j.channel_name ? '' : m.join_channel_default()}
						{j.default_key ? m.join_key_default() : m.join_key_custom()}</span
					>
				</dd>
				{#if j.role}
					<dt>{m.join_role()}</dt>
					<dd><strong>{j.role}</strong></dd>
				{/if}
				<dt>{m.join_hops()}</dt>
				<dd><strong>{j.hop_limit}</strong></dd>
				{#if j.contact}
					<dt>{m.join_contact()}</dt>
					<dd>
						{#if tel}
							<a href={tel} class="contact"><Phone size={15} aria-hidden="true" />{j.contact}</a>
						{:else}<strong>{j.contact}</strong>{/if}
					</dd>
				{/if}
			</dl>
		</section>

		{#if j.url}
			<section aria-labelledby="j-qr" class="card qr-card">
				<h2 id="j-qr" class="section-title">{m.join_qr_title()}</h2>
				<div class="qr-row">
					<QrCode value={j.url} label={m.join_qr_label()} size={200} />
					<div class="qr-text">
						<p>{m.join_qr_body()}</p>
						<p class="muted">{m.join_qr_warning()}</p>
						<div class="actions">
							<a class="btn-link" href={j.url} target="_blank" rel="noopener noreferrer"
								><ExternalLink size={16} aria-hidden="true" />{m.join_open_app()}</a
							>
							<button type="button" class="btn-link" onclick={() => copy(j.url ?? '')}
								><Copy size={16} aria-hidden="true" />{m.join_copy_link()}</button
							>
						</div>
					</div>
				</div>
			</section>
		{/if}

		<section aria-labelledby="j-steps">
			<h2 id="j-steps" class="section-title">{m.join_steps()}</h2>
			<ol class="steps">
				<li>{m.join_step_app()}</li>
				{#if j.region}<li>{m.join_step_region({ region: j.region })}</li>{/if}
				{#if j.preset}<li>{m.join_step_preset({ preset: j.preset_name })}</li>{/if}
				{#if j.slot}<li>{m.join_step_slot({ slot: j.slot })}</li>{/if}
				<li>
					{j.channel_name
						? m.join_step_channel_named({ name: j.channel_name })
						: m.join_step_channel()}
				</li>
				{#if j.role}<li>{m.join_step_role({ role: j.role })}</li>{/if}
			</ol>
		</section>

		{#if j.notes.length}
			<section aria-label={m.join_notes()} class="card notes">
				<NoticeBlocks blocks={j.notes} />
			</section>
		{/if}
	{/if}
</div>

<style>
	.join {
		max-width: 760px;
	}

	p {
		margin: 0 0 10px;
		line-height: 1.55;
		font-size: 0.9375rem;
	}

	.lead {
		font-weight: 600;
	}

	.muted {
		color: var(--text-2);
	}

	.card {
		margin: 16px 0;
		padding: 4px 16px 14px;
	}

	dl {
		display: grid;
		grid-template-columns: max-content minmax(0, 1fr);
		gap: 8px 16px;
		margin: 0;
		font-size: 0.9375rem;
	}

	dt {
		color: var(--text-2);
	}

	dd {
		margin: 0;
		overflow-wrap: anywhere;
	}

	.contact {
		display: inline-flex;
		align-items: center;
		gap: 6px;
		min-height: 32px;
		font-weight: 650;
		color: var(--accent-text, var(--text-1));
	}

	.qr-row {
		display: flex;
		flex-wrap: wrap;
		gap: 16px;
		align-items: flex-start;
	}

	.qr-text {
		flex: 1 1 240px;
		min-width: 0;
	}

	.actions {
		display: flex;
		flex-wrap: wrap;
		gap: 8px;
	}

	.btn-link {
		display: inline-flex;
		align-items: center;
		gap: 6px;
		min-height: 44px;
		padding: 0 12px;
		border: 1px solid var(--line);
		border-radius: var(--r-sm);
		background: var(--fill-1);
		color: var(--text-1);
		font: inherit;
		font-size: 0.875rem;
		font-weight: 550;
		text-decoration: none;
		cursor: pointer;
	}

	.btn-link:hover {
		background: var(--fill-2);
	}

	.steps {
		margin: 0;
		padding-left: 20px;
		line-height: 1.6;
		font-size: 0.9375rem;
	}

	.notes {
		padding-top: 4px;
	}
</style>
