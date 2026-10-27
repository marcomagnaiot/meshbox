<!--
  Estado de un servicio o conector: punto con forma además de color (lleno, hueco, aspa) y
  texto. `active` es booleano (o null sin datos) y `state` el texto de systemd/conector.
-->
<script lang="ts">
	import { m } from '$lib/paraglide/messages';

	interface Props {
		active: boolean | null | undefined;
		state?: string | null;
		/** Texto propio (si no, Funcionando/Detenido/Sin datos). */
		label?: string;
	}

	let { active, state = null, label }: Props = $props();
	const failed = $derived(state === 'failed' || state === 'error');
	const tone = $derived(failed ? 'bad' : active === true ? 'ok' : active === false ? 'off' : 'unk');
	const text = $derived(
		label ??
			(failed
				? m.adm_svc_failed()
				: active === true
					? m.adm_svc_active()
					: active === false
						? m.adm_svc_inactive()
						: m.adm_svc_unknown())
	);
	const showState = $derived(Boolean(state) && !['active', 'inactive'].includes(state ?? ''));
</script>

<span class="pill {tone}">
	<span class="dot" aria-hidden="true"></span>
	<span>{text}</span>{#if showState}<span class="state">({state})</span>{/if}
</span>

<style>
	.pill {
		display: inline-flex;
		align-items: center;
		gap: 6px;
		font-size: 0.8125rem;
		font-weight: 600;
		white-space: nowrap;
	}

	.state {
		font-weight: 400;
		color: var(--text-2);
	}

	.dot {
		width: 10px;
		height: 10px;
		border-radius: 50%;
		flex: none;
	}

	.ok .dot {
		background: var(--success);
		box-shadow: 0 0 0 2px var(--success-soft);
	}

	.off .dot {
		border: 2px solid var(--text-3);
		background: transparent;
	}

	.unk .dot {
		border: 2px dashed var(--text-3);
		background: transparent;
	}

	.bad .dot {
		border-radius: 2px;
		background: var(--danger);
		transform: rotate(45deg);
	}
</style>
