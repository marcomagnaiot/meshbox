<!--
  Sitio y mapa (18.2): nombre, descripción, logo (PNG o WebP), color de acento, idioma, capa por
  defecto, satélite, centro y límites, capas de datos, umbrales de estado, aviso de privacidad
  (Markdown) y extracto del mapa base.
-->
<script lang="ts">
	import ImageUp from '@lucide/svelte/icons/image-up';
	import Trash2 from '@lucide/svelte/icons/trash-2';
	import { onMount } from 'svelte';
	import * as adminApi from '$lib/admin/api';
	import { problemFields, problemText } from '$lib/admin/errors';
	import type { SiteSettings } from '$lib/admin/types';
	import { m } from '$lib/paraglide/messages';
	import { site } from '$lib/stores/site.svelte';
	import { toasts } from '$lib/stores/ui.svelte';
	import Button from '$lib/components/ui/Button.svelte';
	import Skeleton from '$lib/components/ui/Skeleton.svelte';
	import Toggle from '$lib/components/ui/Toggle.svelte';
	import ConfirmAction from '$lib/components/admin/ConfirmAction.svelte';
	import MapPicker from '$lib/components/admin/MapPicker.svelte';
	import CoordFields from '$lib/components/admin/CoordFields.svelte';
	import NumberField from '$lib/components/admin/NumberField.svelte';
	import PageHeader from '$lib/components/admin/PageHeader.svelte';
	import Panel from '$lib/components/admin/Panel.svelte';
	import ProblemNote from '$lib/components/admin/ProblemNote.svelte';
	import SelectField from '$lib/components/admin/SelectField.svelte';
	import TextArea from '$lib/components/admin/TextArea.svelte';
	import TextField from '$lib/components/admin/TextField.svelte';
	import TilesPanel from '$lib/components/admin/site/TilesPanel.svelte';

	const LOGO_MAX = 512 * 1024;
	let form = $state<SiteSettings | null>(null);
	let slug = $state('');
	let timezone = $state('');
	let loadError = $state<unknown>(null);
	let saving = $state(false);
	let errors = $state<Record<string, string>>({});
	let formError = $state<string | null>(null);
	let logoBusy = $state(false);
	let logoVersion = $state(0);
	let logoDeleteOpen = $state(false);
	let fileInput: HTMLInputElement | null = $state(null);
	// Umbrales en minutos (la API los guarda en segundos).
	let activeMin = $state<number | null>(60);
	let recentMin = $state<number | null>(120);
	let lateMin = $state<number | null>(1440);
	let center = $state<number[]>([0, 0]);
	let bounds = $state<number[] | null>(null);
	let zoom = $state<number | null>(11);

	async function load(): Promise<void> {
		try {
			const d = await adminApi.site.get();
			form = d.site;
			slug = d.slug;
			timezone = d.timezone;
			activeMin = Math.round(d.site.status_thresholds.active_s / 60);
			recentMin = Math.round(d.site.status_thresholds.recent_s / 60);
			lateMin = Math.round(d.site.status_thresholds.late_s / 60);
			center = [...d.site.center];
			bounds = d.site.bounds ? [...d.site.bounds] : null;
			zoom = d.site.zoom;
			loadError = null;
		} catch (err) {
			loadError = err;
		}
	}

	onMount(() => {
		void load();
	});

	function validate(): boolean {
		const e: Record<string, string> = {};
		if (!form) return false;
		if (!form.name.trim()) e.name = m.adm_required();
		if (!/^#[0-9a-fA-F]{6}$/.test(form.accent)) e.accent = m.adm_site_accent_invalid();
		const [lat, lon] = center;
		if (!(Math.abs(lat) <= 90 && Math.abs(lon) <= 180)) e.center = m.adm_field_invalid();
		if (zoom === null || zoom < 1 || zoom > 18) e.zoom = m.adm_field_invalid();
		if (
			activeMin === null ||
			recentMin === null ||
			lateMin === null ||
			!(activeMin > 0 && recentMin >= activeMin && lateMin >= recentMin)
		)
			e.status_thresholds = m.adm_site_thresholds_invalid();
		errors = e;
		return Object.keys(e).length === 0;
	}

	async function save(ev: Event): Promise<void> {
		ev.preventDefault();
		if (!form || !validate()) {
			formError = m.adm_fix_fields();
			return;
		}
		saving = true;
		formError = null;
		const { logo: _logo, ...rest } = form;
		try {
			await adminApi.site.put({
				...rest,
				name: form.name.trim(),
				center: center.map(Number),
				zoom: zoom ?? 11,
				bounds,
				status_thresholds: {
					active_s: Math.round((activeMin ?? 60) * 60),
					recent_s: Math.round((recentMin ?? 120) * 60),
					late_s: Math.round((lateMin ?? 1440) * 60)
				}
			});
			toasts.show(m.adm_saved(), { kind: 'success' });
			await site.load(true);
		} catch (err) {
			errors = problemFields(err);
			formError = problemText(err);
		} finally {
			saving = false;
		}
	}

	async function uploadLogo(file: File): Promise<void> {
		if (file.size > LOGO_MAX) {
			toasts.show(m.adm_logo_too_big(), { kind: 'error' });
			return;
		}
		if (!['image/png', 'image/webp'].includes(file.type)) {
			toasts.show(m.adm_logo_format(), { kind: 'error' });
			return;
		}
		logoBusy = true;
		try {
			const out = await adminApi.site.uploadLogo(file);
			if (form) form.logo = out.logo;
			logoVersion++;
			toasts.show(m.adm_logo_saved(), { kind: 'success' });
			await site.load(true);
		} catch (err) {
			toasts.show(problemText(err), { kind: 'error' });
		} finally {
			logoBusy = false;
			if (fileInput) fileInput.value = '';
		}
	}
</script>

<PageHeader slug="sitio" />

{#if loadError && !form}
	<ProblemNote error={loadError} onretry={load} />
{:else if !form}
	<Skeleton lines={8} label={m.loading()} />
{:else}
	<div class="adm-stack">
		<form id="site-form" class="adm-stack" onsubmit={save} novalidate>
			<Panel title={m.adm_site_identity()}>
				<div class="adm-stack">
					<div class="adm-grid">
						<TextField
							label={m.adm_name()}
							bind:value={form.name}
							required
							maxlength={60}
							error={errors.name}
						/>
						<SelectField
							label={m.adm_site_language()}
							bind:value={form.default_language}
							options={[
								{ value: 'es', label: 'Español' },
								{ value: 'en', label: 'English' }
							]}
						/>
					</div>
					<TextArea
						label={m.adm_description()}
						bind:value={form.description}
						maxlength={300}
						rows={2}
						error={errors.description}
					/>
					<div class="accent">
						<TextField
							label={m.adm_site_accent()}
							hint={m.adm_site_accent_hint()}
							bind:value={form.accent}
							mono
							maxlength={7}
							error={errors.accent}
						/>
						<input
							type="color"
							class="swatch"
							aria-label={m.adm_site_accent_pick()}
							bind:value={form.accent}
						/>
					</div>
					<div class="logo">
						<div class="logo-preview">
							{#if form.logo}
								<img
									src="/api/v1/site/logo?v={form.logo}-{logoVersion}"
									alt={m.adm_logo_current()}
								/>
							{:else}
								<img src="/favicon.svg" alt={m.adm_logo_default()} />
							{/if}
						</div>
						<div class="adm-stack">
							<p class="adm-muted">{m.adm_logo_hint()}</p>
							<input
								bind:this={fileInput}
								class="sr-only"
								id="logo-file"
								type="file"
								accept="image/png,image/webp"
								onchange={(e) => {
									const f = e.currentTarget.files?.[0];
									if (f) void uploadLogo(f);
								}}
							/>
							<div class="adm-row">
								<Button
									size="sm"
									icon={ImageUp}
									loading={logoBusy}
									onclick={() => fileInput?.click()}>{m.adm_logo_upload()}</Button
								>
								{#if form.logo}
									<Button
										size="sm"
										variant="ghost"
										icon={Trash2}
										onclick={() => (logoDeleteOpen = true)}>{m.adm_logo_delete()}</Button
									>
								{/if}
							</div>
						</div>
					</div>
					<p class="adm-muted">
						{m.adm_site_slug({ slug })} · {m.adm_site_timezone({ tz: timezone })}
						<a class="adm-link" href="/admin/red">{m.admin_section_network()}</a>
					</p>
				</div>
			</Panel>

			<Panel title={m.adm_site_map()} description={m.adm_site_map_desc()}>
				<div class="adm-stack">
					<MapPicker bind:center bind:zoom bind:bounds label={m.adm_site_map()} />
					<div class="adm-grid">
						<CoordFields
							latLabel={m.adm_site_lat()}
							lonLabel={m.adm_site_lon()}
							bind:lat={() => center[0], (v) => (center = [v ?? 0, center[1]])}
							bind:lon={() => center[1], (v) => (center = [center[0], v ?? 0])}
							error={errors.center}
						/>
						<NumberField
							label={m.adm_site_zoom()}
							bind:value={zoom}
							min={1}
							max={18}
							step="any"
							error={errors.zoom}
						/>
						<TextField
							label={m.adm_site_bounds()}
							value={bounds ? bounds.join(', ') : ''}
							readonly
							mono
							hint={m.adm_site_bounds_hint()}
							error={errors.bounds}
						/>
					</div>
					<div class="adm-grid">
						<SelectField
							label={m.adm_site_default_layer()}
							bind:value={form.default_layer}
							options={[
								{ value: 'dark', label: m.map_base_dark() },
								{ value: 'light', label: m.map_base_light() },
								{ value: 'satellite', label: m.map_base_satellite() }
							]}
						/>
						<Toggle
							label={m.adm_site_satellite()}
							hint={m.adm_site_satellite_hint()}
							bind:checked={form.satellite_enabled}
						/>
					</div>
					<div class="adm-grid">
						<Toggle label={m.map_layer_links()} bind:checked={form.links_layer} />
						<Toggle label={m.map_layer_activity()} bind:checked={form.activity_layer} />
						<Toggle label={m.map_layer_waypoints()} bind:checked={form.waypoints_layer} />
						<Toggle label={m.adm_site_show_inactive()} bind:checked={form.show_inactive} />
					</div>
				</div>
			</Panel>

			<Panel title={m.adm_site_thresholds()} description={m.adm_site_thresholds_desc()}>
				<div class="adm-grid">
					<NumberField
						label={m.status_active()}
						bind:value={activeMin}
						min={1}
						step={1}
						unit="min"
					/>
					<NumberField
						label={m.status_recent()}
						bind:value={recentMin}
						min={1}
						step={1}
						unit="min"
					/>
					<NumberField label={m.status_late()} bind:value={lateMin} min={1} step={1} unit="min" />
				</div>
				{#if errors.status_thresholds}<p class="adm-note danger">{errors.status_thresholds}</p>{/if}
			</Panel>

			<Panel title={m.adm_site_notice()} description={m.adm_site_notice_desc()}>
				<TextArea
					label={m.adm_site_notice_md()}
					bind:value={form.notice_md}
					maxlength={20000}
					rows={12}
					mono
					error={errors.notice_md}
				/>
			</Panel>

			{#if formError}<p class="adm-note danger" role="alert">{formError}</p>{/if}
			<div class="adm-row end sticky">
				<Button type="submit" variant="primary" loading={saving}>{m.adm_save()}</Button>
			</div>
		</form>

		<TilesPanel siteBounds={form.bounds} />
	</div>
{/if}

<ConfirmAction
	bind:open={logoDeleteOpen}
	title={m.adm_logo_delete_title()}
	description={m.adm_logo_delete_desc()}
	confirmLabel={m.adm_delete()}
	action={() => adminApi.site.deleteLogo()}
	onsuccess={() => {
		if (form) form.logo = null;
		void site.load(true);
	}}
/>

<style>
	.accent {
		display: grid;
		grid-template-columns: minmax(0, 260px) 52px;
		align-items: start;
		gap: 10px;
	}

	.swatch {
		margin-top: 26px;
		width: 52px;
		height: 44px;
		padding: 2px;
		border: 1px solid var(--line-strong);
		border-radius: var(--r-sm);
		background: var(--surface-2);
	}

	.logo {
		display: flex;
		align-items: center;
		gap: 16px;
	}

	.logo-preview {
		display: grid;
		place-items: center;
		width: 72px;
		height: 72px;
		border-radius: var(--r-md);
		background: var(--fill-1);
		flex: none;
	}

	.logo-preview img {
		max-width: 56px;
		max-height: 56px;
	}

	.sticky {
		position: sticky;
		bottom: 0;
		padding: 12px 0;
		background: linear-gradient(transparent, var(--bg) 40%);
	}
</style>
