// Tipos compartidos de los componentes del panel.
import type { Snippet } from 'svelte';

export interface ControlProps {
	id: string;
	describedby: string | undefined;
	invalid: boolean;
}

export interface Column<R> {
	key: string;
	label: string;
	/** Pista de la grilla: '120px', 'minmax(180px, 1fr)'. */
	width?: string;
	align?: 'start' | 'end' | 'center';
	cell?: Snippet<[R]>;
	text?: (row: R) => string | number | null | undefined;
	sort?: (a: R, b: R) => number;
	/** Etiqueta solo para lectores de pantalla (columna de íconos). */
	srLabel?: boolean;
}

export interface KV {
	label: string;
	value?: string | number | null;
	/** Contenido propio en vez del texto. */
	content?: Snippet;
	mono?: boolean;
}

export interface Option<V extends string | number = string> {
	value: V;
	label: string;
	disabled?: boolean;
	hint?: string;
}
