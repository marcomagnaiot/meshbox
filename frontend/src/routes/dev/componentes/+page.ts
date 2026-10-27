import { error } from '@sveltejs/kit';

// Catálogo de componentes (16.4): solo en desarrollo.
export function load() {
	if (!import.meta.env.DEV) error(404, 'Not found');
	return {};
}
