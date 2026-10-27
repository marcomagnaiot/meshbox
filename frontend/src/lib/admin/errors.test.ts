import { describe, expect, it } from 'vitest';
import { ApiError, NetworkError } from '$lib/api/client';
import { m } from '$lib/paraglide/messages';
import { fieldPath, isSharedModeError, problemCode, problemFields, problemText } from './errors';

const problem = (status: number, extra: Record<string, unknown> = {}) =>
	new ApiError({ title: 'Error', status, ...extra });

describe('errores RFC 9457 del panel', () => {
	it('usa el detail del servidor', () => {
		expect(problemText(problem(409, { detail: 'Ya existe' }))).toBe('Ya existe');
	});

	it('reconoce el modo compartido por código (409)', () => {
		const err = problem(409, { detail: 'x', code: 'shared_mode' });
		expect(problemCode(err)).toBe('shared_mode');
		expect(isSharedModeError(err)).toBe(true);
		expect(isSharedModeError(problem(409, { code: 'not_allowed_in_shared_mode' }))).toBe(true);
		expect(isSharedModeError(problem(409, { code: 'otro' }))).toBe(false);
		expect(problemText(err)).toBe(m.adm_shared_blocked());
	});

	it('429 con la espera de Retry-After', () => {
		const err = new ApiError({ title: 'Too Many Requests', status: 429 }, 30);
		expect(problemText(err)).toBe(m.adm_rate_limited_wait({ seconds: 30 }));
	});

	it('422: primer error con la ruta del campo', () => {
		const err = problem(422, {
			detail: 'Datos no válidos',
			errors: [
				{ loc: ['body', 'params', 'patterns', 0], msg: 'muy corto' },
				{ loc: ['body', 'name'], msg: 'obligatorio' }
			]
		});
		expect(problemText(err)).toBe('Datos no válidos: params.patterns.0 — muy corto');
		expect(problemFields(err)).toEqual({ 'params.patterns.0': 'muy corto', name: 'obligatorio' });
	});

	it('sin red', () => {
		expect(problemText(new NetworkError())).toBe(m.error_network());
	});

	it('fieldPath quita body, query y path', () => {
		expect(fieldPath(['query', 'since'])).toBe('since');
		expect(fieldPath(['params', 'x'])).toBe('params.x');
	});
});
