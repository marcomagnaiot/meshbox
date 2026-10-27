// Panel de administración (18) contra el backend real: cada sección carga sin errores de
// consola ni de CSP, alta y baja de un usuario y de una regla de alerta, la sección de otro
// rol o deshabilitada se explica, el asistente /setup con usuarios creados y axe en las
// pantallas principales. Una sola sesión para
// todo el archivo (el inicio de sesión admite 5 intentos por minuto); solo en Chromium
// (playwright.config.ts lo excluye de los demás proyectos).
import AxeBuilder from '@axe-core/playwright';
import { mkdirSync } from 'node:fs';
import { join } from 'node:path';
import { E2E_PASSWORD, E2E_USER, FRONTEND } from './env';
import type { Page } from '@playwright/test';
import { cspViolations, expect, test } from './fixtures';

const STATE = join(FRONTEND, 'e2e', '.data', 'admin-state.json');

const SECTIONS: { path: string; title: string }[] = [
	{ path: '/admin', title: 'Panel' },
	{ path: '/admin/radio', title: 'Radio' },
	{ path: '/admin/mqtt', title: 'Broker MQTT' },
	{ path: '/admin/canales', title: 'Canales' },
	{ path: '/admin/paquetes', title: 'Paquetes' },
	{ path: '/admin/nodos', title: 'Nodos' },
	{ path: '/admin/mensajes', title: 'Mensajes' },
	{ path: '/admin/alertas', title: 'Alertas' },
	{ path: '/admin/sitio', title: 'Sitio y mapa' },
	{ path: '/admin/privacidad', title: 'Privacidad y retención' },
	{ path: '/admin/cloudflare', title: 'Cloudflare' },
	{ path: '/admin/red', title: 'Red y sistema' },
	{ path: '/admin/plugins', title: 'Plugins' },
	{ path: '/admin/usuarios', title: 'Usuarios' },
	{ path: '/admin/respaldo', title: 'Respaldo' },
	{ path: '/admin/actualizaciones', title: 'Actualizaciones' },
	{ path: '/admin/registros', title: 'Registros' }
];

test.describe.configure({ mode: 'serial' });
test.use({ storageState: STATE });

test.beforeAll(async ({ browser }, info) => {
	mkdirSync(join(FRONTEND, 'e2e', '.data'), { recursive: true });
	// Contexto limpio (test.use aplica storageState también a browser.newContext).
	const context = await browser.newContext({
		baseURL: info.project.use.baseURL,
		storageState: { cookies: [], origins: [] }
	});
	const page = await context.newPage();
	// Si otra prueba agotó los intentos del minuto, el servidor responde 429: se espera y reintenta.
	for (let attempt = 0; attempt < 3; attempt++) {
		await page.goto('/admin/login');
		await page.getByLabel('Usuario').fill(E2E_USER);
		await page.getByLabel('Contraseña').fill(E2E_PASSWORD);
		const response = page.waitForResponse((r) => r.url().endsWith('/api/v1/admin/auth/login'));
		await page.getByRole('button', { name: 'Entrar' }).click();
		const res = await response;
		if (res.ok()) break;
		const wait = Number(res.headers()['retry-after'] ?? '20');
		await page.waitForTimeout(Math.min(wait + 1, 65) * 1000);
	}
	await page.waitForURL((u) => !u.pathname.startsWith('/admin/login'));
	await context.storageState({ path: STATE });
	await context.close();
});

test('cada sección carga sin errores de consola ni violaciones de CSP', async ({
	page,
	consoleErrors
}) => {
	test.setTimeout(180_000);
	for (const { path, title } of SECTIONS) {
		await page.goto(path);
		await expect(page.getByRole('heading', { level: 1, name: title })).toBeVisible();
		// Los esqueletos de carga desaparecen cuando llegan los datos.
		await expect(page.locator('main [aria-busy="true"]')).toHaveCount(0, { timeout: 20_000 });
		expect(consoleErrors, `${path}: ${consoleErrors.join('\n')}`).toEqual([]);
		expect(await cspViolations(page), path).toEqual([]);
	}
});

test('transmisión deshabilitada: la sección lo explica', async ({ page }) => {
	await page.goto('/admin/transmision');
	await expect(page.getByRole('alert')).toContainText('[tx] enabled = true');
	await expect(
		page
			.getByRole('navigation', { name: 'Menú del panel' })
			.getByRole('link', { name: 'Transmisión' })
	).toHaveCount(0);
});

