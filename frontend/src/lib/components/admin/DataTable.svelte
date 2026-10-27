<!--
  Tabla virtualizada del panel (18.2): solo dibuja las filas visibles, encabezado fijo, orden
  por columna (aria-sort), filas que se abren con clic, Enter o Espacio y flechas para moverse.
  aria-rowcount/aria-rowindex dan el total aunque no estén todas en el documento.
-->
<script lang="ts" generics="T">
	import ArrowDown from '@lucide/svelte/icons/arrow-down';
	import ArrowUp from '@lucide/svelte/icons/arrow-up';
	import { tick, type Snippet } from 'svelte';
	import type { Column } from './types';

	interface Props {
		rows: T[];
		columns: Column<T>[];
		rowKey: (row: T) => string | number;
		label: string;
		rowHeight?: number;
		/** Alto del área desplazable (CSS). */
		height?: string;
		/** Ancho mínimo: en pantallas angostas la tabla se desplaza de costado. */
		minWidth?: string;
		onrowclick?: (row: T) => void;
		selected?: string | number | null;
		rowClass?: (row: T) => string;
		empty?: Snippet;
		/** Orden inicial. */
		sortKey?: string | null;
		sortDir?: 'asc' | 'desc';
	}

	let {
		rows,
		columns,
		rowKey,
		label,
		rowHeight = 44,
		height = 'min(70vh, 640px)',
		minWidth = '640px',
		onrowclick,
		selected = null,
		rowClass,
		empty,
		sortKey = $bindable(null),
		sortDir = $bindable('desc')
	}: Props = $props();

	const HEADER_H = 40;
	const OVERSCAN = 8;
	let viewport: HTMLDivElement | null = $state(null);
	let scrollTop = $state(0);
	let viewH = $state(480);

	const template = $derived(columns.map((c) => c.width ?? 'minmax(0, 1fr)').join(' '));
	const sorted = $derived.by(() => {
		const col = columns.find((c) => c.key === sortKey);
		if (!col?.sort) return rows;
		const out = [...rows].sort(col.sort);
		return sortDir === 'desc' ? out.reverse() : out;
	});
	const start = $derived(Math.max(0, Math.floor((scrollTop - HEADER_H) / rowHeight) - OVERSCAN));
	const end = $derived(
		Math.min(sorted.length, Math.ceil((scrollTop + viewH) / rowHeight) + OVERSCAN)
	);
	const slice = $derived(sorted.slice(start, end));

	$effect(() => {
		if (!viewport) return;
		const ro = new ResizeObserver(([e]) => (viewH = e.contentRect.height));
		ro.observe(viewport);
		return () => ro.disconnect();
	});

	function toggleSort(c: Column<T>): void {
		if (!c.sort) return;
		if (sortKey === c.key) sortDir = sortDir === 'asc' ? 'desc' : 'asc';
		else {
			sortKey = c.key;
			sortDir = 'asc';
		}
	}

	async function focusRow(index: number): Promise<void> {
		if (!viewport || index < 0 || index >= sorted.length) return;
		const top = HEADER_H + index * rowHeight;
		if (top < viewport.scrollTop + HEADER_H) viewport.scrollTop = top - HEADER_H;
		else if (top + rowHeight > viewport.scrollTop + viewport.clientHeight)
			viewport.scrollTop = top + rowHeight - viewport.clientHeight;
		await tick();
		viewport.querySelector<HTMLElement>(`[data-index="${index}"]`)?.focus();
	}

	function onRowKey(e: KeyboardEvent, row: T, index: number): void {
		if (e.key === 'Enter' || e.key === ' ') {
			e.preventDefault();
			onrowclick?.(row);
		} else if (e.key === 'ArrowDown') {
			e.preventDefault();
			void focusRow(index + 1);
		} else if (e.key === 'ArrowUp') {
			e.preventDefault();
			void focusRow(index - 1);
		} else if (e.key === 'Home') {
			e.preventDefault();
			void focusRow(0);
		} else if (e.key === 'End') {
			e.preventDefault();
			void focusRow(sorted.length - 1);
		}
	}

	function cellText(c: Column<T>, row: T): string {
		const v = c.text?.(row);
		return v === null || v === undefined || v === '' ? '—' : String(v);
	}
</script>

