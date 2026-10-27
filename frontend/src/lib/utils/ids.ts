// Identificadores de nodo: `!xxxxxxxx` (12.1).

const NODE_ID = /^!([0-9a-f]{8})$/i;

export function isNodeId(value: string | null | undefined): value is string {
	return typeof value === 'string' && NODE_ID.test(value);
}

/** Número de nodo (32 bits sin signo) para `feature-state` de MapLibre. */
export function nodeNum(id: string): number {
	const m = NODE_ID.exec(id);
	return m ? parseInt(m[1], 16) : NaN;
}

export function normalizeNodeId(value: string): string | null {
	const v = value.trim().toLowerCase();
	if (NODE_ID.test(v)) return v;
	if (/^[0-9a-f]{8}$/.test(v)) return `!${v}`;
	return null;
}

/** Últimos 4 dígitos: nombre de respaldo cuando el nodo no informó nombres. */
export function shortFromId(id: string): string {
	return id.replace(/^!/, '').slice(-4);
}

export function nodeHref(id: string): string {
	return `/n/${id}`;
}
