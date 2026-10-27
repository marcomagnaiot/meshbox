// Texto: búsqueda sin acentos y etiquetas del mapa con glifos disponibles.

/** Minúsculas y sin diacríticos, para comparar búsquedas ("Ñandú" ~ "nandu"). */
export function fold(text: string | null | undefined): string {
	return (text ?? '')
		.normalize('NFD')
		.replace(/\p{M}+/gu, '')
		.toLowerCase();
}

export function matches(query: string, ...fields: (string | null | undefined)[]): boolean {
	const q = fold(query).trim();
	if (!q) return true;
	const terms = q.split(/\s+/);
	const hay = fields.map(fold).join(' ');
	return terms.every((t) => hay.includes(t));
}

// Rangos de glifos que se publican en /tiles/fonts (scripts/fetch-map-assets.mjs).
const GLYPH_RANGES: [number, number][] = [
	[0x20, 0x3ff],
	[0x2000, 0x20ff]
];

function hasGlyph(cp: number): boolean {
	return GLYPH_RANGES.some(([a, b]) => cp >= a && cp <= b);
}

/**
 * Etiqueta para el mapa: solo caracteres con glifos publicados (los nombres cortos de
 * Meshtastic suelen llevar emojis, que pedirían rangos inexistentes). Si no queda nada,
 * se usa el respaldo.
 */
export function mapLabel(text: string | null | undefined, fallback: string): string {
	const clean = [...(text ?? '')]
		.filter((ch) => hasGlyph(ch.codePointAt(0) ?? 0))
		.join('')
		.trim();
	return clean || fallback;
}

/** Recorta con elipsis respetando caracteres compuestos. */
export function truncate(text: string, max: number): string {
	const chars = [...text];
	return chars.length <= max ? text : chars.slice(0, max - 1).join('') + '…';
}
