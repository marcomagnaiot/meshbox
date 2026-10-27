// Errores de la API (RFC 9457) para el panel: texto para mostrar, código (`code`) y errores
// por campo con su ruta completa (`params.patterns`), para marcar el campo exacto.
import { ApiError, NetworkError } from '$lib/api/client';
import { m } from '$lib/paraglide/messages';

/** Códigos que indican que la acción no existe en un equipo compartido (ADR 0004). */
export const SHARED_CODES = new Set(['shared_mode', 'not_allowed_in_shared_mode']);

export function problemCode(err: unknown): string | null {
	if (err instanceof ApiError) {
		const code = err.problem.code;
		return typeof code === 'string' ? code : null;
	}
	return null;
}

export function isSharedModeError(err: unknown): boolean {
	return err instanceof ApiError && err.status === 409 && SHARED_CODES.has(problemCode(err) ?? '');
}

/** Texto del error: `detail` del servidor, o un mensaje propio por estado. */
export function problemText(err: unknown): string {
	if (err instanceof NetworkError) return m.error_network();
	if (err instanceof ApiError) {
		if (isSharedModeError(err)) return m.adm_shared_blocked();
		if (err.status === 429) {
			return err.retryAfter
				? m.adm_rate_limited_wait({ seconds: err.retryAfter })
				: m.adm_rate_limited();
		}
		if (err.status === 403) return err.problem.detail || m.adm_forbidden();
		if (err.status === 422 && err.problem.errors?.length) {
			const first = err.problem.errors[0];
			const field = fieldPath(first.loc);
			return field
				? `${err.problem.detail ?? err.problem.title}: ${field} — ${first.msg}`
				: first.msg;
		}
		return err.problem.detail || err.problem.title || m.error_generic();
	}
	if (err instanceof Error) return err.message;
	return m.error_generic();
}

/** Ruta de un error de validación sin el prefijo `body` (ej. `params.patterns.0`). */
export function fieldPath(loc: (string | number)[]): string {
	const parts = loc[0] === 'body' || loc[0] === 'query' || loc[0] === 'path' ? loc.slice(1) : loc;
	return parts.map(String).join('.');
}

/** Errores por campo (ruta completa → mensaje) de un 422. */
export function problemFields(err: unknown): Record<string, string> {
	const out: Record<string, string> = {};
	if (!(err instanceof ApiError)) return out;
	for (const e of err.problem.errors ?? []) {
		const path = fieldPath(e.loc);
		if (path && !out[path]) out[path] = e.msg;
	}
	return out;
}