test('alta y baja de un usuario operador', async ({ page }) => {
	const name = `e2e-op-${Date.now() % 1_000_000}`;
	await page.goto('/admin/usuarios');
	await page.getByRole('button', { name: 'Agregar usuario' }).click();
	const dialog = page.getByRole('dialog');
	await dialog.getByRole('textbox', { name: 'Usuario', exact: true }).fill(name);
	await dialog
		.getByRole('textbox', { name: 'Contraseña', exact: true })
		.fill('una-clave-larga-de-prueba-2026');
	await dialog.getByRole('button', { name: 'Guardar' }).click();
	await expect(dialog).toBeHidden();
	const table = page.getByRole('table', { name: 'Usuarios' });
	await expect(table.getByText(name)).toBeVisible();

	await page.getByRole('button', { name: `Borrar ${name}` }).click();
	const confirm = page.getByRole('alertdialog');
	await expect(confirm).toContainText(name);
	await confirm.getByRole('button', { name: 'Borrar' }).click();
	await expect(confirm).toBeHidden();
	await expect(table.getByText(name)).toHaveCount(0);
});

test('alta y baja de una regla de alerta (formulario desde JSON Schema)', async ({ page }) => {
	const name = `Prueba e2e ${Date.now() % 1_000_000}`;
	await page.goto('/admin/alertas');
	await page.getByRole('button', { name: 'Agregar regla' }).click();
	const dialog = page.getByRole('dialog');
	await dialog.getByRole('textbox', { name: 'Nombre', exact: true }).fill(name);
	// El tipo por defecto es "palabra clave" con el patrón SOS ya cargado desde el esquema.
	await expect(dialog.getByText('\\bSOS\\b', { exact: true })).toBeVisible();
	await dialog.getByRole('button', { name: 'Guardar' }).click();
	await expect(dialog).toBeHidden();
	const rule = page.getByRole('region', { name });
	await expect(rule).toBeVisible();

	await rule.getByRole('button', { name: 'Borrar' }).click();
	const confirm = page.getByRole('alertdialog');
	await confirm.getByRole('button', { name: 'Borrar' }).click();
	await expect(rule).toHaveCount(0);
});

test('asistente con usuarios: sin sesión la pide; con sesión retoma el primer paso pendiente', async ({
	page,
	browser,
	baseURL
}) => {
	const anon = await browser.newContext({ baseURL, storageState: { cookies: [], origins: [] } });
	const anonPage = await anon.newPage();
	await anonPage.goto('/setup');
	await expect(anonPage.getByRole('heading', { name: 'Iniciar sesión para seguir' })).toBeVisible();
	await expect(anonPage.getByRole('link', { name: 'Iniciar sesión' })).toHaveAttribute(
		'href',
		'/admin/login?next=/setup'
	);
	await anon.close();

	await page.goto('/setup');
	// El administrador ya existe: no se piden el código ni la cuenta.
	await expect(page.locator('#step-title')).toHaveText('Idioma y zona horaria');
	const steps = page.getByRole('navigation', { name: 'Pasos del asistente' });
	await expect(steps.getByText('Código', { exact: true })).toHaveCount(0);
	await expect(steps.getByText('Verificación')).toBeVisible();
});

async function seriousViolations(page: Page): Promise<unknown[]> {
	const results = await new AxeBuilder({ page })
		.withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'wcag22aa'])
		.analyze();
	return results.violations
		.filter((v) => v.impact === 'serious' || v.impact === 'critical')
		.map((v) => ({
			id: v.id,
			help: v.help,
			nodes: v.nodes.slice(0, 4).map((n) => `${n.target.join(' ')} :: ${n.html.slice(0, 160)}`)
		}));
}

for (const path of ['/admin', '/admin/nodos', '/admin/alertas', '/admin/red', '/admin/registros']) {
	test(`axe sin violaciones serias en ${path}`, async ({ page }) => {
		await page.goto(path);
		await expect(page.getByRole('heading', { level: 1 })).toBeVisible();
		await expect(page.locator('main [aria-busy="true"]')).toHaveCount(0, { timeout: 20_000 });
		const serious = await seriousViolations(page);
		expect(serious, JSON.stringify(serious, null, 2)).toEqual([]);
	});
}

test('axe sin violaciones serias en /setup', async ({ page }) => {
	await page.goto('/setup');
	await expect(page.locator('#step-title')).toBeVisible();
	const serious = await seriousViolations(page);
	expect(serious, JSON.stringify(serious, null, 2)).toEqual([]);
});
