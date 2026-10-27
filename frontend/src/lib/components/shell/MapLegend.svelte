<!-- Leyenda del mapa: forma y anillo además del color (16.1.10). -->
<script lang="ts">
	import { m } from '$lib/paraglide/messages';
	import StatusGlyph from '$lib/components/ui/StatusGlyph.svelte';
	import { statusLabel } from '$lib/i18n/labels';
	import { STATUSES } from '$lib/utils/status';

	interface Props {
		activity?: boolean;
	}

	let { activity = true }: Props = $props();
</script>

<div class="legend">
	<ul class="states">
		{#each STATUSES as s (s)}
			<li><StatusGlyph status={s} size={20} /> {statusLabel(s)}</li>
		{/each}
		<li><StatusGlyph status="active" infra size={20} /> {m.status_infra()}</li>
		<li><StatusGlyph status="active" fixed size={20} /> {m.status_fixed()}</li>
	</ul>
	<p class="note">{m.legend_fill()}</p>
	<ul class="lines">
		<li><span class="line good" aria-hidden="true"></span>SNR ≥ 5 dB</li>
		<li><span class="line fair" aria-hidden="true"></span>SNR 0 – 5 dB</li>
		<li><span class="line poor" aria-hidden="true"></span>SNR &lt; 0 dB</li>
	</ul>
	{#if activity}
		<ul class="activity">
			<li>
				<span class="ring" style="--c: var(--cat-1)" aria-hidden="true"
				></span>{m.port_POSITION_APP()}
			</li>
			<li>
				<span class="ring" style="--c: var(--cat-2)" aria-hidden="true"
				></span>{m.port_TEXT_MESSAGE_APP()}
			</li>
			<li>
				<span class="ring" style="--c: var(--cat-3)" aria-hidden="true"
				></span>{m.port_TELEMETRY_APP()}
			</li>
			<li>
				<span class="ring" style="--c: var(--cat-other)" aria-hidden="true"></span>{m.port_other()}
			</li>
		</ul>
	{/if}
</div>

<style>
	.legend {
		font-size: 0.8125rem;
	}

	ul {
		list-style: none;
		margin: 0 0 8px;
		padding: 0;
		display: grid;
		grid-template-columns: 1fr 1fr;
		gap: 6px 12px;
	}

	li {
		display: flex;
		align-items: center;
		gap: 8px;
	}

	.note {
		margin: 0 0 10px;
		color: var(--text-2);
		font-size: 0.75rem;
	}

	.line {
		display: inline-block;
		width: 26px;
		height: 0;
		border-top: 3px solid var(--success);
	}

	.line.fair {
		border-top-style: dashed;
		border-top-color: var(--warning);
	}

	.line.poor {
		border-top-style: dotted;
		border-top-color: var(--danger);
	}

	.ring {
		width: 14px;
		height: 14px;
		border-radius: 50%;
		border: 2.5px solid var(--c);
		flex: none;
	}
</style>
