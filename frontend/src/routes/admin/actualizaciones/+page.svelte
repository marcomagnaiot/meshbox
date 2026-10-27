<!--
  Actualizaciones (23.5, 18.2): versión actual, versiones instaladas en el equipo, versiones
  disponibles con notas, instalar (privd verifica la firma), seguir el trabajo, volver a la
  anterior y búsqueda automática.
-->
<script lang="ts">
	import ArrowDownToLine from '@lucide/svelte/icons/arrow-down-to-line';
	import RefreshCw from '@lucide/svelte/icons/refresh-cw';
	import Undo2 from '@lucide/svelte/icons/undo-2';
	import { onMount } from 'svelte';
	import * as adminApi from '$lib/admin/api';
	import { NetworkError } from '$lib/api/client';
	import { Busy, Resource } from '$lib/admin/resource.svelte';
	import type { PrivJob, ReleaseInfo } from '$lib/admin/types';
	import { fmt } from '$lib/i18n/fmt.svelte';
	import { m } from '$lib/paraglide/messages';
	import { toasts } from '$lib/stores/ui.svelte';
	import Button from '$lib/components/ui/Button.svelte';
	import Skeleton from '$lib/components/ui/Skeleton.svelte';
	import Toggle from '$lib/components/ui/Toggle.svelte';
	import ConfirmAction from '$lib/components/admin/ConfirmAction.svelte';
	import JobProgress from '$lib/components/admin/JobProgress.svelte';
	import KeyValue from '$lib/components/admin/KeyValue.svelte';
	import PageHeader from '$lib/components/admin/PageHeader.svelte';
	import Panel from '$lib/components/admin/Panel.svelte';
	import ProblemNote from '$lib/components/admin/ProblemNote.svelte';
	import TextField from '$lib/components/admin/TextField.svelte';

	const status = new Resource(() => adminApi.updates.status());
	const busy = new Busy();
	let installing = $state<ReleaseInfo | null>(null);
	let installOpen = $state(false);
	let rollbackOpen = $state(false);
	let job = $state<PrivJob | null>(null);
	let jobId = $state<string | null>(null);
	let restarting = $state(false);
	let autoCheck = $state(true);
	let source = $state('');
	let settingsLoaded = false;
	let timer: ReturnType<typeof setTimeout> | null = null;

	onMount(() => {
		void status.load().then((s) => {
			if (s && !settingsLoaded) {
				autoCheck = s.auto_check;
				source = s.source;
				settingsLoaded = true;
			}
			const lastJob = s?.local.job;
			if (lastJob && lastJob.state === 'running') follow(lastJob.job);
		});
		return () => {
			if (timer) clearTimeout(timer);
		};
	});

	const d = $derived(status.data);
	const current = $derived(d?.current ?? '');

	function newer(v: string): boolean {
		const a = v.split('.').map(Number);
		const b = current.split('.').map(Number);
		for (let i = 0; i < 3; i++) if ((a[i] ?? 0) !== (b[i] ?? 0)) return (a[i] ?? 0) > (b[i] ?? 0);
		return false;
	}

	/** Sigue el trabajo de privd; si el servicio se reinicia, espera a que vuelva y recarga. */
	function follow(id: string): void {
		jobId = id;
		const tick = async () => {
			try {
				const j = await adminApi.updates.job(id);
				job = j;
				restarting = false;
				if (j.state === 'running') timer = setTimeout(tick, 2000);
				else {
					if (j.state === 'succeeded') {
						toasts.show(m.adm_update_done(), { kind: 'success' });
						setTimeout(() => location.reload(), 2500);
					}
					void status.load();
				}
			} catch (err) {
				// meshbox se reinicia durante la instalación: se reintenta hasta que vuelva.
				if (err instanceof NetworkError) restarting = true;
				timer = setTimeout(tick, 3000);
			}
		};
		void tick();
	}

	async function saveSettings(): Promise<void> {
		await busy.run('settings', () => adminApi.updates.settings(autoCheck, source.trim() || null), {
			success: m.adm_saved()
		});
	}

	async function checkNow(): Promise<void> {
		await busy.run('check', async () => {
			const s = await adminApi.updates.status(true);
			status.data = s;
		});
	}
</script>

