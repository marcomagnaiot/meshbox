// Idioma reactivo sin recargar la página: Paraglide resuelve el idioma con `getLocale()` en
// cada llamada a un mensaje; al devolver un `$state`, todo texto `{m.algo()}` se vuelve a
// dibujar cuando cambia. Prioridad: elección del visitante > idioma del sitio > español.
import {
	baseLocale,
	isLocale,
	overwriteGetLocale,
	overwriteSetLocale,
	type Locale
} from '$lib/paraglide/runtime';
import { prefs } from '$lib/stores/prefs.svelte';

let current = $state<Locale>(prefs.locale ?? baseLocale);

function applyDocument(locale: Locale): void {
	if (typeof document !== 'undefined') document.documentElement.lang = locale;
}

overwriteGetLocale(() => current);
overwriteSetLocale((locale) => {
	current = locale;
	prefs.locale = locale;
	prefs.save();
	applyDocument(locale);
});

export const i18n = {
	get locale(): Locale {
		return current;
	},
	/** Elección explícita del visitante (se guarda). */
	set(locale: Locale): void {
		current = locale;
		prefs.locale = locale;
		prefs.save();
		applyDocument(locale);
	},
	/** Idioma por defecto configurado en el panel, si el visitante no eligió otro. */
	useSiteDefault(language: string | null | undefined): void {
		if (prefs.locale || !isLocale(language)) return;
		current = language;
		applyDocument(language);
	}
};

applyDocument(prefs.locale ?? baseLocale);
