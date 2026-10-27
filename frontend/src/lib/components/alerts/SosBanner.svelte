<!--
  Aviso de alerta activa en todas las páginas. Un SOS se anuncia con aria-live="assertive";
  las demás alertas, con "polite". Superficie sólida: tiene que leerse sobre cualquier fondo.
-->
<script lang="ts">
	import MapPin from '@lucide/svelte/icons/map-pin';
	import Siren from '@lucide/svelte/icons/siren';
	import TriangleAlert from '@lucide/svelte/icons/triangle-alert';
	import X from '@lucide/svelte/icons/x';
	import { fmt } from '$lib/i18n/fmt.svelte';
	import { severityLabel } from '$lib/i18n/labels';
	import { m } from '$lib/paraglide/messages';
	import { alerts, isSos } from '$lib/stores/alerts.svelte';
	import { nodeHref } from '$lib/utils/ids';

	const alert = $derived(alerts.banner);
	const sos = $derived(alert ? isSos(alert) : false);
</script>

<!-- La región existe siempre para que el lector anuncie lo que aparezca adentro. -->
<div class="sos-region" aria-live={sos ? 'assertive' : 'polite'} aria-atomic="true">
	{#if alert}
		<div
			class="sos"
			class:critical={sos}
			role={sos ? 'alert' : 'status'}
			data-testid="alert-banner"
		>
			<span class="icon" aria-hidden="true">
				{#if sos}<Siren size={22} />{:else}<TriangleAlert size={22} />{/if}
			</span>
			<div class="text">
				<p class="kicker">
					{sos ? m.alerts_sos() : m.alerts_active()} · {severityLabel(alert.severity)} · {fmt.relative(
						alert.ts
					)}
				</p>
				<p class="title">{alert.title}</p>
				{#if alert.body && alert.body !== alert.title}<p class="body">{alert.body}</p>{/if}
			</div>
			<div class="actions">
				{#if alert.node}
					<a class="action" href={nodeHref(alert.node)}>
						<MapPin size={16} aria-hidden="true" />{m.alerts_view_map()}
					</a>
				{/if}
				<a class="action ghost" href="/alertas">{m.alerts_view_all()}</a>
				<button
					type="button"
					class="close"
					aria-label={m.alerts_dismiss()}
					onclick={() => alerts.dismiss(alert.id)}
				>
					<X size={18} aria-hidden="true" />
				</button>
			</div>
		</div>
	{/if}
</div>

<style>
	.sos-region {
		position: fixed;
		z-index: var(--z-toasts);
		top: calc(var(--safe-top) + var(--banner-top, 8px));
		left: 50%;
		transform: translateX(-50%);
		width: min(720px, calc(100vw - 16px));
		pointer-events: none;
	}

	.sos {
		pointer-events: auto;
		display: flex;
		align-items: center;
		gap: 12px;
		padding: 10px 8px 10px 14px;
		border-radius: var(--r-md);
		background: var(--surface-1);
		border: 2px solid var(--warning);
		box-shadow: 0 12px 40px oklch(0% 0 0 / 0.45);
		animation: slide-up var(--dur-2) var(--ease);
	}

	.sos.critical {
		border-color: var(--danger);
		background: color-mix(in oklch, var(--danger) 14%, var(--surface-1));
	}

	.icon {
		display: grid;
		place-items: center;
		width: 40px;
		height: 40px;
		flex: none;
		border-radius: 50%;
		background: var(--warning-soft);
		color: var(--text-1);
	}

	.critical .icon {
		background: var(--danger);
		color: var(--on-danger);
	}

	.text {
		flex: 1;
		min-width: 0;
	}

	.text p {
		margin: 0;
	}

	.kicker {
		font-size: 0.75rem;
		font-weight: 650;
		color: var(--text-2);
	}

	.title {
		font-weight: 700;
		overflow: hidden;
		text-overflow: ellipsis;
	}

	.body {
		font-size: 0.875rem;
		color: var(--text-1);
		overflow: hidden;
		text-overflow: ellipsis;
		display: -webkit-box;
		-webkit-line-clamp: 2;
		line-clamp: 2;
		-webkit-box-orient: vertical;
	}

	.actions {
		display: flex;
		align-items: center;
		gap: 4px;
		flex-wrap: wrap;
		justify-content: flex-end;
	}

	.action {
		display: inline-flex;
		align-items: center;
		gap: 6px;
		min-height: 40px;
		padding: 0 12px;
		border-radius: var(--r-sm);
		background: var(--fill-2);
		color: var(--text-1);
		text-decoration: none;
		font-size: 0.8125rem;
		font-weight: 650;
		white-space: nowrap;
	}

	.action.ghost {
		background: transparent;
	}

	.close {
		display: grid;
		place-items: center;
		width: 40px;
		height: 40px;
		border: 0;
		border-radius: var(--r-sm);
		background: transparent;
		color: var(--text-1);
	}

	@media (max-width: 600px) {
		.sos {
			flex-wrap: wrap;
		}

		.actions {
			width: 100%;
		}
	}
</style>
