<!--
  Extracto del mapa base (16.5): estado, descarga de una caja con zoom máximo (pmtiles extract
  del build diario de Protomaps), progreso y borrado.
-->
<script lang="ts">
	import Download from '@lucide/svelte/icons/download';
	import Trash2 from '@lucide/svelte/icons/trash-2';
	import { onMount } from 'svelte';
	import * as adminApi from '$lib/admin/api';
	import { problemText } from '$lib/admin/errors';
	import { Resource } from '$lib/admin/resource.svelte';
	import { fmt } from '$lib/i18n/fmt.svelte';
	import { m } from '$lib/paraglide/messages';
	import { site } from '$lib/stores/site.svelte';
	import { toasts } from '$lib/stores/ui.svelte';
	import Button from '$lib/components/ui/Button.svelte';
	import ConfirmAction from '../ConfirmAction.svelte';
	import JobProgress from '../JobProgress.svelte';
	import KeyValue from '../KeyValue.svelte';
	import MapPicker from '../MapPicker.svelte';
	import NumberField from '../NumberField.svelte';
	import Panel from '../Panel.svelte';
	import ProblemNote from '../ProblemNote.svelte';
	import TextField from '../TextField.svelte';

	interface Props {
		/** Límites del sitio para proponer la caja. */
		siteBounds: number[] | null;
	}

	let { siteBounds }: Props = $props();
	const status = new Resource(() => adminApi.site.tiles());
	let bbox = $state<number[] | null>(null);
	let center = $state<number[]>([0, 0]);
	let zoom = $state<number | null>(10);
	let maxzoom = $state<number | null>(14);
	let source = $state('');
	let starting = $state(false);
	let error = $state<string | null>(null);
	let deleteOpen = $state(false);
	let stopPoll: (() => void) | null = null;

	const job = $derived(status.data?.job ?? null);
	const running = $derived(job?.state === 'running');
	const area = $derived(bbox ? Math.abs((bbox[2] - bbox[0]) * (bbox[3] - bbox[1])) : 0);

	onMount(() => {
		bbox = siteBounds ? [...siteBounds] : null;
		center = [...site.data.center];
		zoom = Math.max(6, site.data.zoom - 2);
		void status.load().then((s) => {
			if (s?.job.state === 'running') follow();
		});
		return () => stopPoll?.();
	});

	function follow(): void {
		stopPoll?.();
		stopPoll = status.poll(2000);
		const check = setInterval(() => {
			if (status.data?.job.state !== 'running') {
				clearInterval(check);
				stopPoll?.();
				stopPoll = null;
				if (status.data?.job.state === 'done') {
					toasts.show(m.adm_tiles_done(), { kind: 'success' });
					void site.load(true);
				}
			}
		}, 1000);
	}

	async function start(): Promise<void> {
		if (!bbox || area > 25) {
			error = m.adm_tiles_box_invalid();
			return;
		}
		starting = true;
		error = null;
		try {
			await adminApi.site.downloadTiles(bbox, maxzoom ?? 14, source.trim() || null);
			await status.load();
			follow();
		} catch (err) {
			error = problemText(err);
		} finally {
			starting = false;
		}
	}
</script>

<Panel title={m.adm_tiles_title()} description={m.adm_tiles_desc()}>
	<div class="adm-stack">
		{#if status.error && !status.data}
			<ProblemNote error={status.error} onretry={() => status.load()} />
		{:else if status.data}
			{@const st = status.data.store}
			<KeyValue
				columns={3}
				items={[
					{
						label: m.adm_status(),
						value: st?.available ? m.adm_tiles_available() : m.adm_tiles_missing()
					},
					{ label: m.adm_tiles_size(), value: st?.available ? fmt.bytes(st.size) : null },
					{
						label: m.adm_tiles_zooms(),
						value: st?.available ? `${st.min_zoom ?? 0}–${st.max_zoom ?? '?'}` : null
					},
					{
						label: m.adm_tiles_bounds(),
						value: st?.bounds ? st.bounds.map((v) => fmt.number(v, 3)).join(', ') : null
					},
					{ label: m.adm_tiles_served(), value: st ? fmt.number(st.served, 0) : null }
				]}
			/>
			{#if job && job.state !== 'idle'}
				<JobProgress
					label={m.adm_tiles_title()}
					state={job.state}
					message={[job.progress.at(-1), job.bytes ? fmt.bytes(job.bytes) : '']
						.filter(Boolean)
						.join(' · ')}
					error={job.error}
				/>
			{/if}
		{/if}

		<MapPicker
			bind:center
			bind:zoom
			bind:bounds={bbox}
			mode="bbox"
			label={m.adm_tiles_map()}
			height="280px"
		/>
		<div class="adm-grid">
			<TextField
				label={m.adm_tiles_box()}
				value={bbox ? bbox.join(', ') : ''}
				readonly
				mono
				hint={bbox ? m.adm_tiles_area({ area: fmt.number(area, 2) }) : m.adm_tiles_box_hint()}
			/>
			<NumberField
				label={m.adm_tiles_maxzoom()}
				hint={m.adm_tiles_maxzoom_hint()}
				bind:value={maxzoom}
				min={6}
				max={15}
				step={1}
			/>
			<TextField
				label={m.adm_tiles_source()}
				hint={m.adm_tiles_source_hint()}
				bind:value={source}
				type="url"
				mono
				placeholder="https://…/AAAAMMDD.pmtiles"
			/>
		</div>
		{#if error}<p class="adm-note danger" role="alert">{error}</p>{/if}
		<div class="adm-row">
			<Button
				variant="primary"
				icon={Download}
				loading={starting}
				disabled={running || !bbox}
				onclick={start}>{m.adm_tiles_download()}</Button
			>
			{#if status.data?.store?.available}
				<Button variant="ghost" icon={Trash2} disabled={running} onclick={() => (deleteOpen = true)}
					>{m.adm_tiles_delete()}</Button
				>
			{/if}
		</div>
	</div>
</Panel>

<ConfirmAction
	bind:open={deleteOpen}
	title={m.adm_tiles_delete_title()}
	description={m.adm_tiles_delete_desc()}
	confirmLabel={m.adm_delete()}
	danger
	action={() => adminApi.site.deleteTiles()}
	onsuccess={() => {
		void status.load();
		void site.load(true);
	}}
/>
