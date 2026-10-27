#!/usr/bin/env node
// Capturas de docs/diseño/capturas (16.8). Usa el Chromium de Playwright contra la app en marcha:
// `pnpm dev` con el backend de desarrollo (red simulada) o el build servido por el backend.
// Uso: BASE_URL=http://localhost:5173 ADMIN_PASSWORD=… node scripts/capturas.mjs [nombre…]
// Sin ADMIN_PASSWORD se omiten las del panel y del asistente (con un solo inicio de sesión).
// Con nombres, solo regenera esas capturas.

import { mkdirSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { chromium, devices } from '@playwright/test';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..');
const OUT = join(ROOT, '..', 'docs', 'diseño', 'capturas');
const BASE = process.env.BASE_URL ?? 'http://localhost:5173';
const ADMIN_USER = process.env.ADMIN_USER ?? 'admin';
const ADMIN_PASSWORD = process.env.ADMIN_PASSWORD;
// Nodo móvil del simulador (camioneta con recorrido).
const NODE = process.env.CAPTURE_NODE ?? '!0b03cbf5';

const COMMON = {
	locale: 'es-AR',
	timezoneId: 'America/Argentina/Buenos_Aires',
	colorScheme: 'dark',
	// Sin animaciones: el mapa salta al nodo y las capturas salen iguales cada vez.
	reducedMotion: 'reduce'
};
const PC = { viewport: { width: 1440, height: 900 }, deviceScaleFactor: 1 };
const TABLET = { viewport: { width: 1180, height: 820 }, deviceScaleFactor: 1, hasTouch: true };
const PHONE = { ...devices['Pixel 7'], deviceScaleFactor: 2 };
const PHONE_LANDSCAPE = { ...devices['Pixel 7 landscape'], deviceScaleFactor: 2 };

const SHOTS = [
	{ name: 'pc-mapa', device: PC, path: '/' },
	{ name: 'pc-ficha', device: PC, path: `/n/${NODE}`, ready: fichaReady, act: recenter },
	{ name: 'pc-capas', device: PC, path: '/', act: openLayers },
	{
		name: 'pc-estadisticas-claro-solido',
		device: PC,
		path: '/estadisticas',
		prefs: { theme: 'light', solid: true },
		ready: statsReady
	},
	{ name: 'celular-mapa', device: PHONE, path: '/' },
	{
		name: 'celular-ficha',
		device: PHONE,
		path: `/n/${NODE}`,
		ready: fichaReady,
		act: recenter
	},
	{ name: 'celular-chat', device: PHONE, path: '/chat', ready: chatReady },
	{
		name: 'tableta-ficha',
		device: TABLET,
		path: `/n/${NODE}`,
		ready: fichaReady,
		act: recenter
	},
	{ name: 'apaisado-chat', device: PHONE_LANDSCAPE, path: '/chat', ready: chatReady },
	{ name: 'panel-seccion', device: PC, path: '/admin/radio', admin: true },
	{ name: 'panel-resumen', device: PC, path: '/admin', admin: true, full: true },
	{ name: 'panel-paquetes', device: PC, path: '/admin/paquetes', admin: true, ready: packetsReady },
	{
		name: 'panel-alertas-regla',
		device: PC,
		path: '/admin/alertas',
		admin: true,
		act: openRuleForm
	},
	{ name: 'panel-red', device: PC, path: '/admin/red', admin: true, full: true },
	{ name: 'panel-registros', device: PC, path: '/admin/registros', admin: true },
	{ name: 'panel-plugins', device: PC, path: '/admin/plugins', admin: true, full: true },
	{ name: 'panel-celular-nodos', device: PHONE, path: '/admin/nodos', admin: true },
	{ name: 'asistente', device: PC, path: '/setup', admin: true, ready: setupReady },
	{ name: 'asistente-celular', device: PHONE, path: '/setup', admin: true, ready: setupReady }
];

/**
 * Mapa con nodos dibujados y teselas cargadas. No espera el evento `idle`: con datos en vivo
 * las fuentes GeoJSON cambian cada medio segundo y el mapa casi nunca queda quieto.
 */
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
		.catch(() => console.warn('teselas sin terminar de cargar; se captura igual'));
}

