#!/usr/bin/env node
// Contraste de los tokens (16.2 y 16.1.5) contra el peor fondo: capa satelital con zonas
// claras (blanco) y el mapa oscuro. Las capas con alfa se componen en sRGB como el navegador.
// Uso: node scripts/contrast.mjs  (imprime una tabla en Markdown para docs/diseño/tokens.md)

const toLinear = (c) => (c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4);
const toGamma = (c) => (c <= 0.0031308 ? 12.92 * c : 1.055 * c ** (1 / 2.4) - 0.055);
const clamp = (x) => Math.min(1, Math.max(0, x));

/** oklch(L% C h / a) → [r, g, b, a] en sRGB gamma (0-1). */
function oklch(L, C, h, a = 1) {
	const l0 = L / 100;
	const hr = (h * Math.PI) / 180;
	const A = C * Math.cos(hr);
	const B = C * Math.sin(hr);
	const l = (l0 + 0.3963377774 * A + 0.2158037573 * B) ** 3;
	const m = (l0 - 0.1055613458 * A - 0.0638541728 * B) ** 3;
	const s = (l0 - 0.0894841775 * A - 1.291485548 * B) ** 3;
	const r = 4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s;
	const g = -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s;
	const b = -0.0041960863 * l - 0.7034186147 * m + 1.707614701 * s;
	return [clamp(toGamma(r)), clamp(toGamma(g)), clamp(toGamma(b)), a];
}
const hex = (h) => [1, 3, 5].map((i) => parseInt(h.slice(i, i + 2), 16) / 255).concat(1);
function over(top, bottom) {
	const a = top[3];
	return [0, 1, 2].map((i) => top[i] * a + bottom[i] * (1 - a)).concat(1);
}
const lum = (c) => 0.2126 * toLinear(c[0]) + 0.7152 * toLinear(c[1]) + 0.0722 * toLinear(c[2]);
function ratio(fg, bg) {
	const [hi, lo] = [lum(fg), lum(bg)].sort((x, y) => y - x);
	return (hi + 0.05) / (lo + 0.05);
}
const toHex = (c) =>
	'#' +
	c
		.slice(0, 3)
		.map((x) =>
			Math.round(x * 255)
				.toString(16)
				.padStart(2, '0')
		)
		.join('');

// Valores del plan (16.2) y valores finales de app.css, para ver por qué se ajustaron.
const DARK_BG = { 'satélite claro (blanco)': hex('#ffffff'), 'mapa oscuro': oklch(16, 0.02, 255) };
const LIGHT_BG = { 'satélite oscuro (negro)': hex('#000000'), 'mapa claro': oklch(97, 0.005, 255) };
const themes = {
	'oscuro, valores del plan': {
		backgrounds: DARK_BG,
		glass: oklch(22, 0.02, 255, 0.55),
		strong: oklch(22, 0.02, 255, 0.78),
		solid: oklch(22, 0.02, 255, 0.95),
		scrim: oklch(15, 0.02, 255, 0.35),
		fill1: oklch(100, 0, 0, 0.06),
		texts: {
			'--text-1': oklch(97, 0, 0),
			'--text-2': oklch(80, 0.01, 255),
			'--text-3 (65 %)': oklch(65, 0.01, 255),
			'--accent': oklch(72, 0.15, 210)
		}
	},
	'oscuro, valores finales': {
		backgrounds: DARK_BG,
		glass: oklch(22, 0.02, 255, 0.55),
		strong: oklch(22, 0.02, 255, 0.78),
		solid: oklch(22, 0.02, 255, 0.95),
		scrim: oklch(15, 0.02, 255, 0.6),
		fill1: oklch(100, 0, 0, 0.06),
		texts: {
			'--text-1': oklch(97, 0, 0),
			'--text-2': oklch(80, 0.01, 255),
			'--text-3 (72 %)': oklch(72, 0.01, 255),
			'--accent': oklch(72, 0.15, 210)
		}
	},
	'claro, valores finales': {
		backgrounds: LIGHT_BG,
		glass: oklch(99, 0.005, 255, 0.7),
		strong: oklch(99, 0.005, 255, 0.88),
		solid: oklch(99, 0.005, 255, 0.96),
		scrim: oklch(98, 0.005, 255, 0.55),
		fill1: oklch(20, 0.02, 255, 0.04),
		texts: {
			'--text-1': oklch(20, 0.02, 255),
			'--text-2': oklch(37, 0.02, 255),
			'--text-3': oklch(46, 0.02, 255),
			'--accent-ink (42 %)': oklch(42, 0.12, 220)
		}
	}
};

for (const [name, t] of Object.entries(themes)) {
	console.log(`\n### Tema ${name}\n`);
	console.log('| Texto | Fondo | glass + scrim | glass + scrim + fill-1 | fuerte | sólido |');
	console.log('|---|---|---|---|---|---|');
	for (const [bgName, bg] of Object.entries(t.backgrounds)) {
		const glassScrim = over(t.scrim, over(t.glass, bg));
		const card = over(t.fill1, glassScrim);
		const strong = over(t.strong, bg);
		const solid = over(t.solid, bg);
		for (const [tn, tc] of Object.entries(t.texts)) {
			const f = (b) => ratio(tc, b).toFixed(2);
			console.log(
				`| ${tn} | ${bgName} (${toHex(glassScrim)}) | ${f(glassScrim)} | ${f(card)} | ${f(strong)} | ${f(solid)} |`
			);
		}
	}
}

console.log('\n### Estados de nodo (ícono sobre borde oscuro y sobre el fondo)\n');
const outline = oklch(15, 0.02, 255);
const states = {
	activo: oklch(78, 0.17, 150),
	reciente: oklch(85, 0.15, 90),
	tardío: oklch(68, 0.19, 25),
	inactivo: oklch(62, 0.01, 255),
	infraestructura: oklch(75, 0.12, 220),
	alerta: oklch(65, 0.22, 30)
};
console.log('| Estado | Hex | contra borde oscuro | contra blanco |');
console.log('|---|---|---|---|');
for (const [n, c] of Object.entries(states)) {
	console.log(
		`| ${n} | ${toHex(c)} | ${ratio(c, outline).toFixed(2)} | ${ratio(c, hex('#ffffff')).toFixed(2)} |`
	);
}
