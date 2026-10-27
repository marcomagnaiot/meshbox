// Vista pública activa según la ruta: decide qué va en cada panel (16.3).

export type PublicView =
	'home' | 'nodes' | 'node' | 'chat' | 'alerts' | 'stats' | 'about' | 'other';

export function viewFor(routeId: string | null | undefined): PublicView {
	switch (routeId) {
		case '/(public)':
			return 'home';
		case '/(public)/nodos':
			return 'nodes';
		case '/(public)/n/[id]':
			return 'node';
		case '/(public)/chat':
			return 'chat';
		case '/(public)/alertas':
			return 'alerts';
		case '/(public)/estadisticas':
			return 'stats';
		case '/(public)/acerca':
			return 'about';
		default:
			return 'other';
	}
}

/** Anclaje del panel inferior al entrar a cada vista en el celular. */
export function sheetAnchorFor(view: PublicView): 'peek' | 'half' | 'full' {
	if (view === 'home') return 'peek';
	if (view === 'node') return 'half';
	return 'full';
}