async function fichaReady(page) {
	await page.getByRole('heading', { level: 1 }).first().waitFor();
	await page
		.getByText(/^Posiciones: \d+/)
		.first()
		.waitFor({ timeout: 30_000 });
}

/** El nodo móvil sigue andando (reproducción a 10×): se vuelve a centrar justo antes. */
async function recenter(page) {
	await page.getByRole('button', { name: 'Centrar en el mapa' }).first().click();
	await page.mouse.move(1, 1); // sin el resaltado de "hover" en el botón
	await page.waitForFunction(() => !window.__meshboxMap.isMoving(), undefined, { polling: 100 });
}

async function statsReady(page) {
	await page.locator('.uplot').first().waitFor({ timeout: 30_000 });
}

async function chatReady(page) {
	await page.waitForFunction(() => document.querySelectorAll('.msg').length > 5, undefined, {
		timeout: 30_000
	});
}

async function openLayers(page) {
	await page.getByRole('button', { name: 'Capas del mapa' }).first().click();
	await page.getByRole('switch').first().waitFor();
}

async function packetsReady(page) {
	await page.waitForFunction(
		() => document.querySelectorAll('.dt-row.dt-body').length > 8,
		undefined,
		{
			timeout: 60_000
		}
	);
}

async function openRuleForm(page) {
	await page.getByRole('button', { name: 'Agregar regla' }).click();
	await page.getByRole('dialog').getByRole('button', { name: 'Guardar' }).waitFor();
}

async function setupReady(page) {
	await page.locator('#step-title').waitFor();
}

/** Un solo inicio de sesión para todas las capturas del panel (límite de 5 intentos por minuto). */
async function adminState(browser) {
	const context = await browser.newContext(COMMON);
	const page = await context.newPage();
	await page.goto(`${BASE}/admin/login`);
	await page.getByLabel('Usuario').fill(ADMIN_USER);
	await page.getByLabel('Contraseña').fill(ADMIN_PASSWORD);
	await page.getByRole('button', { name: 'Entrar' }).click();
	await page.waitForURL((u) => !u.pathname.startsWith('/admin/login'));
	const state = await context.storageState();
	await context.close();
	return state;
}

const only = process.argv.slice(2);
const shots = SHOTS.filter((s) => only.length === 0 || only.includes(s.name));
mkdirSync(OUT, { recursive: true });

// Chromium completo en modo sin ventana: el "headless shell" deja rectángulos sin pintar sobre
// el lienzo WebGL al abrir menús.
const browser = await chromium.launch({ channel: 'chromium' });
let session = null;
try {
	for (const shot of shots) {
		if (shot.admin && !ADMIN_PASSWORD) {
			console.log(`${shot.name}: omitida (falta ADMIN_PASSWORD)`);
			continue;
		}
		if (shot.admin && !session) session = await adminState(browser);
		const context = await browser.newContext({
			...COMMON,
			...shot.device,
			...(shot.admin ? { storageState: session } : {})
		});
		await context.addInitScript(
			(prefs) => {
				try {
					localStorage.setItem('meshbox.prefs', JSON.stringify(prefs));
				} catch {
					// sin almacenamiento: quedan los valores por defecto
				}
			},
			shot.prefs ?? { theme: 'dark' }
		);
		const page = await context.newPage();
		if (shot.admin) {
			await page.goto(`${BASE}${shot.path}`);
			if (shot.path.startsWith('/admin')) {
				await page.getByRole('heading', { level: 1 }).first().waitFor();
				await page
					.locator('main [aria-busy="true"]')
					.first()
					.waitFor({ state: 'detached', timeout: 20_000 })
					.catch(() => {});
			}
			if (shot.ready) await shot.ready(page);
			if (shot.act) await shot.act(page);
		} else {
			await page.goto(`${BASE}${shot.path}`);
			await mapIdle(page);
			if (shot.ready) await shot.ready(page);
			if (shot.act) await shot.act(page);
			await mapIdle(page);
		}
		await page.evaluate(() => document.fonts.ready);
		await page.waitForTimeout(600);
		const file = join(OUT, `${shot.name}.jpg`);
		await page.screenshot({ path: file, type: 'jpeg', quality: 80, fullPage: Boolean(shot.full) });
		console.log(`${shot.name}: ${file}`);
		await context.close();
	}
} finally {
	await browser.close();
}
