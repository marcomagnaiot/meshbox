#!/usr/bin/env node
// Capturas del manual (docs/manual/img). Usa el Chromium de Playwright contra el servidor de
// prueba de scripts/manual_servidor.py: instalación nueva, red simulada y placa simulada, sin
// datos reales.
//
//   uv run python scripts/manual_servidor.py <carpeta nueva> 8120
//   BASE_URL=http://127.0.0.1:8120 node frontend/scripts/capturas-manual.mjs asistente
//   (con la red ya cargada) node frontend/scripts/capturas-manual.mjs sitio panel
//
// La IP de la PC que aparece en algunos textos se reemplaza por 192.168.0.10.

import { mkdirSync } from 'node:fs';
import { networkInterfaces } from 'node:os';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { chromium, devices } from '@playwright/test';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..');
const OUT = join(ROOT, '..', 'docs', 'manual', 'img');
const BASE = process.env.BASE_URL ?? 'http://127.0.0.1:8120';
const USER = 'admin';
const PASSWORD = 'una frase larga para el panel';
const NODE = process.env.CAPTURE_NODE ?? '!0b03cbf5';
const SHOW_IP = '192.168.0.10';
const LOCAL_IPS = Object.values(networkInterfaces())
	.flat()
	.filter((a) => a && a.family === 'IPv4' && !a.internal)
	.map((a) => a.address);

const COMMON = {
	locale: 'es-AR',
	timezoneId: 'America/Argentina/Buenos_Aires',
	colorScheme: 'dark',
	reducedMotion: 'reduce'
};
const PC = { viewport: { width: 1360, height: 860 }, deviceScaleFactor: 1 };
const PHONE = { ...devices['Pixel 7'], deviceScaleFactor: 2 };

mkdirSync(OUT, { recursive: true });

/** La IP de la PC no sale en las capturas. El flujo en vivo (SSE) no se toca. */
async function maskIp(context) {
	await context.route(
		(url) => url.pathname.startsWith('/api/') && !url.pathname.includes('/stream'),
		async (route) => {
			try {
				const response = await route.fetch();
				let body = await response.text();
				for (const ip of LOCAL_IPS) body = body.replaceAll(ip, SHOW_IP);
				await route.fulfill({ response, body });
			} catch {
				// pedido cancelado al cambiar de página
				await route.continue().catch(() => {});
			}
		}
	);
}

async function newPage(browser, device = PC, storageState) {
	// Sin service worker: el aviso «El sitio quedó disponible sin conexión» taparía la captura.
	const context = await browser.newContext({
		...COMMON,
		...device,
		storageState,
		serviceWorkers: 'block'
	});
	await context.addInitScript(() => {
		try {
			localStorage.setItem('meshbox.prefs', JSON.stringify({ theme: 'dark' }));
		} catch {
			// sin almacenamiento
		}
	});
	await maskIp(context);
	return { context, page: await context.newPage() };
}

async function shot(page, name, opts = {}) {
	await page.evaluate(() => document.fonts.ready);
	await page.waitForTimeout(opts.wait ?? 700);
	const file = join(OUT, `${name}.jpg`);
	await page.screenshot({ path: file, type: 'jpeg', quality: 82, fullPage: Boolean(opts.full) });
	console.log(`${name}: ${file}`);
}

async function stepTitle(page, text) {
	await page.locator('#step-title').filter({ hasText: text }).waitFor({ timeout: 30_000 });
}

async function next(page, name = /Continuar|Crear y continuar|Configurar|Terminar/) {
	await page.getByRole('button', { name }).last().click();
}

async function mapIdle(page) {
	await page.waitForFunction(
		() => {
			const m = window.__meshboxMap;
			if (!m || !m.getSource('m-nodes')) return false;
			const layers = ['m-nodes-icon', 'm-clusters', 'm-selected-icon'].filter((id) =>
				m.getLayer(id)
			);
			return layers.length > 0 && m.queryRenderedFeatures({ layers }).length > 0;
		},
		undefined,
		{ timeout: 60_000, polling: 250 }
	);
	await page
		.waitForFunction(() => window.__meshboxMap.areTilesLoaded(), undefined, {
			timeout: 20_000,
			polling: 250
		})
		.catch(() => {});
}

// ------------------------------------------------------------------ asistente

