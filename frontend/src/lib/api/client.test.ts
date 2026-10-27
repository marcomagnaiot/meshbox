import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import {
	api,
	ApiError,
	apiHooks,
	buildUrl,
	NetworkError,
	parseRetryAfter,
	request
} from './client';

function respond(status: number, body: unknown, headers: Record<string, string> = {}) {
	return new Response(body === undefined ? null : JSON.stringify(body), {
		status,
		headers: { 'content-type': 'application/json', ...headers }
	});
}

/** Espera que la promesa falle y devuelve el error. */
async function failure(p: Promise<unknown>): Promise<ApiError> {
	try {
		await p;
	} catch (e) {
		return e as ApiError;
	}
	throw new Error('se esperaba un error');
}

describe('cliente HTTP (12.1)', () => {
	const fetchMock = vi.fn();

	beforeEach(() => {
		fetchMock.mockReset();
		vi.stubGlobal('fetch', fetchMock);
		apiHooks.onUnauthorized = undefined;
		apiHooks.csrfToken = undefined;
	});

	afterEach(() => {
		vi.unstubAllGlobals();
		vi.useRealTimers();
	});

	it('devuelve el JSON y arma la consulta sin valores vacíos', async () => {
		fetchMock.mockResolvedValueOnce(respond(200, { ok: 1 }));
		await expect(api.get('/api/v1/x', { a: 1, b: null, c: '', d: 'z' })).resolves.toEqual({
			ok: 1
		});
		expect(fetchMock.mock.calls[0][0]).toBe('/api/v1/x?a=1&d=z');
		expect(buildUrl('/p?x=1', { y: 2 })).toBe('/p?x=1&y=2');
	});

	it('interpreta errores RFC 9457 con errores por campo', async () => {
		fetchMock.mockResolvedValueOnce(
			new Response(
				JSON.stringify({
					type: 'about:blank',
					title: 'Datos no válidos',
					status: 422,
					detail: 'Revisar los campos indicados',
					errors: [{ loc: ['body', 'password'], msg: 'muy corta', type: 'too_short' }]
				}),
				{ status: 422, headers: { 'content-type': 'application/problem+json' } }
			)
		);
		const err = await failure(request('/api/v1/admin/x', { method: 'POST', body: {} }));
		expect(err).toBeInstanceOf(ApiError);
		expect(err.status).toBe(422);
		expect(err.message).toBe('Revisar los campos indicados');
		expect(err.fieldErrors).toEqual({ password: 'muy corta' });
	});

	it('401 en el panel avisa para volver al inicio de sesión (salvo en el propio login)', async () => {
		const hook = vi.fn();
		apiHooks.onUnauthorized = hook;
		fetchMock.mockImplementation(async () =>
			respond(401, { title: 'No autenticado', status: 401 })
		);
		await expect(api.get('/api/v1/admin/auth/me')).rejects.toBeInstanceOf(ApiError);
		expect(hook).toHaveBeenCalledWith('/api/v1/admin/auth/me');
		hook.mockClear();
		await expect(api.post('/api/v1/admin/auth/login', {})).rejects.toBeInstanceOf(ApiError);
		await expect(api.get('/api/v1/nodes')).rejects.toBeInstanceOf(ApiError);
		expect(hook).not.toHaveBeenCalled();
	});

	it('manda X-CSRF-Token solo en las peticiones que modifican', async () => {
		apiHooks.csrfToken = () => 'tok123';
		fetchMock.mockImplementation(async () => respond(200, {}));
		await api.get('/api/v1/admin/auth/me');
		await api.post('/api/v1/admin/auth/logout');
		const getHeaders = fetchMock.mock.calls[0][1].headers;
		const postHeaders = fetchMock.mock.calls[1][1].headers;
		expect(getHeaders['X-CSRF-Token']).toBeUndefined();
		expect(postHeaders['X-CSRF-Token']).toBe('tok123');
		expect(fetchMock.mock.calls[1][1].credentials).toBe('same-origin');
	});

	it('429: reintenta una vez si Retry-After es corto (GET)', async () => {
		vi.useFakeTimers();
		fetchMock
			.mockResolvedValueOnce(
				respond(429, { title: 'Demasiadas peticiones', status: 429 }, { 'retry-after': '2' })
			)
			.mockResolvedValueOnce(respond(200, { ok: true }));
		const p = api.get('/api/v1/site');
		await vi.advanceTimersByTimeAsync(2000);
		await expect(p).resolves.toEqual({ ok: true });
		expect(fetchMock).toHaveBeenCalledTimes(2);
	});

	it('429 con espera larga o en POST: error con retryAfter', async () => {
		fetchMock.mockImplementation(async () =>
			respond(429, { title: 'Demasiados intentos', status: 429 }, { 'retry-after': '120' })
		);
		const err = await failure(api.get('/api/v1/site'));
		expect(err).toBeInstanceOf(ApiError);
		expect(err.retryAfter).toBe(120);
		const err2 = await failure(api.post('/api/v1/admin/auth/login', {}));
		expect(err2.retryAfter).toBe(120);
		expect(fetchMock).toHaveBeenCalledTimes(2);
	});

	it('Retry-After como fecha HTTP', () => {
		const now = Date.UTC(2026, 9, 20, 12, 0, 0);
		expect(parseRetryAfter('Tue, 20 Oct 2026 12:00:30 GMT', now)).toBe(30);
		expect(parseRetryAfter('15')).toBe(15);
		expect(parseRetryAfter(null)).toBeNull();
		expect(parseRetryAfter('cualquier cosa')).toBeNull();
	});

	it('sin red: NetworkError', async () => {
		fetchMock.mockRejectedValueOnce(new TypeError('Failed to fetch'));
		await expect(api.get('/api/v1/site')).rejects.toBeInstanceOf(NetworkError);
	});

	it('204 sin cuerpo', async () => {
		fetchMock.mockResolvedValueOnce(new Response(null, { status: 204 }));
		await expect(api.del('/api/v1/push/subscriptions', {})).resolves.toBeUndefined();
	});
});
