/// <reference types="vitest/config" />
import { createHash } from 'node:crypto';
import { createReadStream, existsSync, readdirSync, readFileSync, statSync } from 'node:fs';
import { join, resolve, sep } from 'node:path';
import { paraglideVitePlugin } from '@inlang/paraglide-js';
import { sveltekit } from '@sveltejs/kit/vite';
import tailwindcss from '@tailwindcss/vite';
import { svelteTesting } from '@testing-library/svelte/vite';
import { SvelteKitPWA } from '@vite-pwa/sveltekit';
import { defineConfig, type Plugin, type ProxyOptions } from 'vite';

// Backend de desarrollo (puede cambiarse con MESHBOX_BACKEND, por ejemplo http://127.0.0.1:8000).
const BACKEND = process.env.MESHBOX_BACKEND ?? 'http://127.0.0.1:8100';
const ASSETS_DIR = resolve('static/tiles-assets');
const isTest = Boolean(process.env.VITEST) || Boolean(process.env.MESHBOX_NO_PWA);

/**
 * En `pnpm dev` el backend no tiene los recursos del mapa: se sirven `/tiles/fonts` y
 * `/tiles/sprites` desde `static/tiles-assets` (mismas rutas que en producción).
 */
function mapAssets(): Plugin {
	return {
		name: 'meshbox:map-assets',
		configureServer(server) {
			server.middlewares.use((req, res, next) => {
				const url = decodeURIComponent((req.url ?? '').split('?')[0]);
				const match = /^\/tiles\/(fonts|sprites)\/(.+)$/.exec(url);
				if (!match) return next();
				const [, kind, rest] = match;
				// MapLibre pide "Fuente A,Fuente B": se usa la primera disponible (como el backend).
				const candidates =
					kind === 'fonts'
						? rest
								.split('/')[0]
								.split(',')
								.map((f) => `${f.trim()}/${rest.split('/').slice(1).join('/')}`)
						: [rest];
				for (const rel of candidates) {
					const file = resolve(ASSETS_DIR, kind, rel);
					if (!file.startsWith(ASSETS_DIR + sep)) break;
					try {
						if (!statSync(file).isFile()) continue;
					} catch {
						continue;
					}
					res.setHeader(
						'Content-Type',
						file.endsWith('.pbf')
							? 'application/x-protobuf'
							: file.endsWith('.png')
								? 'image/png'
								: 'application/json'
					);
					createReadStream(file).pipe(res);
					return;
				}
				res.statusCode = 404;
				res.end();
			});
		}
	};
}

/**
 * Íconos de Lucide más livianos: cada ícono importa `../Icon.svelte`, que arma los atributos
 * con varios $derived y dibuja cada trazo con un <svelte:element>; en una página con 40 íconos
 * suma decenas de ms al primer dibujo en un teléfono. Se cambia por `LucideIcon.svelte`, que
 * arma el SVG una vez por ícono. Solo para los íconos del paquete (importados de a uno).
 */
function lightLucide(): Plugin {
	const target = resolve('src/lib/components/ui/LucideIcon.svelte');
	return {
		name: 'meshbox:lucide-liviano',
		enforce: 'pre',
		resolveId(source, importer) {
			if (source !== '../Icon.svelte' || !importer) return null;
			return /@lucide[\\/]svelte[\\/]dist[\\/]icons[\\/]/.test(importer) ? target : null;
		}
	};
}

type PrecacheEntry = { url: string; revision: string | null; size: number };

/**
 * Lista del precache del service worker. Reemplaza la transformación por defecto de
 * @vite-pwa/sveltekit (que no se exporta) haciendo lo mismo para esta configuración (quita el
 * prefijo `client/` y agrega `index.html`, la app de una sola página, con la revisión de
 * `version.json`) y además deja afuera lo que solo usan el panel y el asistente (/admin y
 * /setup): quien visita el sitio público no baja casi medio MB que nunca va a usar. Esas rutas
 * no funcionan sin el backend, así que no pierden nada (sus archivos son inmutables y quedan en
 * la caché HTTP). Se calcula con el manifiesto de Vite: cierre de imports (estáticos y
 * dinámicos) de los nodos del panel menos el de todo lo demás.
 */
