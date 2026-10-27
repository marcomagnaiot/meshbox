#!/usr/bin/env node
// Levanta el backend aislado de las pruebas e2e. Playwright arranca el webServer antes del
// globalSetup, así que los datos se preparan acá, una sola vez (marca e2e/.data/.ready):
// canal público, 24 h de historia reproducidas a máxima velocidad y un usuario del panel.
import { execFileSync, spawn } from 'node:child_process';
import { existsSync, mkdirSync, rmSync, writeFileSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const FRONTEND = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const REPO = resolve(FRONTEND, '..');
const DATA = join(FRONTEND, 'e2e', '.data');
const READY = join(DATA, '.ready');
const CONFIG = 'frontend/e2e/backend.toml';
const USER = process.env.E2E_USER ?? 'e2e';
const PASSWORD = process.env.E2E_PASSWORD ?? 'prueba-del-panel-2026';

function meshbox(args, input) {
	execFileSync('uv', ['run', 'meshbox', ...args, '--config', CONFIG], {
		cwd: REPO,
		input,
		stdio: input === undefined ? 'inherit' : ['pipe', 'inherit', 'inherit'],
		timeout: 600_000
	});
}

if (!existsSync(READY)) {
	rmSync(DATA, { recursive: true, force: true });
	mkdirSync(DATA, { recursive: true });
	meshbox(['channel', 'add', '--name', 'MediumFast', '--key', 'AQ==', '--public']);
	meshbox(['replay', 'backend/tests/fixtures/sim-24h.jsonl', '--speed', 'max']);
	meshbox(['user', 'create', USER, '--role', 'admin', '--password-stdin'], `${PASSWORD}\n`);
	writeFileSync(READY, new Date().toISOString());
}

const child = spawn('uv', ['run', 'meshbox', 'dev', '--config', CONFIG], {
	cwd: REPO,
	stdio: 'inherit',
	env: process.env
});
child.on('exit', (code) => process.exit(code ?? 0));
for (const signal of ['SIGINT', 'SIGTERM']) process.on(signal, () => child.kill(signal));
