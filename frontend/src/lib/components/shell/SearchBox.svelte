<!-- Buscador con resultados (combobox accesible): nombre largo, corto o id del nodo. -->
<script lang="ts">
	import Search from '@lucide/svelte/icons/search';
	import X from '@lucide/svelte/icons/x';
	import { goto } from '$app/navigation';
	import { fmt } from '$lib/i18n/fmt.svelte';
	import { m } from '$lib/paraglide/messages';
	import { clock } from '$lib/stores/clock.svelte';
	import { live } from '$lib/stores/live.svelte';
	import { site } from '$lib/stores/site.svelte';
	import { nodeHref } from '$lib/utils/ids';
	import { displayName, shortName } from '$lib/utils/nodes';
	import { classify } from '$lib/utils/status';
	import { matches } from '$lib/utils/text';
	import StatusGlyph from '$lib/components/ui/StatusGlyph.svelte';
	import type { Node } from '$lib/api/types';

	interface Props {
		input?: HTMLInputElement | null;
	}

	let { input = $bindable(null) }: Props = $props();

	const uid = $props.id();
	let query = $state('');
	let open = $state(false);
	let active = $state(-1);

	const results = $derived.by(() => {
		const q = query.trim();
		if (!q) return [] as Node[];
		return live
			.nodeList()
			.filter((n) => matches(q, n.long_name, n.short_name, n.id))
			.sort((a, b) => b.last_heard - a.last_heard)
			.slice(0, 8);
	});

	function choose(node: Node) {
		query = '';
		open = false;
		active = -1;
		input?.blur();
		void goto(nodeHref(node.id));
	}

	function onKey(e: KeyboardEvent) {
		if (e.key === 'ArrowDown') {
			open = true;
			active = Math.min(results.length - 1, active + 1);
			e.preventDefault();
		} else if (e.key === 'ArrowUp') {
			active = Math.max(-1, active - 1);
			e.preventDefault();
		} else if (e.key === 'Enter') {
			const pick = results[active] ?? results[0];
			if (pick) {
				choose(pick);
				e.preventDefault();
			}
		} else if (e.key === 'Escape') {
			if (query) query = '';
			else input?.blur();
			open = false;
		}
	}
</script>

<div class="search" role="search">
	<Search size={18} aria-hidden="true" class="lead" />
	<input
		bind:this={input}
		bind:value={query}
		type="search"
		role="combobox"
		autocomplete="off"
		spellcheck="false"
		aria-label={m.search_label()}
		aria-expanded={open && query.trim().length > 0}
		aria-controls="{uid}-results"
		aria-autocomplete="list"
		aria-activedescendant={active >= 0 ? `${uid}-opt-${active}` : undefined}
		placeholder={m.search_placeholder()}
		oninput={() => {
			open = true;
			active = -1;
		}}
		onfocus={() => (open = true)}
		onblur={() => setTimeout(() => (open = false), 120)}
		onkeydown={onKey}
	/>
	{#if query}
		<button type="button" class="clear" aria-label={m.search_clear()} onclick={() => (query = '')}>
			<X size={16} aria-hidden="true" />
		</button>
	{/if}
	{#if open && query.trim()}
		<ul
			id="{uid}-results"
			role="listbox"
			class="menu-surface results"
			aria-label={m.search_label()}
		>
			{#each results as node, i (node.id)}
				<li
					id="{uid}-opt-{i}"
					role="option"
					aria-selected={i === active}
					class="menu-item"
					class:active={i === active}
					onpointerdown={(e) => {
						e.preventDefault();
						choose(node);
					}}
				>
					<StatusGlyph
						status={classify(node.last_heard, clock.now, site.data.thresholds)}
						infra={node.is_infra}
						fixed={node.is_fixed}
					/>
					<span class="name">{displayName(node)}</span>
					<span class="short">{shortName(node)}</span>
					<span class="ago">{fmt.relative(node.last_heard)}</span>
				</li>
			{:else}
				<li class="empty" role="option" aria-selected="false" aria-disabled="true">
					{m.search_no_results()}
				</li>
			{/each}
		</ul>
	{/if}
</div>

<style>
	.search {
		position: relative;
		display: flex;
		align-items: center;
		flex: 1;
		min-width: 0;
		max-width: 420px;
		height: 44px;
		border-radius: 999px;
		background: var(--fill-1);
		border: 1px solid var(--line);
	}

	.search :global(.lead) {
		position: absolute;
		left: 14px;
		color: var(--text-2);
		pointer-events: none;
	}

	input {
		flex: 1;
		min-width: 0;
		height: 100%;
		padding: 0 40px 0 40px;
		border: 0;
		border-radius: 999px;
		background: transparent;
		color: var(--text-1);
		font: inherit;
		font-size: 0.875rem;
	}

	input::placeholder {
		color: var(--text-2);
	}

	input::-webkit-search-cancel-button {
		display: none;
	}

	input:focus-visible {
		outline: 2px solid var(--focus);
		outline-offset: 1px;
	}

	.clear {
		position: absolute;
		right: 4px;
		display: grid;
		place-items: center;
		width: 36px;
		height: 36px;
		border: 0;
		border-radius: 50%;
		background: transparent;
		color: var(--text-2);
	}

	.results {
		position: absolute;
		top: calc(100% + 8px);
		left: 0;
		right: 0;
		max-width: none;
		margin: 0;
		list-style: none;
	}

	.results .menu-item {
		cursor: pointer;
	}

	.results .active {
		background: var(--fill-2);
	}

	.name {
		flex: 1;
		min-width: 0;
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}

	.short {
		font-size: 0.75rem;
		color: var(--text-2);
	}

	.ago {
		font-size: 0.75rem;
		color: var(--text-2);
		white-space: nowrap;
	}

	.empty {
		padding: 10px;
		color: var(--text-2);
		font-size: 0.875rem;
	}
</style>
