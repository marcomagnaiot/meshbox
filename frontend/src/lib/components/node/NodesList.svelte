<!--
  Lista de nodos (17.1): búsqueda, filtros (estado, rol, infraestructura, con posición, con
  telemetría), orden y lista virtualizada. Es también la alternativa accesible al mapa.
-->
<script lang="ts">
	import ListFilter from '@lucide/svelte/icons/list-filter';
	import SearchX from '@lucide/svelte/icons/search-x';
	import X from '@lucide/svelte/icons/x';
	import { KNOWN_ROLES, roleLabel, statusLabel } from '$lib/i18n/labels';
	import { m } from '$lib/paraglide/messages';
	import { clock } from '$lib/stores/clock.svelte';
	import { live } from '$lib/stores/live.svelte';
	import { site } from '$lib/stores/site.svelte';
	import { filters, selection } from '$lib/stores/ui.svelte';
	import { filterNodes, sortNodes, type SortKey } from '$lib/utils/nodes';
	import { STATUSES } from '$lib/utils/status';
	import Chip from '$lib/components/ui/Chip.svelte';
	import EmptyState from '$lib/components/ui/EmptyState.svelte';
	import Skeleton from '$lib/components/ui/Skeleton.svelte';
	import StatusGlyph from '$lib/components/ui/StatusGlyph.svelte';
	import VirtualList from '$lib/components/ui/VirtualList.svelte';
	import FilterChips from '$lib/components/shell/FilterChips.svelte';
	import NodeCard from './NodeCard.svelte';

	interface Props {
		/** Muestra filtros avanzados y orden (página /nodos). */
		full?: boolean;
		/** Muestra los chips rápidos (en el celular están en la barra superior). */
		chips?: boolean;
	}

	let { full = false, chips = true }: Props = $props();

	let showFilters = $state(false);
	const uid = $props.id();

	const all = $derived(live.nodeList());
	const visible = $derived(
		sortNodes(
			filterNodes(all, filters.value, clock.now, site.data.thresholds),
			filters.sort,
			clock.now,
			site.data.thresholds
		)
	);
	const roles = $derived([...new Set([...KNOWN_ROLES, ...all.map((n) => n.role)])].sort());
	const sorts = $derived<{ value: SortKey; label: string }[]>([
		{ value: 'last_heard', label: m.sort_last_heard() },
		{ value: 'name', label: m.sort_name() },
		{ value: 'battery', label: m.sort_battery() },
		{ value: 'snr', label: m.sort_snr() },
		{ value: 'hops', label: m.sort_hops() }
	]);
</script>

