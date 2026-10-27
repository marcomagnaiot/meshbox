#!/usr/bin/env node
// Genera src/lib/api/schema.d.ts desde el OpenAPI del backend (solo servidor LAN; en modo
// desarrollo no pide sesión). Backend: MESHBOX_BACKEND (por defecto http://127.0.0.1:8100).

import { writeFile } from 'node:fs/promises';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import openapiTS, { astToString } from 'openapi-typescript';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..');
const backend = process.env.MESHBOX_BACKEND ?? 'http://127.0.0.1:8100';
const url = new URL('/api/openapi.json', backend);

const ast = await openapiTS(url, { alphabetize: true, exportType: true });
const header =
	'// Generado con `pnpm gen:api` desde ' + url.pathname + ' del backend. No editar a mano.\n\n';
const out = join(ROOT, 'src', 'lib', 'api', 'schema.d.ts');
await writeFile(out, header + astToString(ast));
console.log(`tipos generados en ${out}`);
