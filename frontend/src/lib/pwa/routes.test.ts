import { readdirSync } from 'node:fs';
import { join, relative, resolve } from 'node:path';
import { describe, expect, it } from 'vitest';
import { isAppRoute } from './routes';

// Vitest corre desde la carpeta del frontend (con jsdom, import.meta.url no es un archivo).
const PUBLIC = resolve('src/routes/(public)');

function pages(dir: string): string[] {
	return readdirSync(dir, { withFileTypes: true }).flatMap((e) =>
		e.isDirectory() ? pages(join(dir, e.name)) : e.name === '+page.svelte' ? [dir] : []
	);
}

describe('rutas que el service worker responde con la aplicación', () => {
	it('incluyen cada página pública', () => {
		const found = pages(PUBLIC);
		expect(found.length).toBeGreaterThan(1);
		for (const dir of found) {
			const route = '/' + relative(PUBLIC, dir).split(/[\\/]/).filter(Boolean).join('/');
			expect(isAppRoute(route.replace(/\[[^\]]+\]/g, 'x')), route).toBe(true);
		}
	});

	it('dejan a la red las páginas propias, los archivos y el panel', () => {
		expect(isAppRoute('/?lat=-40.8')).toBe(true);
		expect(isAppRoute('/n/!826eb03a')).toBe(true);
		expect(isAppRoute('/informe/')).toBe(false);
		expect(isAppRoute('/informe/boletin.pdf')).toBe(false);
		expect(isAppRoute('/nodos-viejos')).toBe(false);
		expect(isAppRoute('/admin')).toBe(false);
		expect(isAppRoute('/setup')).toBe(false);
	});
});