function precacheManifest(entries: PrecacheEntry[]) {
	const out = withoutAdminOnly(entries).map((e) => ({
		...e,
		url: e.url.replace(/^client\//, '')
	}));
	const version = resolve('.svelte-kit/output/client/_app/version.json');
	const content = readFileSync(version);
	out.push({
		url: 'index.html',
		revision: createHash('md5').update(content).digest('hex'),
		size: content.length
	});
	return { manifest: out };
}

function withoutAdminOnly(entries: PrecacheEntry[]): PrecacheEntry[] {
	const manifestFile = resolve('.svelte-kit/output/client/.vite/manifest.json');
	const nodesDir = resolve('.svelte-kit/generated/client-optimized/nodes');
	if (!existsSync(manifestFile) || !existsSync(nodesDir)) return entries;
	type Chunk = {
		file: string;
		imports?: string[];
		dynamicImports?: string[];
		css?: string[];
		assets?: string[];
		isEntry?: boolean;
	};
	const manifest = JSON.parse(readFileSync(manifestFile, 'utf8')) as Record<string, Chunk>;
	const keyOf = (node: string) =>
		Object.keys(manifest).find((k) => k.endsWith(`client-optimized/nodes/${node}`));
	const adminRoots: string[] = [];
	const otherRoots = Object.keys(manifest).filter(
		(k) => manifest[k].isEntry && !k.includes('/nodes/')
	);
	for (const node of readdirSync(nodesDir)) {
		const key = keyOf(node);
		if (!key) continue;
		const src = readFileSync(join(nodesDir, node), 'utf8');
		(/src\/routes\/(admin|setup)\//.test(src) ? adminRoots : otherRoots).push(key);
	}
	// app.js importa en diferido todos los nodos (el enrutador): al recorrer lo público no se
	// entra a los nodos del panel.
	const files = (roots: string[], skip: Set<string> = new Set()) => {
		const seen = new Set<string>();
		const out = new Set<string>();
		const stack = [...roots];
		while (stack.length) {
			const k = stack.pop()!;
			if (seen.has(k) || skip.has(k) || !manifest[k]) continue;
			seen.add(k);
			const c = manifest[k];
			out.add(c.file);
			for (const f of [...(c.css ?? []), ...(c.assets ?? [])]) out.add(f);
			stack.push(...(c.imports ?? []), ...(c.dynamicImports ?? []));
		}
		return out;
	};
	const shared = files(otherRoots, new Set(adminRoots));
	const adminOnly = new Set([...files(adminRoots)].filter((f) => !shared.has(f)));
	const norm = (url: string) => url.replace(/^(\.\/)?(client\/)?/, '');
	return entries.filter((e) => !adminOnly.has(norm(e.url)));
}

const proxy: Record<string, ProxyOptions> = {
	'/api': { target: BACKEND },
	'/tiles/v.json': { target: BACKEND },
	'/tiles/v/': { target: BACKEND }
};

export default defineConfig({
	plugins: [
		lightLucide(),
		tailwindcss(),
		paraglideVitePlugin({
			project: './project.inlang',
			outdir: './src/lib/paraglide',
			strategy: ['localStorage', 'baseLocale'],
			emitTsDeclarations: true
		}),
		sveltekit(),
		svelteTesting(),
		mapAssets(),
		!isTest &&
			SvelteKitPWA({
				strategies: 'injectManifest',
				srcDir: 'src',
				filename: 'service-worker.ts',
				registerType: 'prompt',
				injectRegister: false,
				manifestFilename: 'manifest.webmanifest',
				manifest: {
					id: '/',
					name: 'meshbox · Red Meshtastic',
					short_name: 'meshbox',
					description: 'Mapa en vivo, nodos, chat y alertas de la red Meshtastic local',
					lang: 'es',
					dir: 'ltr',
					start_url: '/',
					scope: '/',
					display: 'standalone',
					orientation: 'any',
					background_color: '#0f141b',
					theme_color: '#0f141b',
					categories: ['utilities', 'navigation'],
					icons: [
						{ src: '/pwa-64x64.png', sizes: '64x64', type: 'image/png' },
						{ src: '/pwa-192x192.png', sizes: '192x192', type: 'image/png' },
						{ src: '/pwa-512x512.png', sizes: '512x512', type: 'image/png' },
						{
							src: '/maskable-icon-512x512.png',
							sizes: '512x512',
							type: 'image/png',
							purpose: 'maskable'
						}
					]
				},
				injectManifest: {
					// La app (JS, CSS, fuentes, íconos); nunca los recursos del mapa (van en caché aparte).
					// De Inter solo latín y latín extendido: los demás alfabetos se piden si aparecen
					// en un nombre (unicode-range) y sin conexión caen en la fuente del sistema.
					globPatterns: ['client/**/*.{js,css,woff2,svg,png,ico,webmanifest}'],
					globIgnores: [
						'client/tiles-assets/**',
						'client/**/inter-cyrillic*',
						'client/**/inter-greek*',
						'client/**/inter-vietnamese*',
						'server/**'
					],
					manifestTransforms: [precacheManifest]
				},
				kit: {
					adapterFallback: 'index.html',
					spa: true,
					includeVersionFile: true
				},
				devOptions: { enabled: false }
			})
	],
	server: {
		port: 5173,
		strictPort: false,
		proxy
	},
	preview: {
		proxy
	},
	build: {
		target: 'es2022',
		sourcemap: false,
		chunkSizeWarningLimit: 1200
	},
	// El worker de MapLibre 6 es un módulo ES (lo crea con `type: 'module'`).
	worker: {
		format: 'es'
	},
	test: {
		include: ['src/**/*.{test,spec}.{js,ts}'],
		environment: 'jsdom',
		setupFiles: ['./src/test-setup.ts'],
		restoreMocks: true,
		// jsdom pesa: pocos procesos a la vez evitan esperas al arrancar en equipos cargados.
		maxWorkers: 4
	}
});
