import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

export const FRONTEND = resolve(dirname(fileURLToPath(import.meta.url)), '..');
export const REPO = resolve(FRONTEND, '..');
export const BUILD = join(FRONTEND, 'build');
export const LAN_PORT = 8110;
export const PUBLIC_PORT = 8111;
export const BASE_URL = `http://127.0.0.1:${LAN_PORT}`;
export const PUBLIC_URL = `http://127.0.0.1:${PUBLIC_PORT}`;
// Usuario de prueba del backend aislado (lo crea e2e/serve.mjs en e2e/.data, fuera del repositorio).
export const E2E_USER = 'e2e';
export const E2E_PASSWORD = 'prueba-del-panel-2026';
