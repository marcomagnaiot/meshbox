<!--
  Historial de posiciones (17.2): rango de 1 h a 7 d, recorrido en el mapa y reproducción con
  pausa. La velocidad estimada viene del servidor (haversine, sin movimientos chicos). Con
  movimiento reducido no hay reproducción animada; el deslizador sigue disponible.
-->
<script lang="ts">
	import Pause from '@lucide/svelte/icons/pause';
	import Play from '@lucide/svelte/icons/play';
	import { onDestroy } from 'svelte';
	import { publicApi } from '$lib/api/public';
	import { fmt } from '$lib/i18n/fmt.svelte';
	import { m } from '$lib/paraglide/messages';
	import { clock } from '$lib/stores/clock.svelte';
	import { selection, ui } from '$lib/stores/ui.svelte';
	import IconButton from '$lib/components/ui/IconButton.svelte';
	import Segmented from '$lib/components/ui/Segmented.svelte';
	import { HISTORY_RANGES } from './metrics';

	interface Props {
		nodeId: string;
	}

	let { nodeId }: Props = $props();

	const uid = $props.id();
	let range = $state<string>('86400');
	let loading = $state(false);
	let failed = $state(false);
	let playing = $state(false);
	let timer: ReturnType<typeof setInterval> | null = null;

	const track = $derived(selection.track);
	const cursor = $derived(selection.cursor ?? (track.length ? track.length - 1 : 0));
	const point = $derived(track[cursor]);
	const speed = $derived.by(() => {
		if (!track.length) return null;
		const p =
			selection.cursor !== null
				? track[selection.cursor]
				: [...track].reverse().find((x) => x.speed_kmh);
		return p?.speed_kmh ?? null;
	});

	$effect(() => {
		const id = nodeId;
		const span = Number(range);
		const ctrl = new AbortController();
		stop();
		loading = true;
		failed = false;
		const to = clock.exact();
		publicApi
			.positions(id, to - span, to, 500, ctrl.signal)
			.then((list) => {
				if (selection.nodeId !== id) return;
				selection.track = list;
				selection.cursor = null;
			})
			.catch((err) => {
				if (!(err instanceof DOMException)) failed = true;
			})
			.finally(() => (loading = false));
		return () => ctrl.abort();
	});

	function play() {
		if (track.length < 2) return;
		playing = true;
		if (selection.cursor === null || selection.cursor >= track.length - 1) selection.cursor = 0;
		const step = Math.max(60, Math.round(10_000 / track.length));
		timer = setInterval(() => {
			const next = (selection.cursor ?? 0) + 1;
			if (next >= track.length) {
				stop();
				return;
			}
			selection.cursor = next;
		}, step);
	}

	function stop() {
		playing = false;
		if (timer) clearInterval(timer);
		timer = null;
	}

	onDestroy(stop);
</script>

<section class="history" aria-labelledby="{uid}-title">
	<h2 id="{uid}-title" class="section-title">{m.node_history()}</h2>
	<Segmented
		label={m.node_history_range()}
		options={[...HISTORY_RANGES]}
		bind:value={range}
		size="sm"
	/>
	{#if failed}
		<p class="muted">{m.error_generic()}</p>
	{:else if !loading && track.length === 0}
		<p class="muted">{m.node_history_empty()}</p>
	{:else}
		<div class="player" class:busy={loading}>
			{#if !ui.reducedMotion}
				<IconButton
					icon={playing ? Pause : Play}
					label={playing ? m.node_pause() : m.node_play()}
					variant="fill"
					onclick={() => (playing ? stop() : play())}
					disabled={track.length < 2}
				/>
			{/if}
			<input
				type="range"
				min="0"
				max={Math.max(0, track.length - 1)}
				value={cursor}
				aria-label={m.node_playback_position()}
				aria-valuetext={point ? fmt.dateTime(point.ts) : ''}
				oninput={(e) => {
					stop();
					selection.cursor = Number(e.currentTarget.value);
				}}
			/>
		</div>
		<dl class="facts">
			<div>
				<dt>{m.node_position_time()}</dt>
				<dd class="tabular">{point ? fmt.dateTime(point.ts) : '—'}</dd>
			</div>
			<div>
				<dt>{m.node_speed()}</dt>
				<dd class="tabular">
					{speed ? fmt.unit(speed, 'kilometer-per-hour', 0) : m.node_stopped()}
				</dd>
			</div>
			<div>
				<dt class="sr-only">{m.node_history()}</dt>
				<dd class="count">{m.node_history_points({ count: track.length })}</dd>
			</div>
		</dl>
	{/if}
</section>

<style>
	.history {
		display: flex;
		flex-direction: column;
		gap: 10px;
	}

	.player {
		display: flex;
		align-items: center;
		gap: 10px;
		transition: opacity var(--dur-1);
	}

	.player.busy {
		opacity: 0.55;
	}

	input[type='range'] {
		flex: 1;
		min-height: 44px;
		accent-color: var(--accent);
	}

	.facts {
		display: grid;
		grid-template-columns: repeat(auto-fit, minmax(120px, 1fr));
		gap: 8px;
		margin: 0;
	}

	.facts div {
		display: flex;
		flex-direction: column;
	}

	dt {
		font-size: 0.75rem;
		color: var(--text-2);
	}

	dd {
		margin: 0;
		font-size: 0.875rem;
		font-weight: 600;
	}

	.count {
		color: var(--text-2);
		font-weight: 500;
	}

	.muted {
		margin: 0;
		color: var(--text-2);
		font-size: 0.875rem;
	}
</style>
