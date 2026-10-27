// Cliente HTTP de la API (sección 12.1): JSON, errores RFC 9457 (`application/problem+json`),
// 401 → inicio de sesión del panel, 429 con `Retry-After` y cabecera `X-CSRF-Token` en toda
// petición que modifica.

export interface ProblemFieldError {
	loc: (string | number)[];
	msg: string;
	type?: string;
}

export interface ProblemDetails {
	type?: string;
	title: string;
	status: number;
	detail?: string;
	instance?: string;
	errors?: ProblemFieldError[];
	[key: string]: unknown;
}

export class ApiError extends Error {
	readonly status: number;
	readonly problem: ProblemDetails;
	/** Segundos a esperar (cabecera `Retry-After`), si vino. */
	readonly retryAfter: number | null;

	constructor(problem: ProblemDetails, retryAfter: number | null = null) {
		super(problem.detail || problem.title);
		this.name = 'ApiError';
		this.status = problem.status;
		this.problem = problem;
		this.retryAfter = retryAfter;
	}

	/** Errores por campo (`errors[].loc` → último segmento) para los formularios. */
	get fieldErrors(): Record<string, string> {
		const out: Record<string, string> = {};
		for (const e of this.problem.errors ?? []) {
			const key = String(e.loc[e.loc.length - 1] ?? '');
			if (key && !out[key]) out[key] = e.msg;
		}
		return out;
	}
}

/** Sin red o el servidor no respondió. */
export class NetworkError extends Error {
	constructor(cause?: unknown) {
		super('network');
		this.name = 'NetworkError';
		this.cause = cause;
	}
}

export interface ApiHooks {
	/** 401 en una ruta de administración (salvo el propio inicio de sesión). */
	onUnauthorized?: (path: string) => void;
	/** Token CSRF de la sesión del panel. */
	csrfToken?: () => string | null;
}

export const apiHooks: ApiHooks = {};

export type QueryValue = string | number | boolean | null | undefined;

export interface RequestOptions {
	method?: 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE';
	body?: unknown;
	/** Cuerpo crudo (archivos): se envía tal cual, sin JSON. */
	raw?: Blob | ArrayBuffer;
	/** `Content-Type` del cuerpo crudo (por defecto, el del archivo o octet-stream). */
	contentType?: string;
	query?: Record<string, QueryValue>;
	signal?: AbortSignal;
	headers?: Record<string, string>;
	/** Reintentar una vez tras un 429 si `Retry-After` es corto (por defecto, solo en GET). */
	retry429?: boolean;
}

const UNSAFE = new Set(['POST', 'PUT', 'PATCH', 'DELETE']);
const MAX_AUTO_WAIT_S = 5;

/** `Retry-After` en segundos o como fecha HTTP. */
export function parseRetryAfter(value: string | null, now = Date.now()): number | null {
	if (!value) return null;
	const trimmed = value.trim();
	if (/^\d+$/.test(trimmed)) return Number(trimmed);
	const date = Date.parse(trimmed);
	if (Number.isNaN(date)) return null;
	return Math.max(0, Math.ceil((date - now) / 1000));
}

export function buildUrl(path: string, query?: Record<string, QueryValue>): string {
	if (!query) return path;
	const params = new URLSearchParams();
	for (const [k, v] of Object.entries(query)) {
		if (v === undefined || v === null || v === '') continue;
		params.set(k, String(v));
	}
	const qs = params.toString();
	return qs ? `${path}${path.includes('?') ? '&' : '?'}${qs}` : path;
}

async function toProblem(res: Response): Promise<ProblemDetails> {
	const type = res.headers.get('content-type') ?? '';
	if (type.includes('json')) {
		try {
			const body = (await res.json()) as Partial<ProblemDetails>;
			return {
				...body,
				title: body.title ?? res.statusText ?? 'Error',
				status: body.status ?? res.status
			};
		} catch {
			// cuerpo inválido: se arma un problema genérico
		}
	}
	return { title: res.statusText || 'Error', status: res.status };
}

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

/** Respuesta cruda (descargas): el llamador decide cómo leerla. */
async function fetchOk(path: string, opts: RequestOptions): Promise<Response> {
	const method = opts.method ?? 'GET';
	const headers: Record<string, string> = { Accept: 'application/json', ...opts.headers };
	let body: BodyInit | undefined;
	if (opts.raw !== undefined) {
		headers['Content-Type'] =
			opts.contentType || (opts.raw instanceof Blob && opts.raw.type) || 'application/octet-stream';
		body = opts.raw;
	} else if (opts.body !== undefined) {
		headers['Content-Type'] = 'application/json';
		body = JSON.stringify(opts.body);
	}
	if (UNSAFE.has(method)) {
		const token = apiHooks.csrfToken?.();
		if (token) headers['X-CSRF-Token'] = token;
	}
	const url = buildUrl(path, opts.query);
	const retry429 = opts.retry429 ?? method === 'GET';

	for (let attempt = 0; ; attempt++) {
		let res: Response;
		try {
			res = await fetch(url, {
				method,
				headers,
				body,
				signal: opts.signal,
				credentials: 'same-origin'
			});
		} catch (err) {
			if (err instanceof DOMException && err.name === 'AbortError') throw err;
			throw new NetworkError(err);
		}
		if (res.ok) return res;

		const retryAfter = parseRetryAfter(res.headers.get('retry-after'));
		if (
			res.status === 429 &&
			retry429 &&
			attempt === 0 &&
			retryAfter !== null &&
			retryAfter <= MAX_AUTO_WAIT_S
		) {
			await sleep(retryAfter * 1000);
			continue;
		}

		const problem = await toProblem(res);
		if (
			res.status === 401 &&
			path.startsWith('/api/v1/admin') &&
			!path.startsWith('/api/v1/admin/auth/login')
		) {
			apiHooks.onUnauthorized?.(path);
		}
		throw new ApiError(problem, retryAfter);
	}
}

/** Nombre de archivo de `Content-Disposition` (attachment; filename="…"). */
export function filenameFrom(res: Response, fallback: string): string {
	const cd = res.headers.get('content-disposition') ?? '';
	const m = /filename\*?=(?:UTF-8'')?"?([^";]+)"?/i.exec(cd);
	return m ? decodeURIComponent(m[1]) : fallback;
}

/** Pide un archivo (con CSRF si modifica) y lo devuelve como Blob con su nombre. */
export async function requestBlob(
	path: string,
	opts: RequestOptions & { filename?: string } = {}
): Promise<{ blob: Blob; filename: string }> {
	const res = await fetchOk(path, opts);
	return { blob: await res.blob(), filename: filenameFrom(res, opts.filename ?? 'descarga') };
}

export async function request<T>(path: string, opts: RequestOptions = {}): Promise<T> {
	const res = await fetchOk(path, opts);
	if (res.status === 204 || res.headers.get('content-length') === '0') {
		return undefined as T;
	}
	const type = res.headers.get('content-type') ?? '';
	return (type.includes('json') ? await res.json() : await res.text()) as T;
}

export const api = {
	get: <T>(path: string, query?: Record<string, QueryValue>, signal?: AbortSignal) =>
		request<T>(path, { query, signal }),
	post: <T>(path: string, body?: unknown) => request<T>(path, { method: 'POST', body }),
	put: <T>(path: string, body?: unknown) => request<T>(path, { method: 'PUT', body }),
	patch: <T>(path: string, body?: unknown) => request<T>(path, { method: 'PATCH', body }),
	del: <T>(path: string, body?: unknown) => request<T>(path, { method: 'DELETE', body })
};
