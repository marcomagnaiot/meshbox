import adapter from '@sveltejs/adapter-static';
import { vitePreprocess } from '@sveltejs/vite-plugin-svelte';

/** @type {import('@sveltejs/kit').Config} */
const config = {
	preprocess: vitePreprocess(),
	kit: {
		// SPA: el backend devuelve index.html para toda ruta que no sea /api, /tiles ni un archivo (12.1).
		adapter: adapter({
			pages: 'build',
			assets: 'build',
			fallback: 'index.html',
			// .br y .gz junto a cada archivo: el backend los sirve sin comprimir en la Pi.
			precompress: true,
			strict: true
		}),
		// Rutas absolutas a /_app: la página de reserva se sirve desde cualquier ruta (/n/!id, /chat).
		paths: { relative: false },
		// El service worker lo registra vite-pwa (aviso de nueva versión con botón "Actualizar").
		serviceWorker: { register: false },
		version: { pollInterval: 0 }
	}
};

export default config;
