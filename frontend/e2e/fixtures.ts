// Fixtures comunes: errores de consola, violaciones de CSP y la capa satelital de Esri
// respondida localmente (las pruebas no dependen de internet; la CSP se evalúa igual).
import { test as base, expect, type Page } from '@playwright/test';

// PNG de 1×1 px.
const PNG = Buffer.from(
	'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==',
	'base64'
);

export const test = base.extend<{ consoleErrors: string[] }>({
	consoleErrors: [
		async ({ page }, use) => {
			const errors: string[] = [];
			page.on('console', (msg) => {
				if (msg.type() === 'error') errors.push(msg.text());
			});
			page.on('pageerror', (err) => errors.push(`pageerror: ${err.message}`));
			await page.addInitScript(() => {
				const w = window as unknown as { __csp: string[] };
				w.__csp = [];
				document.addEventListener('securitypolicyviolation', (e) => {
					w.__csp.push(`${e.violatedDirective} ${e.blockedURI}`);
				});
			});
			await page.route('https://server.arcgisonline.com/**', (route) =>
				route.fulfill({ status: 200, contentType: 'image/png', body: PNG })
			);
			await use(errors);
		},
		{ auto: true }
	]
});

export { expect };

export async function cspViolations(page: Page): Promise<string[]> {
	return page.evaluate(() => (window as unknown as { __csp?: string[] }).__csp ?? []);
}

/**
 * Espera a que el mapa (cargado en diferido) tenga nodos dibujados. No pregunta `loaded()`: con
 * la actividad en vivo a 10× la fuente de pulsos cambia 30 veces por segundo y, con la CPU
 * ocupada, casi nunca está "cargada" justo cuando se consulta.
 */
export async function waitForMap(page: Page): Promise<void> {
	await page.waitForFunction(
		() => {
			const m = (
				window as unknown as {
					__meshboxMap?: {
						getSource(id: string): unknown;
						getLayer(id: string): unknown;
						queryRenderedFeatures(o: object): unknown[];
					};
				}
			).__meshboxMap;
			if (!m || !m.getSource('m-nodes')) return false;
			const layers = ['m-nodes-icon', 'm-clusters', 'm-selected-icon'].filter((id) =>
				m.getLayer(id)
			);
			return layers.length > 0 && m.queryRenderedFeatures({ layers }).length > 0;
		},
		undefined,
		{ timeout: 30_000, polling: 250 }
	);
}

/** Indicador "en vivo" (en el celular el texto es solo para lectores de pantalla). */
export async function waitForLive(page: Page): Promise<void> {
	await expect(page.getByRole('status').filter({ hasText: 'En vivo' }).first()).toBeAttached();
}