async function asistente(browser) {
	const { context, page } = await newPage(browser);
	// Un nodo Heltec V3 enchufado: el paso Radio lo detecta (en la PC no hay puerto serie).
	await context.route('**/api/v1/admin/connectors/serial-ports', (route) =>
		route.fulfill({
			json: {
				ports: [{ device: '/dev/ttyUSB0', description: 'CP2102 USB to UART Bridge Controller' }]
			}
		})
	);
	await context.route('**/api/v1/admin/connectors/*/test', (route) =>
		route.fulfill({
			json: {
				ok: true,
				node: {
					num: 3127830956,
					user: {
						id: '!ba6fe1ac',
						longName: 'Heltec de la casa',
						shortName: 'CASA',
						hwModel: 'HELTEC_V3'
					},
					firmware_version: '2.7.15'
				}
			}
		})
	);
	await page.goto(`${BASE}/`);
	await page.getByText('Falta configurar meshbox').waitFor({ timeout: 30_000 });
	await shot(page, 'sitio-falta-configurar');

	await page.goto(`${BASE}/setup`);
	await stepTitle(page, 'Código');
	await page.getByRole('textbox', { name: /^Código/ }).fill('ABCD2345');
	await shot(page, 'asistente-01-codigo');
	await next(page);

	await stepTitle(page, 'Idioma');
	await shot(page, 'asistente-02-idioma');
	await next(page);

	await stepTitle(page, 'Cuenta');
	await page.getByRole('textbox', { name: /^Usuario/ }).fill(USER);
	await page.getByLabel(/^Contraseña/).fill(PASSWORD);
	await page.getByLabel(/^Repetir la contraseña/).fill(PASSWORD);
	await shot(page, 'asistente-03-administrador');
	await next(page);

	await stepTitle(page, 'Sitio');
	await page.getByRole('textbox', { name: /^Nombre/ }).fill('Red Meshtastic de la zona');
	await page
		.getByRole('textbox', { name: /^Descripción/ })
		.fill('Mapa en vivo de la red Meshtastic de la zona.');
	await page.getByRole('searchbox', { name: 'Buscar un lugar' }).fill('Viedma, Río Negro');
	await page.getByRole('searchbox', { name: 'Buscar un lugar' }).press('Enter');
	await page.locator('.place-search .results button').first().waitFor({ timeout: 30_000 });
	await shot(page, 'asistente-04a-sitio-buscar', { full: true });
	await page.locator('.place-search .results button').first().click();
	await page.waitForTimeout(2500);
	await shot(page, 'asistente-04b-sitio', { full: true });
	await next(page);

	await stepTitle(page, 'Radio');
	await page.waitForTimeout(1500);
	await shot(page, 'asistente-05a-radio', { full: true });
	await next(page);
	await page.getByRole('button', { name: 'Probar la conexión' }).click();
	await page.getByText('El nodo respondió.').waitFor();
	await shot(page, 'asistente-05b-radio-prueba', { full: true });
	await next(page);

	await stepTitle(page, 'Canal');
	await page.getByRole('combobox', { name: /^Nombre del canal/ }).fill('MediumFast');
	await shot(page, 'asistente-06-canal');
	await next(page);

	await stepTitle(page, 'Privacidad');
	await shot(page, 'asistente-07-privacidad', { full: true });
	await next(page);

	await stepTitle(page, 'Mapa base');
	await page.waitForTimeout(2500);
	await page.getByRole('button', { name: 'Usar la vista como caja' }).click();
	await shot(page, 'asistente-08-mapa-base', { full: true });
	await page.getByRole('button', { name: /Hacerlo después|Omitir/ }).click();

	await stepTitle(page, 'Publicar');
	await shot(page, 'asistente-09-cloudflare');
	await page.getByRole('button', { name: /Hacerlo después|Omitir/ }).click();

	await stepTitle(page, 'Verificación');
	await page.waitForTimeout(8000);
	// En la PC los paquetes vienen de la red simulada y no hay placa en /dev/ttyUSB0: se muestra
	// lo que ve una instalación real con la placa enchufada.
	await page.evaluate(() => {
		const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
		for (let n = walker.nextNode(); n; n = walker.nextNode()) {
			if (n.textContent?.includes('usb-heltec')) n.textContent = 'usb-heltec: Conectado';
		}
	});
	await shot(page, 'asistente-10-verificacion', { full: true });
	await next(page, 'Terminar');
	await page.getByText('¡Listo!').waitFor();
	await shot(page, 'asistente-11-listo');
	await context.close();
}

// ------------------------------------------------------------------ sitio público

