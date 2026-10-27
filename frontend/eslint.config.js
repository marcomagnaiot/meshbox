import js from '@eslint/js';
import prettier from 'eslint-config-prettier';
import svelte from 'eslint-plugin-svelte';
import { defineConfig } from 'eslint/config';
import globals from 'globals';
import ts from 'typescript-eslint';
import svelteConfig from './svelte.config.js';

export default defineConfig(
	{
		ignores: [
			'build/',
			'.svelte-kit/',
			'dev-dist/',
			'node_modules/',
			'src/lib/paraglide/',
			'src/lib/api/schema.d.ts',
			'static/',
			'test-results/',
			'playwright-report/',
			'e2e/.data/',
			'project.inlang/'
		]
	},
	js.configs.recommended,
	...ts.configs.recommended,
	...svelte.configs.recommended,
	prettier,
	...svelte.configs.prettier,
	{
		languageOptions: {
			globals: { ...globals.browser, ...globals.node }
		}
	},
	{
		files: ['**/*.svelte', '**/*.svelte.ts', '**/*.svelte.js'],
		languageOptions: {
			parserOptions: {
				projectService: true,
				extraFileExtensions: ['.svelte'],
				parser: ts.parser,
				svelteConfig
			}
		}
	},
	{
		rules: {
			// Ningún texto que venga de la radio se inserta como HTML (13.5, regla 0.1.8).
			'svelte/no-at-html-tags': 'error',
			// La SPA se sirve siempre en la raíz (paths.base vacío): resolve() no aporta nada y
			// complicaría las rutas armadas por funciones (nodeHref, secciones del panel).
			'svelte/no-navigation-without-resolve': 'off',
			// Las tiendas usan $state.raw con Map/Set inmutables (se reemplaza el objeto entero
			// en cada cambio); SvelteMap haría reactivo cada set() sin necesidad.
			'svelte/prefer-svelte-reactivity': 'off',
			'svelte/no-target-blank': 'error',
			'svelte/button-has-type': 'error',
			'@typescript-eslint/no-unused-vars': [
				'error',
				{ argsIgnorePattern: '^_', varsIgnorePattern: '^_', caughtErrors: 'none' }
			],
			'no-undef': 'off'
		}
	}
);
