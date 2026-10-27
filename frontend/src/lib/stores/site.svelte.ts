// Configuración pública del sitio (`GET /api/v1/site`): nombre, centro, capas, umbrales,
// funciones, aviso, zona horaria. Se pide una vez al arrancar; sin red, el service worker
// devuelve la última copia.
import { publicApi } from '$lib/api/public';
import type { Site } from '$lib/api/types';
import { i18n } from '$lib/i18n/locale.svelte';
import { onColor } from '$lib/utils/color';
import { DEFAULT_THRESHOLDS } from '$lib/utils/status';

export const FALLBACK_SITE: Site = {
	name: 'meshbox',
	description: '',
	logo_url: null,
	accent: '#22b8cf',
	center: [-34.6037, -58.3816],
	zoom: 11,
	bounds: null,
	layers: { dark: false, light: false, satellite: true, default: 'satellite' },
	has_tiles: false,
	thresholds: DEFAULT_THRESHOLDS,
	features: {
		push: false,
		activity: true,
		links: true,
		waypoints: true,
		show_inactive: false,
		tx: false
	},
	notice: [],
	public_channels: [],
	timezone: 'America/Argentina/Buenos_Aires',
	language: 'es',
	languages: ['es', 'en'],
	version: '',
	attributions: [],
	plugin_layers: [],
	server: 'public'
};

class SiteStore {
	data = $state.raw<Site>(FALLBACK_SITE);
	loaded = $state(false);
	error = $state<unknown>(null);
	#promise: Promise<Site> | null = null;

	get timezone(): string {
		return this.data.timezone || Intl.DateTimeFormat().resolvedOptions().timeZone;
	}

	load(force = false): Promise<Site> {
		if (this.#promise && !force) return this.#promise;
		this.#promise = publicApi
			.site()
			.then((site) => {
				this.data = {
					...FALLBACK_SITE,
					...site,
					features: { ...FALLBACK_SITE.features, ...site.features }
				};
				this.loaded = true;
				this.error = null;
				this.applyAccent();
				i18n.useSiteDefault(site.language);
				return this.data;
			})
			.catch((err: unknown) => {
				this.error = err;
				this.#promise = null;
				return this.data;
			});
		return this.#promise;
	}

	/** Color de acento configurado en el panel (hex) → tokens `--accent` y `--on-accent`. */
	applyAccent(): void {
		if (typeof document === 'undefined') return;
		const accent = this.data.accent;
		if (!/^#[0-9a-f]{6}$/i.test(accent)) return;
		const root = document.documentElement;
		root.style.setProperty('--accent', accent);
		root.style.setProperty('--on-accent', onColor(accent));
	}
}

export const site = new SiteStore();
