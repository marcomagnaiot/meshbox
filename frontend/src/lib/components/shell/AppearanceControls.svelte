<!-- Apariencia: tema, modo sólido e idioma (16.4 "menú de apariencia"). -->
<script lang="ts">
	import { i18n } from '$lib/i18n/locale.svelte';
	import { m } from '$lib/paraglide/messages';
	import type { Locale } from '$lib/paraglide/runtime';
	import { prefs, type Theme } from '$lib/stores/prefs.svelte';
	import Segmented from '$lib/components/ui/Segmented.svelte';
	import Toggle from '$lib/components/ui/Toggle.svelte';

	const themes = $derived([
		{ value: 'dark' as Theme, label: m.theme_dark() },
		{ value: 'light' as Theme, label: m.theme_light() },
		{ value: 'system' as Theme, label: m.theme_system() }
	]);
	const languages: { value: Locale; label: string }[] = [
		{ value: 'es', label: 'Español' },
		{ value: 'en', label: 'English' }
	];
</script>

<div class="appearance">
	<p class="menu-heading">{m.appearance_theme()}</p>
	<Segmented
		label={m.appearance_theme()}
		options={themes}
		value={prefs.theme}
		size="sm"
		onchange={(v) => prefs.setTheme(v)}
	/>
	<div class="solid">
		<Toggle
			label={m.appearance_solid()}
			hint={m.appearance_solid_hint()}
			checked={prefs.solid}
			onchange={(v) => prefs.setSolid(v)}
		/>
	</div>
	<p class="menu-heading">{m.appearance_language()}</p>
	<Segmented
		label={m.appearance_language()}
		options={languages}
		value={i18n.locale}
		size="sm"
		onchange={(v) => i18n.set(v)}
	/>
</div>

<style>
	.appearance {
		display: flex;
		flex-direction: column;
		gap: 4px;
	}

	.solid {
		padding: 4px 8px 0;
	}
</style>
