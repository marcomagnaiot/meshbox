// Antes de las pruebas: el build tiene que existir (el backend lo sirve con su CSP).
// Los datos del backend los prepara e2e/serve.mjs al levantarlo.
import { existsSync } from 'node:fs';
import { join } from 'node:path';
import { BUILD } from './env';

export default function globalSetup(): void {
	if (!existsSync(join(BUILD, 'index.html'))) {
		throw new Error('Falta el build del frontend: ejecutar `pnpm build` antes de `pnpm e2e`.');
	}
}
