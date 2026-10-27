// Preferencias del visitante (apariencia, idioma, capas) en localStorage: el sitio público no
// usa cookies (sección 30). El script en línea de app.html aplica tema y modo sólido antes de
// pintar con la misma clave.
import type { BaseLayer } from '$lib/api/types';

export type Theme = 'dark' | 'light' | 'system';
export type LocalePref = 'es' | 'en';

export interface DataLayers {
	links: boolean;
	activity: boolean;
	waypoints: boolean;
	uncertainty: boolean;
}

interface Stored {
	theme?: Theme;
	solid?: boolean;
	locale?: LocalePref;
	base?: BaseLayer;
	layers?: Partial<DataLayers>;
	fpsSuggested?: boolean;
}

export const PREFS_KEY = 'meshbox.prefs';

const DEFAULT_LAYERS: DataLayers = {
	links: true,
	activity: true,
	waypoints: true,
	uncertainty: true
};

function read(): Stored {
	try {
		const raw = globalThis.localStorage?.getItem(PREFS_KEY);
		return raw ? (JSON.parse(raw) as Stored) : {};
	} catch {
		return {};
	}
}

class Prefs {
	theme = $state<Theme>('dark');
	solid = $state(false);
	locale = $state<LocalePref | null>(null);
	base = $state<BaseLayer | null>(null);
	layers = $state<DataLayers>({ ...DEFAULT_LAYERS });
	fpsSuggested = $state(false);
	/** Tema efectivo (resuelve "según el sistema"). */
	systemLight = $state(false);

	constructor() {
		const s = read();
		if (s.theme === 'dark' || s.theme === 'light' || s.theme === 'system') this.theme = s.theme;
		this.solid = Boolean(s.solid);
		if (s.locale === 'es' || s.locale === 'en') this.locale = s.locale;
		if (s.base === 'dark' || s.base === 'light' || s.base === 'satellite') this.base = s.base;
		this.layers = { ...DEFAULT_LAYERS, ...(s.layers ?? {}) };
		this.fpsSuggested = Boolean(s.fpsSuggested);
		if (typeof matchMedia === 'function') {
			const mq = matchMedia('(prefers-color-scheme: light)');
			this.systemLight = mq.matches;
			mq.addEventListener?.('change', (e) => {
				this.systemLight = e.matches;
				this.apply();
			});
		}
	}

	get resolvedTheme(): 'dark' | 'light' {
		if (this.theme === 'system') return this.systemLight ? 'light' : 'dark';
		return this.theme;
	}

	save(): void {
		const data: Stored = {
			theme: this.theme,
			solid: this.solid,
			locale: this.locale ?? undefined,
			base: this.base ?? undefined,
			layers: this.layers,
			fpsSuggested: this.fpsSuggested
		};
		try {
			globalThis.localStorage?.setItem(PREFS_KEY, JSON.stringify(data));
		} catch {
			// modo privado o almacenamiento bloqueado: la preferencia vale solo en esta sesión
		}
	}

	/** Aplica tema y modo sólido al documento. */
	apply(): void {
		if (typeof document === 'undefined') return;
		const root = document.documentElement;
		const theme = this.resolvedTheme;
		root.setAttribute('data-theme', theme);
		if (this.solid) root.setAttribute('data-solid', '');
		else root.removeAttribute('data-solid');
		const meta = document.querySelector('meta[name="theme-color"]');
		meta?.setAttribute('content', theme === 'light' ? '#f5f7fa' : '#0f141b');
	}

	setTheme(theme: Theme): void {
		this.theme = theme;
		this.apply();
		this.save();
	}

	setSolid(solid: boolean): void {
		this.solid = solid;
		this.apply();
		this.save();
	}

	setBase(base: BaseLayer): void {
		this.base = base;
		this.save();
	}

	setLayer(name: keyof DataLayers, on: boolean): void {
		this.layers = { ...this.layers, [name]: on };
		this.save();
	}

	markFpsSuggested(): void {
		this.fpsSuggested = true;
		this.save();
	}
}

export const prefs = new Prefs();
