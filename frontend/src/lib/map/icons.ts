// Íconos de nodo dibujados en un lienzo (sin marcadores DOM): relleno según frescura, anillo
// grueso de infraestructura, anillo fino de nodo fijo y borde oscuro que los separa de
// cualquier fondo (la misma codificación que StatusGlyph).
import type { NodeStatus } from '$lib/api/types';
import type { MapColors } from './theme';

const PIXEL_RATIO = 2;
const FRACTION: Record<NodeStatus, number> = { active: 1, recent: 0.75, late: 0.5, inactive: 0 };

export interface IconImage {
	width: number;
	height: number;
	data: Uint8ClampedArray;
}

function canvas(size: number): CanvasRenderingContext2D | null {
	const c = document.createElement('canvas');
	c.width = c.height = size * PIXEL_RATIO;
	const ctx = c.getContext('2d');
	ctx?.scale(PIXEL_RATIO, PIXEL_RATIO);
	return ctx;
}

function toImage(ctx: CanvasRenderingContext2D, size: number): IconImage {
	const px = size * PIXEL_RATIO;
	const img = ctx.getImageData(0, 0, px, px);
	return { width: px, height: px, data: img.data };
}

/** `node-<estado>-<infra><fijo>`, por ejemplo `node-recent-10`. */
export function parseIconName(
	name: string
): { status: NodeStatus; infra: boolean; fixed: boolean } | null {
	const m = /^node-(active|recent|late|inactive)-([01])([01])$/.exec(name);
	if (!m) return null;
	return { status: m[1] as NodeStatus, infra: m[2] === '1', fixed: m[3] === '1' };
}

export function drawNodeIcon(
	colors: MapColors,
	status: NodeStatus,
	infra: boolean,
	fixed: boolean
): IconImage | null {
	const size = 30;
	const ctx = canvas(size);
	if (!ctx) return null;
	const c = size / 2;
	const r = 6.5;
	const fill = colors[status];
	const fraction = FRACTION[status];

	if (fixed) {
		ctx.beginPath();
		ctx.arc(c, c, infra ? 13 : 11, 0, Math.PI * 2);
		ctx.lineWidth = 3.5;
		ctx.strokeStyle = colors.outline;
		ctx.stroke();
		ctx.lineWidth = 1.5;
		ctx.strokeStyle = colors.text;
		ctx.stroke();
	}
	if (infra) {
		ctx.beginPath();
		ctx.arc(c, c, 10, 0, Math.PI * 2);
		ctx.lineWidth = 5;
		ctx.strokeStyle = colors.outline;
		ctx.stroke();
		ctx.lineWidth = 2.75;
		ctx.strokeStyle = colors.infra;
		ctx.stroke();
	}
	// Disco base oscuro (lo "vacío") con borde.
	ctx.beginPath();
	ctx.arc(c, c, r + 1.5, 0, Math.PI * 2);
	ctx.fillStyle = colors.outline;
	ctx.fill();
	// Relleno según frescura, desde las 12 en sentido horario.
	if (fraction > 0) {
		ctx.beginPath();
		if (fraction >= 1) {
			ctx.arc(c, c, r, 0, Math.PI * 2);
		} else {
			ctx.moveTo(c, c);
			ctx.arc(c, c, r, -Math.PI / 2, -Math.PI / 2 + fraction * Math.PI * 2);
			ctx.closePath();
		}
		ctx.fillStyle = fill;
		ctx.fill();
	}
	// Contorno del color de estado: el círculo se lee aunque esté vacío.
	ctx.beginPath();
	ctx.arc(c, c, r - 0.6, 0, Math.PI * 2);
	ctx.lineWidth = 1.6;
	ctx.strokeStyle = fill;
	ctx.stroke();
	return toImage(ctx, size);
}

/** Alfiler de punto de interés. */
export function drawWaypointIcon(colors: MapColors): IconImage | null {
	const size = 28;
	const ctx = canvas(size);
	if (!ctx) return null;
	ctx.beginPath();
	ctx.moveTo(14, 26);
	ctx.bezierCurveTo(14, 26, 5, 16, 5, 10.5);
	ctx.arc(14, 10.5, 9, Math.PI, 0);
	ctx.bezierCurveTo(23, 16, 14, 26, 14, 26);
	ctx.closePath();
	ctx.fillStyle = colors.accent;
	ctx.fill();
	ctx.lineWidth = 2;
	ctx.strokeStyle = colors.outline;
	ctx.stroke();
	ctx.beginPath();
	ctx.arc(14, 10.5, 3.5, 0, Math.PI * 2);
	ctx.fillStyle = colors.outline;
	ctx.fill();
	return toImage(ctx, size);
}

export const ICON_PIXEL_RATIO = PIXEL_RATIO;
