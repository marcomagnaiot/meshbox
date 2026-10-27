<!--
  Paso 4: nombre, descripción y ubicación del sitio (centro y límites en el mapa). El
  identificador corto arma la raíz del tópico MQTT (msh/AR/<identificador>).
-->
<script lang="ts">
	import { onMount } from 'svelte';
	import * as adminApi from '$lib/admin/api';
	import { problemFields, problemText } from '$lib/admin/errors';
	import { m } from '$lib/paraglide/messages';
	import type { Wizard } from '$lib/setup/wizard.svelte';
	import { site } from '$lib/stores/site.svelte';
	import MapPicker from '$lib/components/admin/MapPicker.svelte';
	import CoordFields from '$lib/components/admin/CoordFields.svelte';
	import NumberField from '$lib/components/admin/NumberField.svelte';
	import TextArea from '$lib/components/admin/TextArea.svelte';
	import TextField from '$lib/components/admin/TextField.svelte';
	import StepFrame from './StepFrame.svelte';

	interface Props {
		wizard: Wizard;
	}

	let { wizard }: Props = $props();
	const SLUG_RE = /^[a-z0-9-]{2,32}$/;
	let name = $state('');
	let description = $state('');
	let center = $state<number[]>([-34.6, -58.4]);
	let zoom = $state<number | null>(11);
	let bounds = $state<number[] | null>(null);
	let slug = $state('');
	let busy = $state(false);
	let error = $state<string | null>(null);
	let errors = $state<Record<string, string>>({});

	onMount(async () => {
		try {
			const d = await adminApi.site.get();
			name = d.site.name;
			description = d.site.description ?? '';
			center = [...d.site.center];
			zoom = d.site.zoom;
			bounds = d.site.bounds ? [...d.site.bounds] : null;
			slug = d.slug;
		} catch {
			// sin sesión todavía o sin datos: se usan los del sitio público
			name = site.data.name;
		}
	});

	async function submit(): Promise<void> {
		errors = {
			...(name.trim() ? {} : { name: m.adm_required() }),
			...(!slug.trim() || SLUG_RE.test(slug.trim()) ? {} : { slug: m.setup_site_slug_invalid() })
		};
		if (Object.keys(errors).length) return;
		busy = true;
		error = null;
		try {
			await wizard.post('site', {
				name: name.trim(),
				description: description.trim(),
				center: center.map(Number),
				zoom: zoom ?? 11,
				bounds,
				slug: slug.trim() || undefined
			});
			void site.load(true);
			wizard.complete('site');
		} catch (err) {
			errors = problemFields(err);
			error = problemText(err);
		} finally {
			busy = false;
		}
	}
</script>

<StepFrame
	title={m.setup_site_title()}
	description={m.setup_site_desc()}
	onsubmit={submit}
	onback={() => wizard.back()}
	{busy}
	{error}
>
	<div class="adm-grid two">
		<TextField label={m.adm_name()} bind:value={name} required maxlength={60} error={errors.name} />
		<TextField
			label={m.setup_site_slug()}
			hint={m.setup_site_slug_hint({ slug: slug || 'mi-red' })}
			bind:value={slug}
			maxlength={32}
			mono
			autocapitalize="none"
			spellcheck={false}
			error={errors.slug}
		/>
	</div>
	<TextArea
		label={m.adm_description()}
		bind:value={description}
		maxlength={300}
		rows={2}
		error={errors.description}
	/>
	<MapPicker bind:center bind:zoom bind:bounds label={m.adm_site_map()} height="340px" />
	<div class="adm-grid">
		<CoordFields
			latLabel={m.adm_site_lat()}
			lonLabel={m.adm_site_lon()}
			bind:lat={() => center[0], (v) => (center = [v ?? 0, center[1]])}
			bind:lon={() => center[1], (v) => (center = [center[0], v ?? 0])}
		/>
		<NumberField label={m.adm_site_zoom()} min={1} max={18} step={0.5} bind:value={zoom} />
	</div>
	<p class="adm-muted">{m.setup_site_map_hint()}</p>
</StepFrame>
