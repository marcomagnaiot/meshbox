<!--
  Un traceroute como en la app: la ida y la vuelta salto por salto, con el SNR con que cada nodo
  recibió del anterior. Se usa en la ficha pública del nodo y en el panel.
-->
<script lang="ts">
	import type { Traceroute } from '$lib/api/types';
	import { fmt } from '$lib/i18n/fmt.svelte';
	import { m } from '$lib/paraglide/messages';
	import { hopsLabel, tracerouteLegs, type Hop } from '$lib/utils/traceroute';

	interface Props {
		tr: Traceroute;
		/** Nombre a mostrar de un nodo. */
		name: (id: string) => string;
	}

	let { tr, name }: Props = $props();

	const legs = $derived(tracerouteLegs(tr));
</script>

{#snippet leg(title: string, hops: Hop[])}
	<div class="leg">
		<p class="title">
			{title}
			<span class="count">· {hopsLabel(hops.length - 2)}</span>
		</p>
		<ol>
			{#each hops as h, i (`${i}-${h.id}`)}
				<li class:unknown={h.unknown}>
					<span class="node">{h.unknown ? m.trace_unknown() : name(h.id)}</span>
					{#if i > 0}
						<span class="snr">{h.snr === null ? '?' : fmt.db(h.snr)}</span>
					{/if}
				</li>
			{/each}
		</ol>
	</div>
{/snippet}

<div class="legs">
	{@render leg(m.trace_towards(), legs.towards)}
	{#if legs.back}
		{@render leg(m.trace_back(), legs.back)}
	{:else}
		<p class="none">{m.trace_no_back()}</p>
	{/if}
</div>

<style>
	.legs {
		display: grid;
		grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
		gap: 10px 18px;
	}

	.title {
		margin: 0 0 4px;
		font-size: 0.8125rem;
		font-weight: 650;
	}

	.count {
		font-weight: 400;
		color: var(--text-2);
	}

	ol {
		list-style: none;
		margin: 0;
		padding: 0;
		display: flex;
		flex-direction: column;
	}

	li {
		display: flex;
		align-items: baseline;
		justify-content: space-between;
		gap: 10px;
		padding: 3px 0 3px 16px;
		position: relative;
		font-size: 0.8125rem;
	}

	/* Una línea vertical une los saltos, como el recorrido en la app. */
	li::before {
		content: '';
		position: absolute;
		left: 4px;
		top: 50%;
		width: 7px;
		height: 7px;
		margin-top: -3.5px;
		border-radius: 50%;
		background: var(--accent);
	}

	li + li::after {
		content: '';
		position: absolute;
		left: 7px;
		bottom: 50%;
		height: 100%;
		width: 1px;
		background: var(--line);
	}

	li.unknown .node {
		color: var(--text-2);
		font-style: italic;
	}

	.node {
		min-width: 0;
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}

	.snr {
		flex: none;
		font-variant-numeric: tabular-nums;
		color: var(--text-2);
	}

	.none {
		margin: 0;
		font-size: 0.8125rem;
		color: var(--text-2);
	}
</style>