<div
	class="dt-viewport"
	bind:this={viewport}
	style="height: {height}; --cols: {template}; --min-w: {minWidth}; --row-h: {rowHeight}px"
	onscroll={(e) => (scrollTop = e.currentTarget.scrollTop)}
>
	<div class="dt-table" role="table" aria-label={label} aria-rowcount={sorted.length + 1}>
		<div class="dt-row dt-head" role="row" aria-rowindex={1}>
			{#each columns as c (c.key)}
				<div
					class="dt-cell dt-th {c.align ?? 'start'}"
					role="columnheader"
					aria-sort={sortKey === c.key
						? sortDir === 'asc'
							? 'ascending'
							: 'descending'
						: undefined}
				>
					{#if c.sort}
						<button type="button" class="dt-sort" onclick={() => toggleSort(c)}>
							<span class:sr-only={c.srLabel}>{c.label}</span>
							{#if sortKey === c.key}
								{#if sortDir === 'asc'}<ArrowUp size={14} aria-hidden="true" />{:else}<ArrowDown
										size={14}
										aria-hidden="true"
									/>{/if}
							{/if}
						</button>
					{:else}
						<span class:sr-only={c.srLabel}>{c.label}</span>
					{/if}
				</div>
			{/each}
		</div>
		{#if sorted.length === 0}
			<div class="dt-empty" role="row">
				<div role="cell">{@render empty?.()}</div>
			</div>
		{:else}
			<div class="dt-canvas" role="rowgroup" style="height: {sorted.length * rowHeight}px">
				{#each slice as row, i (rowKey(row))}
					{@const index = start + i}
					<div
						class="dt-row dt-body {rowClass?.(row) ?? ''}"
						class:clickable={Boolean(onrowclick)}
						class:selected={selected !== null && rowKey(row) === selected}
						role="row"
						aria-rowindex={index + 2}
						aria-selected={onrowclick ? selected !== null && rowKey(row) === selected : undefined}
						tabindex={onrowclick ? 0 : undefined}
						data-index={index}
						style="transform: translateY({index * rowHeight}px)"
						onclick={() => onrowclick?.(row)}
						onkeydown={onrowclick ? (e) => onRowKey(e, row, index) : undefined}
					>
						{#each columns as c (c.key)}
							<div class="dt-cell {c.align ?? 'start'}" role="cell">
								{#if c.cell}{@render c.cell(row)}{:else}{cellText(c, row)}{/if}
							</div>
						{/each}
					</div>
				{/each}
			</div>
		{/if}
	</div>
</div>

<style>
	.dt-viewport {
		position: relative;
		overflow: auto;
		overscroll-behavior: contain;
		border-top: 1px solid var(--line);
	}

	.dt-table {
		min-width: var(--min-w);
	}

	.dt-row {
		display: grid;
		grid-template-columns: var(--cols);
		align-items: center;
		column-gap: 12px;
		padding: 0 16px;
	}

	.dt-head {
		position: sticky;
		top: 0;
		z-index: 1;
		height: 40px;
		background: var(--surface-2);
		border-bottom: 1px solid var(--line);
	}

	.dt-th {
		font-size: 0.75rem;
		font-weight: 650;
		color: var(--text-2);
		text-transform: uppercase;
		letter-spacing: 0.02em;
	}

	.dt-sort {
		display: inline-flex;
		align-items: center;
		gap: 4px;
		min-height: 32px;
		padding: 0;
		border: 0;
		background: transparent;
		color: inherit;
		font: inherit;
		text-transform: inherit;
		letter-spacing: inherit;
		cursor: pointer;
	}

	.dt-canvas {
		position: relative;
	}

	.dt-body {
		position: absolute;
		top: 0;
		left: 0;
		right: 0;
		height: var(--row-h);
		border-bottom: 1px solid var(--line);
		font-size: 0.8125rem;
	}

	.dt-body.clickable {
		cursor: pointer;
	}

	.dt-body.clickable:hover {
		background: var(--fill-1);
	}

	.dt-body:focus-visible {
		outline: 2px solid var(--focus);
		outline-offset: -2px;
	}

	.dt-body.selected {
		background: var(--accent-soft);
	}

	.dt-cell {
		min-width: 0;
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
		font-variant-numeric: tabular-nums;
	}

	.dt-cell.end {
		text-align: right;
		justify-self: end;
	}

	.dt-cell.center {
		text-align: center;
		justify-self: center;
	}

	.dt-empty {
		padding: 24px 16px;
	}
</style>
