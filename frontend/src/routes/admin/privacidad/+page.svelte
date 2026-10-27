<!--
  Privacidad y retención (18.2, 30): ignorar lo que llega por MQTT, política de precisión de las
  posiciones, días de retención por tabla y purga inmediata.
-->
<script lang="ts">
	import Eraser from '@lucide/svelte/icons/eraser';
	import { onMount } from 'svelte';
	import * as adminApi from '$lib/admin/api';
	import { problemFields, problemText } from '$lib/admin/errors';
	import type { PrivacyCfg, RetentionCfg } from '$lib/admin/types';
	import { fmt } from '$lib/i18n/fmt.svelte';
	import { m } from '$lib/paraglide/messages';
	import { toasts } from '$lib/stores/ui.svelte';
	import Button from '$lib/components/ui/Button.svelte';
	import Skeleton from '$lib/components/ui/Skeleton.svelte';
	import Toggle from '$lib/components/ui/Toggle.svelte';
	import ConfirmAction from '$lib/components/admin/ConfirmAction.svelte';
	import NumberField from '$lib/components/admin/NumberField.svelte';
	import PageHeader from '$lib/components/admin/PageHeader.svelte';
	import Panel from '$lib/components/admin/Panel.svelte';
	import ProblemNote from '$lib/components/admin/ProblemNote.svelte';
	import SelectField from '$lib/components/admin/SelectField.svelte';

	let privacy = $state<PrivacyCfg | null>(null);
	let retention = $state<RetentionCfg | null>(null);
	let loadError = $state<unknown>(null);
	let saving = $state(false);
	let errors = $state<Record<string, string>>({});
	let formError = $state<string | null>(null);
	let purgeOpen = $state(false);
	let purged = $state<Record<string, number> | null>(null);

	const TABLES: { key: keyof RetentionCfg; label: () => string }[] = [
		{ key: 'packets', label: m.adm_ret_packets },
		{ key: 'positions', label: m.adm_ret_positions },
		{ key: 'telemetry_raw', label: m.adm_ret_telemetry },
		{ key: 'rollup_hourly', label: m.adm_ret_rollups },
		{ key: 'messages', label: m.adm_ret_messages },
		{ key: 'radio_messages', label: m.adm_ret_radio_messages },
		{ key: 'traceroutes', label: m.adm_ret_traceroutes },
		{ key: 'links', label: m.adm_ret_links },
		{ key: 'alerts', label: m.adm_ret_alerts },
		{ key: 'audit', label: m.adm_ret_audit }
	];

	async function load(): Promise<void> {
		try {
			const d = await adminApi.site.privacy();
			privacy = d.privacy;
			retention = d.retention;
			loadError = null;
		} catch (err) {
			loadError = err;
		}
	}

	onMount(() => {
		void load();
	});

	async function save(e: Event): Promise<void> {
		e.preventDefault();
		if (!privacy || !retention) return;
		const errs: Record<string, string> = {};
		for (const t of TABLES) {
			const v = retention[t.key];
			if (!Number.isInteger(v) || v < 1) errs[`retention.${t.key}`] = m.adm_min_value({ min: 1 });
		}
		if (
			privacy.position_policy === 'degrade' &&
			!(privacy.degrade_meters >= 50 && privacy.degrade_meters <= 50000)
		)
			errs['privacy.degrade_meters'] = m.adm_field_invalid();
		errors = errs;
		if (Object.keys(errs).length) {
			formError = m.adm_fix_fields();
			return;
		}
		saving = true;
		formError = null;
		try {
			await adminApi.site.putPrivacy({ privacy, retention });
			toasts.show(m.adm_saved(), { kind: 'success' });
		} catch (err) {
			errors = problemFields(err);
			formError = problemText(err);
		} finally {
			saving = false;
		}
	}
</script>

<PageHeader slug="privacidad" />

{#if loadError && !privacy}
	<ProblemNote error={loadError} onretry={load} />
{:else if !privacy || !retention}
	<Skeleton lines={8} label={m.loading()} />
{:else}
	<div class="adm-stack">
		<form class="adm-stack" onsubmit={save} novalidate>
			<Panel title={m.adm_privacy_sources()}>
				<div class="adm-stack">
					<Toggle
						label={m.adm_privacy_ignore_mqtt()}
						hint={m.adm_privacy_ignore_mqtt_hint()}
						bind:checked={privacy.ignore_via_mqtt}
					/>
					<div class="adm-grid">
						<SelectField
							label={m.adm_privacy_policy()}
							bind:value={privacy.position_policy}
							options={[
								{ value: 'as_received', label: m.adm_privacy_as_received() },
								{ value: 'degrade', label: m.adm_privacy_degrade() }
							]}
							hint={privacy.position_policy === 'degrade'
								? m.adm_privacy_degrade_hint()
								: m.adm_privacy_as_received_hint()}
						/>
						{#if privacy.position_policy === 'degrade'}
							<NumberField
								label={m.adm_privacy_meters()}
								bind:value={privacy.degrade_meters}
								min={50}
								max={50000}
								step={50}
								unit="m"
								error={errors['privacy.degrade_meters']}
							/>
						{/if}
					</div>
				</div>
			</Panel>

			<Panel title={m.adm_retention()} description={m.adm_retention_desc()}>
				<div class="adm-grid">
					{#each TABLES as t (t.key)}
						<NumberField
							label={t.label()}
							bind:value={retention[t.key]}
							min={1}
							step={1}
							unit={m.adm_days_unit()}
							error={errors[`retention.${t.key}`]}
						/>
					{/each}
				</div>
			</Panel>

			{#if formError}<p class="adm-note danger" role="alert">{formError}</p>{/if}
			<div class="adm-row end">
				<Button type="submit" variant="primary" loading={saving}>{m.adm_save()}</Button>
			</div>
		</form>

		<Panel title={m.adm_purge_now()} description={m.adm_purge_now_desc()} tone="danger">
			<div class="adm-stack">
				{#if purged}
					<ul class="purged" role="status">
						{#each Object.entries(purged) as [k, v] (k)}
							<li><span class="adm-mono">{k}</span><span>{fmt.number(v, 0)}</span></li>
						{/each}
					</ul>
				{/if}
				<div class="adm-row">
					<Button variant="danger" icon={Eraser} onclick={() => (purgeOpen = true)}
						>{m.adm_purge_now()}</Button
					>
				</div>
			</div>
		</Panel>

		<p class="adm-muted">
			{m.adm_privacy_notice_where()}
			<a class="adm-link" href="/admin/sitio">{m.admin_section_site()}</a>
		</p>
	</div>
{/if}

<ConfirmAction
	bind:open={purgeOpen}
	title={m.adm_purge_now_title()}
	description={m.adm_purge_now_confirm()}
	confirmLabel={m.adm_purge_now()}
	danger
	action={() => adminApi.site.purge()}
	onsuccess={(r) => (purged = (r as { deleted: Record<string, number> }).deleted)}
/>

<style>
	.purged {
		margin: 0;
		padding: 0;
		list-style: none;
		display: grid;
		grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
		gap: 6px 20px;
		font-size: 0.8125rem;
	}

	.purged li {
		display: flex;
		justify-content: space-between;
		gap: 8px;
	}
</style>
