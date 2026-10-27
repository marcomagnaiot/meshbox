#!/usr/bin/env node
// Descarga los recursos del estilo del mapa (tipografías SDF y sprites) desde
// protomaps/basemaps-assets a static/tiles-assets/. El backend los sirve en
// /tiles/fonts/... y /tiles/sprites/... desde <estáticos>/tiles-assets (sección 16.5).
//
// Solo baja las fuentes que usa el estilo generado con @protomaps/basemaps y solo los
// rangos útiles para español: Latin-1, Latin extendido, modificadores, diacríticos
// combinables y puntuación general. Los demás rangos MapLibre los dibuja localmente.
//
// Uso:
//   node scripts/fetch-map-assets.mjs              descarga lo que falte
//   node scripts/fetch-map-assets.mjs --force      vuelve a descargar todo
//   node scripts/fetch-map-assets.mjs --if-missing no hace nada si ya están todos
// Variable MAP_ASSETS_BASE: otra fuente (espejo) con la misma estructura.

import { mkdir, stat, writeFile } from 'node:fs/promises';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { layers, namedFlavor } from '@protomaps/basemaps';

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const OUT = join(ROOT, 'static', 'tiles-assets');
const BASE =
	process.env.MAP_ASSETS_BASE ?? 'https://raw.githubusercontent.com/protomaps/basemaps-assets/main';
const RANGES = ['0-255', '256-511', '512-767', '768-1023', '8192-8447'];
const SPRITES = ['light', 'dark'].flatMap((f) => [
	`${f}.json`,
	`${f}.png`,
	`${f}@2x.json`,
	`${f}@2x.png`
]);
// Fuentes de escrituras que no aparecen con lang=es en la región (se dibujan localmente si hiciera falta).
const SKIP_FONTS = /Devanagari/;
const LIMIT_BYTES = 5 * 1024 * 1024;

function stylesFonts() {
	const fonts = new Set();
	for (const flavor of ['dark', 'light']) {
		const json = JSON.stringify(layers('protomaps', namedFlavor(flavor), { lang: 'es' }));
		for (const m of json.matchAll(/"(Noto Sans[^"]*)"/g)) {
			if (!SKIP_FONTS.test(m[1])) fonts.add(m[1]);
		}
	}
	return [...fonts].sort();
}

async function exists(path) {
	try {
		return (await stat(path)).size > 0;
	} catch {
		return false;
	}
}

async function download(url, dest, attempts = 3) {
	for (let i = 1; i <= attempts; i++) {
		try {
			const res = await fetch(url);
			if (!res.ok) throw new Error(`HTTP ${res.status}`);
			const buf = Buffer.from(await res.arrayBuffer());
			await mkdir(dirname(dest), { recursive: true });
			await writeFile(dest, buf);
			return buf.length;
		} catch (err) {
			if (i === attempts)
				throw new Error(`no se pudo bajar ${url}: ${err.message}`, { cause: err });
			await new Promise((r) => setTimeout(r, 500 * i));
		}
	}
	return 0;
}

async function main() {
	const force = process.argv.includes('--force');
	const ifMissing = process.argv.includes('--if-missing');
	const fonts = stylesFonts();
	const jobs = [
		...fonts.flatMap((font) =>
			RANGES.map((r) => ({
				url: `${BASE}/fonts/${encodeURIComponent(font)}/${r}.pbf`,
				dest: join(OUT, 'fonts', font, `${r}.pbf`)
			}))
		),
		...SPRITES.map((name) => ({
			url: `${BASE}/sprites/v4/${name}`,
			dest: join(OUT, 'sprites', 'v4', name)
		}))
	];

	const missing = [];
	for (const job of jobs) if (force || !(await exists(job.dest))) missing.push(job);
	if (ifMissing && missing.length === 0) return;

	console.log(
		`recursos del mapa: ${fonts.join(', ')}; ${missing.length} de ${jobs.length} por bajar`
	);
	let total = 0;
	const queue = [...missing];
	const workers = Array.from({ length: 4 }, async () => {
		while (queue.length) {
			const job = queue.shift();
			// `total += await ...` leería `total` antes de esperar y perdería sumas concurrentes.
			const bytes = await download(job.url, job.dest);
			total += bytes;
		}
	});
	await Promise.all(workers);

	let size = 0;
	for (const job of jobs) size += (await stat(job.dest)).size;
	console.log(
		`listo: ${(total / 1024).toFixed(0)} KB descargados; tiles-assets ocupa ${(size / 1024).toFixed(0)} KB`
	);
	if (size > LIMIT_BYTES) {
		console.warn('aviso: más de 5 MB; no versionar static/tiles-assets (agregar al .gitignore)');
	}
}

main().catch((err) => {
	console.error(err.message);
	process.exit(1);
});
