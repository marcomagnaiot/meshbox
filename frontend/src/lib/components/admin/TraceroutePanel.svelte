<!--
  Traceroutes de un nodo en el panel: el último con la ida y la vuelta salto por salto y los
  anteriores plegados. Con `sentAt` (recién pedido) consulta cada 4 s hasta que llega una
  respuesta más nueva o vence la espera, que crece con los saltos pedidos. Con `startedAt`, la
  espera se cuenta desde el pedido aunque el panel se haya abierto después.
-->
<script lang="ts">
	import { untrack } from 'svelte';
	import { radioApi } from '$lib/admin/radio';
	import type { Traceroute } from '$lib/api/types';
	import { fmt } from '$lib/i18n/fmt.svelte';
	import { m } from '$lib/paraglide/messages';
	import TracerouteHops from '$lib/components/node/TracerouteHops.svelte';
	import { hopsLabel } from '$lib/utils/traceroute';

	interface Props {
		node: string;
		name: (id: string) => string;
		/** Hora (del servidor) del pedido recién enviado; `null` si no se espera nada. */
		sentAt?: number | null;
		/** Hora de la PC en que se mandó el pedido (ms); si falta, la de abrir el panel. */
		startedAt?: number;
		hopLimit?: number;
	}

	let { node, name, sentAt = null, startedAt, hopLimit = 3 }: Props = $props();

	const LIMIT = 5;
	let traces = $state.raw<Traceroute[] | null>(null);
	let waiting = $state(false);
	let elapsed = $state(0);
	let timedOut = $state(false);

	const latest = $derived(traces?.[0] ?? null);
	const older = $derived(traces?.slice(1) ?? []);

	$effect(() => {
		// Historial al elegir otro nodo.
		const id = node;
		const ctrl = new AbortController();
		traces = null;
		radioApi
			.traceroutes(id, LIMIT, ctrl.signal)
			.then((t) => (traces = t))
			.catch(() => {
				if (!ctrl.signal.aborted) traces = [];
			});
		return () => ctrl.abort();
	});

	$effect(() => {
		// Pedido recién enviado: se espera una respuesta posterior.
		const since = sentAt;
		const id = node;
		if (!since) return;
		const start = untrack(() => startedAt) ?? Date.now();
		const hops = untrack(() => hopLimit);
		const deadline = start + Math.min(240, 45 * (hops + 1)) * 1000;
		let stopped = false;
		let timer: ReturnType<typeof setTimeout>;
		// Si la espera venció con el panel cerrado, se mira una sola vez si llegó la respuesta.
		waiting = Date.now() <= deadline;
		timedOut = false;
		elapsed = Math.round((Date.now() - start) / 1000);
		const tick = async (): Promise<void> => {
			if (stopped) return;
			elapsed = Math.round((Date.now() - start) / 1000);
			try {
				const t = await radioApi.traceroutes(id, LIMIT);
				if (stopped) return;
				if (t.some((x) => x.ts >= since - 2)) {
					traces = t;
					waiting = false;
					return;
				}
			} catch {
				// sin red: se reintenta en el próximo turno
			}
			if (Date.now() > deadline) {
				waiting = false;
				timedOut = true;
				return;
			}
			timer = setTimeout(tick, 4000);
		};
		timer = setTimeout(tick, Math.max(0, start + 3000 - Date.now()));
		return () => {
			stopped = true;
			clearTimeout(timer);
		};
	});
</script>

<section class="adm-stack trace" aria-label={m.node_traceroutes()}>
	<p class="head">{m.node_traceroutes()}</p>
	{#if waiting}
		<p class="adm-muted" role="status">{m.adm_trace_waiting({ seconds: elapsed })}</p>
	{:else if timedOut}
		<p class="adm-note warn" role="status">{m.adm_trace_timeout()}</p>
	{/if}
	{#if latest}
		<div class="item">
			<p class="when adm-muted">
				{m.node_traceroute_path({
					from: name(latest.from),
					to: name(latest.to),
					hops: hopsLabel(latest.route.length)
				})} · {fmt.relative(latest.ts)}
			</p>
			<TracerouteHops tr={latest} {name} />
		</div>
		{#if older.length}
			<details>
				<summary class="adm-muted">{m.adm_trace_older({ n: older.length })}</summary>
				<div class="adm-stack older">
					{#each older as tr (`${tr.ts}-${tr.from}-${tr.to}`)}
						<div class="item">
							<p class="when adm-muted">
								{m.node_traceroute_path({
									from: name(tr.from),
									to: name(tr.to),
									hops: hopsLabel(tr.route.length)
								})} · {fmt.relative(tr.ts)}
							</p>
							<TracerouteHops {tr} {name} />
						</div>
					{/each}
				</div>
			</details>
		{/if}
	{:else if traces && !waiting}
		<p class="adm-muted">{m.adm_trace_none()}</p>
	{/if}
</section>

<style>
	.head {
		margin: 0;
		font-size: 0.875rem;
		font-weight: 650;
	}

	.when {
		margin: 0 0 6px;
	}

	.older {
		margin-top: 10px;
	}

	details summary {
		cursor: pointer;
		padding: 4px 0;
	}
</style>