<PageHeader slug="actualizaciones">
	{#snippet actions()}
		<Button size="sm" icon={RefreshCw} loading={busy.is('check')} onclick={checkNow}
			>{m.adm_update_check()}</Button
		>
	{/snippet}
</PageHeader>

{#if status.error && !d}
	<ProblemNote error={status.error} onretry={() => status.load()} />
{:else if !d}
	<Skeleton lines={6} label={m.loading()} />
{:else}
	<div class="adm-stack">
		{#if job || restarting}
			<Panel title={m.adm_update_job()}>
				{#if restarting}<p class="adm-note warn" role="status">{m.adm_update_restarting()}</p>{/if}
				{#if job}
					<JobProgress
						label={m.adm_update_job()}
						state={job.state}
						progress={job.progress}
						step={job.step}
						message={job.message}
						error={job.state === 'failed' ? (job.message ?? job.error_code) : null}
					/>
					<p class="adm-muted">{m.adm_update_job_id({ id: jobId ?? '' })}</p>
				{/if}
			</Panel>
		{/if}

		<div class="adm-grid two">
			<Panel title={m.adm_update_installed()}>
				<KeyValue
					items={[
						{ label: m.adm_update_current(), value: d.current },
						{ label: m.adm_update_latest(), value: d.latest ?? '—' },
						{
							label: m.adm_update_local(),
							value: d.local.installed?.join(', ') ?? d.local.error ?? '—'
						},
						{ label: m.adm_update_previous(), value: d.local.previous ?? '—' },
						{
							label: m.adm_update_last(),
							value:
								typeof d.local.last_update === 'number'
									? fmt.dateTime(d.local.last_update)
									: (d.local.last_update ?? '—')
						}
					]}
				/>
				{#if d.local.previous}
					<div class="adm-row action">
						<Button icon={Undo2} onclick={() => (rollbackOpen = true)}>
							{m.adm_update_rollback({ version: d.local.previous })}
						</Button>
					</div>
				{/if}
			</Panel>

			<Panel title={m.adm_update_settings()}>
				<div class="adm-stack">
					<Toggle
						label={m.adm_update_auto()}
						hint={m.adm_update_auto_hint()}
						bind:checked={autoCheck}
					/>
					<TextField label={m.adm_update_source()} bind:value={source} type="url" mono />
					<div class="adm-row end">
						<Button size="sm" variant="primary" loading={busy.is('settings')} onclick={saveSettings}
							>{m.adm_save()}</Button
						>
					</div>
				</div>
			</Panel>
		</div>

		{#if d.error}<p class="adm-note warn">{d.error}</p>{/if}

		<Panel title={m.adm_update_releases()}>
			{#if d.releases.length === 0}
				<p class="adm-muted">{m.adm_update_none()}</p>
			{:else}
				<ul class="releases">
					{#each d.releases as r (r.version)}
						<li>
							<div class="rel-head">
								<strong>{r.name}</strong>
								<span class="adm-mono">{r.version}</span>
								{#if r.version === d.current}<span class="adm-badge accent"
										>{m.adm_update_this()}</span
									>{/if}
								{#if r.prerelease}<span class="adm-badge warn">{m.adm_update_pre()}</span>{/if}
								{#if r.signed}<span class="adm-badge ok">{m.adm_update_signed()}</span>{:else}<span
										class="adm-badge danger">{m.adm_update_unsigned()}</span
									>{/if}
								{#if r.published_at}<span class="adm-muted"
										>{fmt.date(Date.parse(r.published_at) / 1000)}</span
									>{/if}
								{#if newer(r.version) && r.has_package && r.signed}
									<Button
										size="sm"
										variant="primary"
										icon={ArrowDownToLine}
										disabled={job?.state === 'running'}
										onclick={() => {
											installing = r;
											installOpen = true;
										}}>{m.adm_update_install()}</Button
									>
								{/if}
							</div>
							{#if r.notes}
								<details>
									<summary class="adm-muted">{m.adm_update_notes()}</summary>
									<pre class="notes">{r.notes}</pre>
								</details>
							{/if}
						</li>
					{/each}
				</ul>
			{/if}
		</Panel>
	</div>
{/if}

{#if installing}
	<ConfirmAction
		bind:open={installOpen}
		title={m.adm_update_install_title({ version: installing.version })}
		description={m.adm_update_install_desc()}
		confirmLabel={m.adm_update_install()}
		requireText={installing.version}
		action={() => adminApi.updates.install(installing!.version)}
		onsuccess={(r) => follow((r as { job: string }).job)}
	/>
{/if}

<ConfirmAction
	bind:open={rollbackOpen}
	title={m.adm_update_rollback_title({ version: d?.local.previous ?? '' })}
	description={m.adm_update_rollback_desc()}
	confirmLabel={m.adm_update_rollback_action()}
	danger
	action={() => adminApi.updates.rollback()}
	onsuccess={(r) => follow((r as { job: string }).job)}
/>

<style>
	.action {
		margin-top: 14px;
	}

	.releases {
		list-style: none;
		margin: 0;
		padding: 0;
		display: flex;
		flex-direction: column;
		gap: 14px;
	}

	.releases li {
		padding-bottom: 14px;
		border-bottom: 1px solid var(--line);
	}

	.releases li:last-child {
		border-bottom: 0;
		padding-bottom: 0;
	}

	.rel-head {
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		gap: 6px 10px;
	}

	.notes {
		margin: 8px 0 0;
		white-space: pre-wrap;
		font: inherit;
		font-size: 0.8125rem;
		color: var(--text-2);
		max-height: 320px;
		overflow: auto;
	}

	details summary {
		cursor: pointer;
		padding: 6px 0;
	}
</style>
