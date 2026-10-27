// Pruebas extremo a extremo (27) contra el backend real sirviendo el build (CSP incluida).
// Antes: `pnpm build`. El backend aislado se levanta solo (puertos 8110/8111, datos en e2e/.data).
import { defineConfig, devices } from '@playwright/test';
import { BASE_URL, BUILD, LAN_PORT, PUBLIC_PORT, REPO } from './e2e/env';

const withWebkit = process.env.E2E_WEBKIT !== '0';
const ADMIN_SPEC = /admin\.spec\.ts$/;

export default defineConfig({
	testDir: './e2e',
	timeout: 60_000,
	expect: { timeout: 15_000 },
	fullyParallel: false,
	workers: 2,
	retries: process.env.CI ? 1 : 0,
	reporter: [['list'], ['html', { open: 'never', outputFolder: 'playwright-report' }]],
	globalSetup: './e2e/global-setup.ts',
	use: {
		baseURL: BASE_URL,
		trace: 'retain-on-failure',
		screenshot: 'only-on-failure',
		locale: 'es-AR',
		timezoneId: 'America/Argentina/Buenos_Aires',
		serviceWorkers: 'allow'
	},
	projects: [
		{
			name: 'chromium-escritorio',
			use: { ...devices['Desktop Chrome'], viewport: { width: 1440, height: 900 } }
		},
		// El panel (una sola sesión por el límite de inicios de sesión) se prueba en Chromium.
		{ name: 'pixel-7', use: { ...devices['Pixel 7'] }, testIgnore: ADMIN_SPEC },
		...(withWebkit
			? [
					{
						name: 'webkit-escritorio',
						use: { ...devices['Desktop Safari'] },
						testIgnore: ADMIN_SPEC
					}
				]
			: [])
	],
	webServer: {
		// Prepara los datos la primera vez y levanta `meshbox dev` (ver e2e/serve.mjs).
		command: 'node frontend/e2e/serve.mjs',
		cwd: REPO,
		url: `${BASE_URL}/api/v1/health`,
		reuseExistingServer: !process.env.CI,
		timeout: 120_000,
		stdout: 'ignore',
		stderr: 'pipe',
		env: {
			MESHBOX_PATHS__WEB: BUILD,
			MESHBOX_SERVER__LAN_BIND: `127.0.0.1:${LAN_PORT}`,
			MESHBOX_SERVER__PUBLIC_BIND: `127.0.0.1:${PUBLIC_PORT}`
		}
	}
});
