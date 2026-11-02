// Rutas públicas de la aplicación. El service worker les responde con la aplicación en caché, así
// abren sin conexión; cualquier otra navegación va a la red, donde el servidor sirve las páginas
// propias (ADR 0021) o la aplicación. Al sumar una ruta pública hay que agregarla acá: la prueba
// de routes.test.ts recorre src/routes/(public) y falla si falta alguna.
// Workbox compara contra la ruta más la consulta (?...).
export const APP_ROUTES: RegExp[] = [
	/^\/(?:\?.*)?$/,
	/^\/(?:acerca|alertas|chat|estadisticas|nodos|n)(?:[/?].*)?$/
];

export function isAppRoute(pathAndSearch: string): boolean {
	return APP_ROUTES.some((re) => re.test(pathAndSearch));
}