async function sitio(browser) {
	let { context, page } = await newPage(browser);
	await page.goto(`${BASE}/`);
	await mapIdle(page);
	await shot(page, 'sitio-mapa', { wait: 1500 });

	await page.getByRole('button', { name: 'Capas del mapa' }).first().click();
	await page.getByRole('switch').first().waitFor();
	await shot(page, 'sitio-capas');

	await page.goto(`${BASE}/n/${NODE}`);
	await page.getByRole('heading', { level: 1 }).first().waitFor();
	await mapIdle(page);
	await page.getByRole('button', { name: 'Centrar en el mapa' }).first().click();
	await page.mouse.move(1, 1);
	await shot(page, 'sitio-ficha', { wait: 1500 });

	await page.goto(`${BASE}/estadisticas`);
	await page.locator('.uplot').first().waitFor({ timeout: 30_000 });
	await shot(page, 'sitio-estadisticas', { wait: 1500 });

	await page.goto(`${BASE}/alertas`);
	await mapIdle(page);
	await shot(page, 'sitio-alertas');
	await context.close();

	({ context, page } = await newPage(browser, PHONE));
	await page.goto(`${BASE}/`);
	await mapIdle(page);
	await shot(page, 'celular-mapa', { wait: 1500 });
	await page.goto(`${BASE}/chat`);
	await page.waitForFunction(() => document.querySelectorAll('.msg').length > 5, undefined, {
		timeout: 30_000
	});
	await shot(page, 'celular-chat');
	await context.close();
}

// ------------------------------------------------------------------ panel

async function login(browser) {
	const { context, page } = await newPage(browser);
	await page.goto(`${BASE}/admin/login`);
	await page.getByLabel('Usuario').fill(USER);
	await page.getByLabel('Contraseña').fill(PASSWORD);
	await page.getByRole('button', { name: 'Entrar' }).click();
	await page.waitForURL((u) => !u.pathname.startsWith('/admin/login'));
	const state = await context.storageState();
	await context.close();
	return state;
}

async function panel(browser) {
	const state = await login(browser);
	const { context, page } = await newPage(browser, PC, state);
	const pages = [
		['panel-resumen', '/admin', { full: true }],
		['panel-cliente-estado', '/admin/cliente', { full: true }],
		['panel-canales', '/admin/canales', {}],
		['panel-nodos', '/admin/nodos', {}],
		['panel-sitio', '/admin/sitio', {}],
		['panel-privacidad', '/admin/privacidad', {}],
		['panel-cloudflare', '/admin/cloudflare', {}],
		['panel-usuarios', '/admin/usuarios', {}],
		['panel-respaldo', '/admin/respaldo', {}],
		['panel-actualizaciones', '/admin/actualizaciones', {}]
	];
	for (const [name, path, opts] of pages) {
		await page.goto(`${BASE}${path}`);
		await page.getByRole('heading', { level: 1 }).first().waitFor();
		await page
			.locator('main [aria-busy="true"]')
			.first()
			.waitFor({ state: 'detached', timeout: 20_000 })
			.catch(() => {});
		await shot(page, name, { ...opts, wait: 2000 });
	}
	await page.goto(`${BASE}/admin/cliente`);
	await page.getByRole('heading', { level: 1 }).first().waitFor();
	await page
		.getByRole('radio', { name: 'Mensajes' })
		.click()
		.catch(async () => {
			await page.getByRole('tab', { name: 'Mensajes' }).click();
		});
	await shot(page, 'panel-cliente-mensajes', { wait: 2000 });

	// Broker MQTT con la cuenta de un Heltec por WiFi: la contraseña y los comandos salen una vez.
	await page.goto(`${BASE}/admin/mqtt`);
	await page.getByRole('heading', { level: 1 }).first().waitFor();
	await page.getByRole('button', { name: 'Crear cuenta' }).first().click();
	const form = page.getByRole('dialog');
	await form.getByRole('textbox', { name: /^Nombre/ }).fill('techo');
	await form.getByRole('textbox', { name: /^Nota/ }).fill('Heltec del techo, por WiFi');
	await shot(page, 'panel-mqtt-crear');
	await form.getByRole('button', { name: 'Crear' }).click();
	await page.getByRole('dialog').getByText('gw-techo').first().waitFor();
	await shot(page, 'panel-mqtt-cuenta', { wait: 1200 });
	await page.keyboard.press('Escape');
	await page.waitForTimeout(800);
	await shot(page, 'panel-mqtt', { full: true, wait: 1500 });
	await context.close();
}

const phases = { asistente, sitio, panel };
const wanted = process.argv.slice(2);
const browser = await chromium.launch({ channel: 'chromium' });
try {
	for (const name of wanted.length ? wanted : Object.keys(phases)) {
		if (!phases[name]) throw new Error(`fase desconocida: ${name}`);
		console.log(`== ${name}`);
		await phases[name](browser);
	}
} finally {
	await browser.close();
}
