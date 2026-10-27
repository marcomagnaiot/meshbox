// Color de cada nodo, el mismo que le da la app de Meshtastic para Android: los 24 bits bajos
// del número del nodo son rojo, verde y azul. Así un nodo se reconoce igual en meshbox y en
// el celular. El texto encima va en negro o blanco, el de más contraste (siempre ≥ 4,5:1).
import { contrastRatio, rgbToOklch, type Rgb } from './color';
import { nodeNum } from './ids';

/** Croma máxima del tinte de las burbujas: el tono del nodo, sin colores chillones. */
const BUBBLE_CHROMA = 0.11;

export interface NodeColor {
	rgb: Rgb;
	/** Color exacto (chip con el nombre corto). */
	css: string;
	/** Texto sobre ese color: negro o blanco. */
	ink: string;
	/** Tono y croma (OKLCH) para teñir la burbuja con el brillo de cada tema. */
	hue: number;
	chroma: number;
}

export function nodeColor(id: string | null | undefined): NodeColor | null {
	if (!id) return null;
	const num = nodeNum(id);
	if (!Number.isFinite(num)) return null;
	const rgb: Rgb = [(num >> 16) & 255, (num >> 8) & 255, num & 255];
	const ink =
		contrastRatio(rgb, [0, 0, 0]) >= contrastRatio(rgb, [255, 255, 255]) ? '#000000' : '#ffffff';
	const { C, h } = rgbToOklch(rgb);
	return {
		rgb,
		css: `rgb(${rgb.join(' ')})`,
		ink,
		hue: Math.round(h),
		chroma: Math.min(C, BUBBLE_CHROMA)
	};
}

/**
 * Variables CSS con el color del nodo: `--node` y `--node-ink` (chip), `--node-h` y `--node-c`
 * (burbuja, ver `--node-bubble-l` en app.css). Sin id válido no pinta nada.
 */
export function nodeColorStyle(id: string | null | undefined): string | undefined {
	const c = nodeColor(id);
	if (!c) return undefined;
	return `--node:${c.css};--node-ink:${c.ink};--node-h:${c.hue};--node-c:${c.chroma.toFixed(3)}`;
}
