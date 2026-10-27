/// <reference types="@sveltejs/kit" />
/// <reference no-default-lib="true"/>
/// <reference lib="esnext" />
/// <reference lib="webworker" />
// Service worker (sección 20), estrategia injectManifest de vite-pwa:
// - la aplicación queda en caché para abrir sin red (shell);
// - `/api/v1/site` y `/api/v1/nodes`: red primero, con la última foto como respaldo;
// - teselas `/tiles/v/*`: caché primero, solo respuestas 200 completas, tope aproximado de 50 MB;
// - la API de administración nunca se guarda;
// - notificaciones push con acción "Ver en el mapa".
import { CacheableResponsePlugin } from 'workbox-cacheable-response';
import { ExpirationPlugin } from 'workbox-expiration';
import {
	cleanupOutdatedCaches,
	createHandlerBoundToURL,
	precacheAndRoute
} from 'workbox-precaching';
import { NavigationRoute, registerRoute } from 'workbox-routing';
import { CacheFirst, NetworkFirst, NetworkOnly } from 'workbox-strategies';

declare let self: ServiceWorkerGlobalScope & {
	__WB_MANIFEST: Array<{ url: string; revision: string | null }>;
};

// Tamaño medio de una tesela vectorial z10-14 comprimida (~25 KB): 2000 entradas ≈ 50 MB.
const TILE_MAX_ENTRIES = 2000;

precacheAndRoute(self.__WB_MANIFEST);
cleanupOutdatedCaches();

// Administración: siempre a la red (el servidor público responde 404 por construcción).
registerRoute(({ url }) => url.pathname.startsWith('/api/v1/admin'), new NetworkOnly());
registerRoute(({ url }) => url.pathname.startsWith('/api/v1/setup'), new NetworkOnly());

// Navegación: la aplicación (index.html en caché) para toda ruta pública.
registerRoute(
	new NavigationRoute(createHandlerBoundToURL('/index.html'), {
		denylist: [/^\/api\//, /^\/tiles\//, /^\/admin(\/|$)/, /^\/setup(\/|$)/]
	})
);

// Última foto del sitio y de los nodos para mostrar sin conexión.
registerRoute(
	({ url, request }) =>
		request.method === 'GET' &&
		(url.pathname === '/api/v1/site' ||
			url.pathname === '/api/v1/nodes' ||
			url.pathname === '/tiles/v.json'),
	new NetworkFirst({
		cacheName: 'meshbox-api',
		networkTimeoutSeconds: 6,
		plugins: [new CacheableResponsePlugin({ statuses: [200] })]
	})
);

// Teselas vectoriales: la URL lleva la versión del extracto (?v=), así que no cambian.
registerRoute(
	({ url }) => url.pathname.startsWith('/tiles/v/'),
	new CacheFirst({
		cacheName: 'meshbox-tiles',
		plugins: [
			new CacheableResponsePlugin({ statuses: [200] }),
			new ExpirationPlugin({
				maxEntries: TILE_MAX_ENTRIES,
				maxAgeSeconds: 60 * 86400,
				purgeOnQuotaError: true
			})
		]
	})
);

// Tipografías y sprites del estilo.
registerRoute(
	({ url }) =>
		url.pathname.startsWith('/tiles/fonts/') || url.pathname.startsWith('/tiles/sprites/'),
	new CacheFirst({
		cacheName: 'meshbox-map-assets',
		plugins: [
			new CacheableResponsePlugin({ statuses: [200] }),
			new ExpirationPlugin({ maxEntries: 120, purgeOnQuotaError: true })
		]
	})
);

// Aviso de nueva versión: la página pide activar el service worker nuevo.
self.addEventListener('message', (event) => {
	if (event.data && event.data.type === 'SKIP_WAITING') void self.skipWaiting();
});

interface PushPayload {
	id?: number;
	title?: string;
	body?: string | null;
	node?: string | null;
	severity?: string;
	url?: string;
	data?: PushPayload;
}

const spanish = () => (self.navigator.language || 'es').toLowerCase().startsWith('es');

self.addEventListener('push', (event) => {
	let payload: PushPayload;
	try {
		payload = (event.data?.json() as PushPayload) ?? {};
	} catch {
		payload = { body: event.data?.text() ?? '' };
	}
	// Admite el cuerpo plano de la alerta o envuelto como el webhook ({event, data}).
	const alert = payload.data && typeof payload.data === 'object' ? payload.data : payload;
	const title = alert.title || 'meshbox';
	const url = alert.url || (alert.node ? `/n/${alert.node}` : '/alertas');
	const options: NotificationOptions & { actions?: { action: string; title: string }[] } = {
		body: alert.body ?? '',
		tag: alert.id !== undefined ? `alert-${alert.id}` : undefined,
		icon: '/pwa-192x192.png',
		badge: '/pwa-64x64.png',
		data: { url },
		requireInteraction: alert.severity === 'critical',
		actions: [{ action: 'map', title: spanish() ? 'Ver en el mapa' : 'Show on the map' }]
	};
	event.waitUntil(self.registration.showNotification(title, options));
});

self.addEventListener('notificationclick', (event) => {
	event.notification.close();
	const target = new URL(
		(event.notification.data as { url?: string } | null)?.url ?? '/',
		self.location.origin
	).href;
	event.waitUntil(
		(async () => {
			const windows = await self.clients.matchAll({ type: 'window', includeUncontrolled: true });
			for (const client of windows) {
				if (new URL(client.url).origin === self.location.origin) {
					await client.focus();
					if ('navigate' in client) await (client as WindowClient).navigate(target);
					return;
				}
			}
			await self.clients.openWindow(target);
		})()
	);
});
