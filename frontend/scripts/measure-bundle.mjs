#!/usr/bin/env node
// Mide el JS inicial de la ruta "/" (presupuesto 5.5: ≤ 180 KB comprimido, sin MapLibre) y
// los paquetes diferidos. Usa el manifiesto de Vite del build: suma el cierre de imports
// estáticos de la entrada de SvelteKit, el layout raíz, el layout público y la página de inicio.
// También verifica que el prefijo -webkit- del glass lleve valores escritos (16.1.6).
// Uso: pnpm build && pnpm size

import { readFileSync, readdirSync, statSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { brotliCompressSync, gzipSync } from 'node:zlib';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..');
const CLIENT = join(ROOT, '.svelte-kit', 'output', 'client');
const BUILD = join(ROOT, 'build');
const manifest = JSON.parse(readFileSync(join(CLIENT, '.vite', 'manifest.json'), 'utf8'));
const BUDGET_KB = 180;

const gz = (buf) => gzipSync(buf, { level: 9 }).length;
const br = (buf) => brotliCompressSync(buf).length;
const kb = (n) => (n / 1024).toFixed(1);

function entryFor(predicate) {
	const key = Object.keys(manifest).find(predicate);
	if (!key) throw new Error('no se encontró la entrada en el manifiesto');
	return key;
}

/** Cierre de imports estáticos (los dinámicos, como MapLibre, quedan afuera). */
function closure(keys) {
	const seen = new Set();
	const css = new Set();
	const stack = [...keys];
	while (stack.length) {
		const key = stack.pop();
		if (seen.has(key)) continue;
		seen.add(key);
		const chunk = manifest[key];
		for (const c of chunk.css ?? []) css.add(c);
		for (const imp of chunk.imports ?? []) stack.push(imp);
	}
	return { files: [...seen].map((k) => manifest[k].file), css: [...css] };
}

function sizeOf(files) {
	let raw = 0;
	let g = 0;
	let b = 0;
	for (const f of files) {
		const buf = readFileSync(join(CLIENT, f));
		raw += buf.length;
		g += gz(buf);
		b += br(buf);
	}
	return { raw, gz: g, br: b };
}

// SvelteKit genera un nodo por layout/página (nodes/N.js) que reexporta el componente.
const NODES_DIR = join(ROOT, '.svelte-kit', 'generated', 'client-optimized', 'nodes');
function nodeFor(component) {
	for (const f of readdirSync(NODES_DIR)) {
		const src = readFileSync(join(NODES_DIR, f), 'utf8');
		if (src.includes(`src/routes/${component}"`)) {
			return entryFor((k) => k.endsWith(`client-optimized/nodes/${f}`));
		}
	}
	throw new Error(`no se encontró el nodo de ${component}`);
}

const roots = [
	entryFor((k) => k.endsWith('runtime/client/entry.js')),
	entryFor((k) => k.endsWith('generated/client-optimized/app.js')),
	nodeFor('+layout.svelte'),
	nodeFor('(public)/+layout.svelte'),
	nodeFor('(public)/+page.svelte')
];
const initial = closure(roots);
const initialSize = sizeOf(initial.files);
const cssSize = sizeOf(initial.css);

// Diferidos: lo que se pide con import() desde el layout público y la ficha.
function lazy(sourceMatch) {
	const key = Object.keys(manifest).find((k) => sourceMatch.test(k));
	if (!key) return null;
	const own = closure([key]);
	const extra = own.files.filter((f) => !initial.files.includes(f));
	return { key, size: sizeOf(extra), files: extra.length };
}

const map = lazy(/src\/lib\/map\/MapView\.svelte$/);
const uplot = lazy(/node_modules\/.*uplot\/dist\/uPlot\.esm\.js$/);

// Workers (el de MapLibre 6 va aparte y se pide al crear el mapa).
const WORKERS = join(CLIENT, '_app', 'immutable', 'workers');
let workerFiles = [];
try {
	workerFiles = readdirSync(WORKERS)
		.filter((f) => f.endsWith('.js'))
		.map((f) => join('_app', 'immutable', 'workers', f));
} catch {
	// sin workers
}

const rows = [
	['JS inicial de "/" (sin MapLibre)', initialSize, initial.files.length],
	['CSS inicial', cssSize, initial.css.length],
	...(map ? [['Mapa diferido (MapLibre + estilo + capas)', map.size, map.files]] : []),
	...(workerFiles.length
		? [['Worker de MapLibre (diferido)', sizeOf(workerFiles), workerFiles.length]]
		: []),
	...(uplot ? [['uPlot diferido (gráficos completos)', uplot.size, uplot.files]] : [])
];

console.log('| Paquete | Archivos | Sin comprimir | gzip -9 | brotli |');
console.log('|---|---|---|---|---|');
for (const [name, s, n] of rows) {
	console.log(`| ${name} | ${n} | ${kb(s.raw)} KB | ${kb(s.gz)} KB | ${kb(s.br)} KB |`);
}

let total = 0;
let compressed = 0;
const walk = (dir) => {
	for (const f of readdirSync(dir)) {
		const p = join(dir, f);
		const st = statSync(p);
		if (st.isDirectory()) walk(p);
		else if (/\.(br|gz)$/.test(f)) compressed += st.size;
		else total += st.size;
	}
};
walk(BUILD);
console.log(
	`\nbuild/ completo (con tiles-assets): ${kb(total)} KB, más ${kb(compressed)} KB de copias .br/.gz`
);

const ok = initialSize.gz / 1024 <= BUDGET_KB;
console.log(
	`Presupuesto JS inicial: ${kb(initialSize.gz)} KB de ${BUDGET_KB} KB → ${ok ? 'dentro' : 'EXCEDIDO'}`
);

// Glass: el prefijo -webkit- debe llevar valores escritos (Safari no acepta variables ahí).
const cssDir = join(CLIENT, '_app', 'immutable', 'assets');
const allCss = readdirSync(cssDir)
	.filter((f) => f.endsWith('.css'))
	.map((f) => readFileSync(join(cssDir, f), 'utf8'))
	.join('\n');
const webkitVar = /-webkit-backdrop-filter:\s*blur\(var\(/.test(allCss);
const webkitLiteral = /-webkit-backdrop-filter:\s*blur\(16px\)/.test(allCss);
console.log(`Glass -webkit- con valores escritos: ${webkitLiteral && !webkitVar ? 'sí' : 'NO'}`);

if (!ok || webkitVar || !webkitLiteral) process.exitCode = 1;
