<!--
  Barras horizontales como tabla (cada fila: categoría, barra con su valor y proporción).
  Una sola serie y un solo color para todas las barras (categorías nominales); la cola se
  agrupa en "Otros". La tabla es a la vez el gráfico y su equivalente accesible.
-->
<script lang="ts">
	import { fmt } from '$lib/i18n/fmt.svelte';

	interface Row {
		key: string;
		label: string;
		value: number;
	}

	interface Props {
		rows: Row[];
		caption: string;
		labelHeader: string;
		valueHeader: string;
		shareHeader: string;
		/** Cantidad máxima de filas; el resto se suma en `otherLabel`. */
		max?: number;
		otherLabel?: string;
		/** Mantener el orden recibido (categorías ordinales, como los saltos). */
		keepOrder?: boolean;
	}

	let {
		rows,
		caption,
		labelHeader,
		valueHeader,
		shareHeader,
		max = 8,
		otherLabel,
		keepOrder = false
	}: Props = $props();

	const prepared = $derived.by(() => {
		const list = keepOrder ? [...rows] : [...rows].sort((a, b) => b.value - a.value);
		if (!keepOrder && otherLabel && list.length > max) {
			const head = list.slice(0, max - 1);
			const rest = list.slice(max - 1).reduce((s, r) => s + r.value, 0);
			head.push({ key: '__other', label: otherLabel, value: rest });
			return head;
		}
		return list;
	});
	const total = $derived(prepared.reduce((s, r) => s + r.value, 0));
	const top = $derived(Math.max(1, ...prepared.map((r) => r.value)));
</script>

<table class="bars">
	<caption class="sr-only">{caption}</caption>
	<thead class="sr-only">
		<tr
			><th scope="col">{labelHeader}</th><th scope="col">{valueHeader}</th><th scope="col"
				>{shareHeader}</th
			></tr
		>
	</thead>
	<tbody>
		{#each prepared as row (row.key)}
			<tr>
				<th scope="row">{row.label}</th>
				<td class="cell">
					<span class="track">
						<span class="bar" style="width: {(row.value / top) * 100}%"></span>
					</span>
					<span class="value tabular">{fmt.number(row.value, 0)}</span>
				</td>
				<td class="share tabular">{total ? fmt.percent((row.value / total) * 100, 0) : '—'}</td>
			</tr>
		{/each}
	</tbody>
</table>

<style>
	.bars {
		width: 100%;
		border-collapse: collapse;
		font-size: 0.8125rem;
	}

	th {
		text-align: left;
		font-weight: 500;
		padding: 6px 8px 6px 0;
		white-space: nowrap;
		max-width: 40%;
		overflow: hidden;
		text-overflow: ellipsis;
		color: var(--text-1);
	}

	td {
		padding: 6px 0;
	}

	.cell {
		display: flex;
		align-items: center;
		gap: 8px;
		width: 100%;
	}

	.track {
		flex: 1;
		display: block;
		min-width: 40px;
	}

	.bar {
		display: block;
		height: 12px;
		min-width: 2px;
		border-radius: 0 4px 4px 0;
		background: var(--chart-line);
	}

	.value {
		min-width: 3.5ch;
		text-align: right;
		font-weight: 650;
	}

	.share {
		width: 4.5ch;
		text-align: right;
		color: var(--text-2);
		padding-left: 8px;
	}

	tr + tr th,
	tr + tr td {
		border-top: 1px solid var(--line);
	}
</style>
