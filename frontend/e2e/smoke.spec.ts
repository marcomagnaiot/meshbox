// Pruebas de humo del sitio público y del panel (27), servidas por el backend real.
import { cspViolations, expect, test, waitForLive, waitForMap } from './fixtures';
import { E2E_PASSWORD, E2E_USER } from './env';

test.describe('sitio público', () => {
	test('el mapa carga sin errores de consola ni violaciones de CSP', async ({
		page,
		consoleErrors
	}) => {
		await page.goto('/');
		await expect(page.locator('.maplibregl-canvas')).toBeVisible();
		await waitForLive(page);
		await waitForMap(page);
		expect(consoleErrors).toEqual([]);
		expect(await cspViolations(page)).toEqual([]);
	});

	test('buscar en la lista y abrir la ficha de un nodo', async ({ page }) => {
		await page.goto('/nodos');
		await expect(page.locator('a[data-node]').first()).toBeVisible();
		// La lista se reordena en vivo: se filtra por nombre (sin acentos) antes de elegir.
		await page.getByRole('searchbox', { name: 'Buscar nodos' }).last().fill('torre del agua');
		const row = page.locator('a[data-node="!0b03cbf1"]');
		await expect(row).toBeVisible();
		await expect(page.locator('a[data-node]')).toHaveCount(1);
		await row.click();
		await expect(page).toHaveURL('/n/!0b03cbf1');
		await expect(page.getByRole('heading', { level: 1, name: 'Torre del Agua' })).toBeVisible();
		await expect(page.getByText('Datos técnicos')).toBeAttached();
	});

	test('el enlace directo /n/!id abre la ficha y centra el mapa en el nodo', async ({
		page,
		consoleErrors
	}) => {
		await page.goto('/n/!0b03cbf0');
		await expect(page.getByRole('heading', { level: 1, name: 'Techo Magna' })).toBeVisible();
		await waitForMap(page);
		await page.waitForFunction(
			() => {
				const m = (
					window as unknown as {
						__meshboxMap?: {
							isMoving(): boolean;
							getCenter(): { lat: number; lng: number };
							getZoom(): number;
						};
					}
				).__meshboxMap;
				if (!m || m.isMoving()) return false;
				const c = m.getCenter();
				return (
					Math.abs(c.lat - -40.8131) < 0.02 &&
					Math.abs(c.lng - -62.9964) < 0.02 &&
					m.getZoom() >= 12.9
				);
			},
			undefined,
			{ timeout: 20_000 }
		);
		expect(consoleErrors).toEqual([]);
	});

	test('el chat lista mensajes con separadores de día', async ({ page }) => {
		await page.goto('/chat');
		await expect(
			page.getByRole('heading', { level: 1, name: 'Chat del canal público' })
		).toBeVisible();
		await expect(page.locator('.msg').first()).toBeVisible();
		expect(await page.locator('.msg').count()).toBeGreaterThan(5);
		await expect(page.locator('.day').first()).toBeAttached();
	});

	test('aviso SOS con aria-live assertive', async ({ page }) => {
		const now = Date.now() / 1000;
		await page.route('**/api/v1/alerts?**', (route) =>
			route.fulfill({
				json: {
					alerts: [
						{
							id: 77,
							state: 'firing',
							severity: 'critical',
							kind: 'keyword',
							node: '!0b03cbf0',
							title: 'SOS desde Techo Magna',
							body: 'SOS necesito ayuda en la ruta 3',
							ts: now - 30
						}
					],
					next: null
				}
			})
		);
		await page.goto('/');
		const banner = page.getByTestId('alert-banner');
		await expect(banner).toBeVisible();
		await expect(banner).toHaveAttribute('role', 'alert');
		await expect(page.locator('.sos-region')).toHaveAttribute('aria-live', 'assertive');
		await expect(banner).toContainText('SOS desde Techo Magna');
		await expect(banner.getByRole('link', { name: 'Ver en el mapa' })).toHaveAttribute(
			'href',
			'/n/!0b03cbf0'
		);
		await banner.getByRole('button', { name: 'Ocultar el aviso' }).click();
		await expect(banner).toBeHidden();
	});

	test('manifiesto PWA válido, íconos y service worker', async ({ page, request }) => {
		const res = await request.get('/manifest.webmanifest');
		expect(res.ok()).toBeTruthy();
		const manifest = await res.json();
		expect(manifest.name).toBeTruthy();
		expect(manifest.short_name).toBeTruthy();
		expect(manifest.display).toBe('standalone');
		expect(manifest.start_url).toBe('/');
		const icons = manifest.icons as {
			src: string;
			sizes: string;
			purpose?: string;
			type: string;
		}[];
		expect(icons.some((i) => i.sizes === '192x192')).toBe(true);
		expect(icons.some((i) => i.sizes === '512x512' && !i.purpose)).toBe(true);
		expect(icons.some((i) => i.purpose === 'maskable')).toBe(true);
		for (const icon of icons) {
			const img = await request.get(icon.src);
			expect(img.ok(), icon.src).toBeTruthy();
			expect(img.headers()['content-type']).toContain('image/png');
		}
		const sw = await request.get('/service-worker.js');
		expect(sw.ok()).toBeTruthy();
		expect(sw.headers()['content-type']).toContain('javascript');
		await page.goto('/');
		await expect(page.locator('link[rel="manifest"]')).toHaveAttribute(
			'href',
			'/manifest.webmanifest'
		);
		const registered = await page.evaluate(async () => {
			if (!('serviceWorker' in navigator)) return 'sin soporte';
			const reg = await navigator.serviceWorker.ready;
			return reg.active ? 'activo' : 'registrado';
		});
		expect(['activo', 'registrado']).toContain(registered);
	});
});

test.describe('panel', () => {
	test('un inicio de sesión fallido muestra el error', async ({ page }) => {
		await page.goto('/admin/login');
		await page.getByLabel('Usuario').fill(E2E_USER);
		await page.getByLabel('Contraseña').fill('no-es-la-clave');
		await page.getByRole('button', { name: 'Entrar' }).click();
		// 401 del servidor; si otra prueba agotó el límite de intentos (5/min), 429 con espera.
		await expect(page.getByRole('alert')).toContainText(/incorrectos|esperar/);
		await expect(page).toHaveURL(/\/admin\/login/);
	});

	test('con la clave correcta entra al panel con el menú de secciones', async ({ page }, info) => {
		test.skip(
			info.project.name !== 'chromium-escritorio',
			'un solo navegador: el login tiene límite por minuto'
		);
		await page.goto('/admin/radio');
		await expect(page).toHaveURL(/\/admin\/login\?next=%2Fadmin%2Fradio/);
		await page.getByLabel('Usuario').fill(E2E_USER);
		await page.getByLabel('Contraseña').fill(E2E_PASSWORD);
		await page.getByRole('button', { name: 'Entrar' }).click();
		await expect(page).toHaveURL('/admin/radio');
		await expect(page.getByRole('heading', { level: 1, name: 'Radio' })).toBeVisible();
		const nav = page.getByRole('navigation', { name: 'Menú del panel' });
		await expect(nav.getByRole('link', { name: 'Broker MQTT' })).toBeAttached();
		await expect(nav.getByRole('link', { name: 'Registros' })).toBeAttached();
	});
});