<div class="nodes">
	<div class="head">
		<div class="search">
			<input
				type="search"
				placeholder={m.search_placeholder()}
				aria-label={m.search_label()}
				value={filters.value.query}
				oninput={(e) => filters.set('query', e.currentTarget.value)}
			/>
			{#if filters.value.query}
				<button
					type="button"
					class="clear"
					aria-label={m.search_clear()}
					onclick={() => filters.set('query', '')}
				>
					<X size={16} aria-hidden="true" />
				</button>
			{/if}
			{#if full}
				<button
					type="button"
					class="btn-icon"
					aria-label={m.filter_label()}
					aria-expanded={showFilters}
					aria-controls="{uid}-filters"
					onclick={() => (showFilters = !showFilters)}
				>
					<ListFilter size={20} aria-hidden="true" />
				</button>
			{/if}
		</div>
		{#if chips}<FilterChips />{/if}
		{#if full && showFilters}
			<div class="advanced" id="{uid}-filters">
				<fieldset>
					<legend>{m.filter_status()}</legend>
					<div class="row">
						{#each STATUSES as s (s)}
							<Chip
								pressed={filters.value.statuses.includes(s)}
								onclick={() => filters.toggleStatus(s)}
							>
								{#snippet lead()}<StatusGlyph status={s} size={14} />{/snippet}
								{statusLabel(s)}
							</Chip>
						{/each}
					</div>
				</fieldset>
				<div class="row">
					<label class="field">
						<span>{m.filter_role()}</span>
						<select
							value={filters.value.role}
							onchange={(e) => filters.set('role', e.currentTarget.value)}
						>
							<option value="">{m.filter_role_any()}</option>
							{#each roles as r (r)}<option value={r}>{roleLabel(r)}</option>{/each}
						</select>
					</label>
					<Chip pressed={filters.value.withPosition} onclick={() => filters.toggle('withPosition')}>
						{m.filter_with_position()}
					</Chip>
				</div>
				{#if filters.active > 0}
					<button type="button" class="link-btn" onclick={() => filters.clear()}
						>{m.filter_clear()}</button
					>
				{/if}
			</div>
		{/if}
		<div class="meta">
			<span class="count" aria-live="polite"
				>{m.nodes_count({ shown: visible.length, total: all.length })}</span
			>
			{#if full}
				<label class="sort">
					<span>{m.sort_label()}</span>
					<select
						value={filters.sort}
						onchange={(e) => (filters.sort = e.currentTarget.value as SortKey)}
					>
						{#each sorts as s (s.value)}<option value={s.value}>{s.label}</option>{/each}
					</select>
				</label>
			{/if}
		</div>
	</div>
	{#if !live.hasData}
		<div class="pad"><Skeleton lines={6} avatar label={m.nodes_loading()} /></div>
	{:else}
		<VirtualList items={visible} itemHeight={64} key={(n) => n.id} label={m.nodes_list_label()}>
			{#snippet row(node)}
				<NodeCard {node} selected={node.id === selection.nodeId} />
			{/snippet}
			{#snippet empty()}
				<EmptyState
					icon={SearchX}
					title={m.nodes_empty()}
					description={m.nodes_empty_hint()}
					compact
				>
					{#if filters.active > 0 || filters.value.query}
						<button
							type="button"
							class="link-btn"
							onclick={() => {
								filters.clear();
								filters.set('query', '');
							}}>{m.filter_clear()}</button
						>
					{/if}
				</EmptyState>
			{/snippet}
		</VirtualList>
	{/if}
</div>

<style>
	.nodes {
		display: flex;
		flex-direction: column;
		min-height: 0;
		height: 100%;
	}

	.head {
		flex: none;
		display: flex;
		flex-direction: column;
		gap: 8px;
		padding: 8px 12px;
	}

	.search {
		position: relative;
		display: flex;
		align-items: center;
		gap: 6px;
	}

	input[type='search'] {
		flex: 1;
		min-width: 0;
		height: 44px;
		padding: 0 40px 0 14px;
		border-radius: var(--r-sm);
		border: 1px solid var(--line);
		background: var(--fill-1);
		color: var(--text-1);
		font: inherit;
		font-size: 0.875rem;
	}

	input::-webkit-search-cancel-button {
		display: none;
	}

	input::placeholder {
		color: var(--text-2);
	}

	.clear {
		position: absolute;
		right: 52px;
		display: grid;
		place-items: center;
		width: 36px;
		height: 36px;
		border: 0;
		border-radius: 8px;
		background: transparent;
		color: var(--text-2);
	}

	.search:not(:has(.btn-icon)) .clear {
		right: 4px;
	}

	.advanced {
		display: flex;
		flex-direction: column;
		gap: 10px;
		padding: 10px;
		border-radius: var(--r-sm);
		background: var(--fill-1);
	}

	fieldset {
		border: 0;
		margin: 0;
		padding: 0;
	}

	legend {
		font-size: 0.75rem;
		font-weight: 650;
		color: var(--text-2);
		margin-bottom: 6px;
	}

	.row {
		display: flex;
		flex-wrap: wrap;
		gap: 8px;
		align-items: center;
	}

	.field,
	.sort {
		display: inline-flex;
		align-items: center;
		gap: 6px;
		font-size: 0.75rem;
		color: var(--text-2);
	}

	select {
		height: 36px;
		padding: 0 8px;
		border-radius: 8px;
		border: 1px solid var(--line);
		background: var(--surface-2);
		color: var(--text-1);
		font: inherit;
		font-size: 0.8125rem;
	}

	@media (pointer: coarse) {
		select {
			height: 44px;
		}
	}

	.meta {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 8px;
		min-height: 24px;
	}

	.count {
		font-size: 0.75rem;
		color: var(--text-2);
	}

	.link-btn {
		align-self: flex-start;
		border: 0;
		background: transparent;
		color: var(--accent-ink);
		font: inherit;
		font-size: 0.8125rem;
		font-weight: 600;
		min-height: 36px;
		padding: 0 4px;
		text-decoration: underline;
		text-underline-offset: 2px;
	}

	.pad {
		padding: 8px 16px;
	}

	.nodes :global(.viewport) {
		padding: 0 6px 12px;
	}
</style>
