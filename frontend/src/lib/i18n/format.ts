// Formatos con Intl según el idioma, siempre en la zona horaria del sitio (16.7).
// Funciones puras: reciben el contexto explícito (las pruebas fijan idioma, zona y "ahora").

export interface FormatContext {
	locale: string;
	timeZone: string;
	/** Ahora, en segundos Unix (hora del servidor corregida). */
	now: number;
}

const cache = new Map<string, Intl.DateTimeFormat | Intl.NumberFormat | Intl.RelativeTimeFormat>();

function dtf(
	locale: string,
	timeZone: string,
	opts: Intl.DateTimeFormatOptions
): Intl.DateTimeFormat {
	const key = `d|${locale}|${timeZone}|${JSON.stringify(opts)}`;
	let f = cache.get(key) as Intl.DateTimeFormat | undefined;
	if (!f) {
		try {
			f = new Intl.DateTimeFormat(locale, { ...opts, timeZone });
		} catch {
			// zona horaria desconocida para este navegador: se usa la local
			f = new Intl.DateTimeFormat(locale, opts);
		}
		cache.set(key, f);
	}
	return f;
}

function nf(locale: string, opts: Intl.NumberFormatOptions): Intl.NumberFormat {
	const key = `n|${locale}|${JSON.stringify(opts)}`;
	let f = cache.get(key) as Intl.NumberFormat | undefined;
	if (!f) {
		f = new Intl.NumberFormat(locale, opts);
		cache.set(key, f);
	}
	return f;
}

function rtf(locale: string, style: Intl.RelativeTimeFormatStyle): Intl.RelativeTimeFormat {
	const key = `r|${locale}|${style}`;
	let f = cache.get(key) as Intl.RelativeTimeFormat | undefined;
	if (!f) {
		f = new Intl.RelativeTimeFormat(locale, { numeric: 'auto', style });
		cache.set(key, f);
	}
	return f;
}

const capitalize = (s: string) => (s ? s[0].toLocaleUpperCase() + s.slice(1) : s);

export function formatTime(ts: number, ctx: FormatContext, seconds = false): string {
	return dtf(ctx.locale, ctx.timeZone, {
		hour: '2-digit',
		minute: '2-digit',
		...(seconds ? { second: '2-digit' } : {})
	}).format(ts * 1000);
}

export function formatDateTime(ts: number, ctx: FormatContext): string {
	return dtf(ctx.locale, ctx.timeZone, {
		day: 'numeric',
		month: 'short',
		year: 'numeric',
		hour: '2-digit',
		minute: '2-digit'
	}).format(ts * 1000);
}

export function formatDate(ts: number, ctx: FormatContext): string {
	return dtf(ctx.locale, ctx.timeZone, { day: 'numeric', month: 'short', year: 'numeric' }).format(
		ts * 1000
	);
}

/** Clave de día calendario en la zona del sitio (para separadores del chat). */
export function dayKey(ts: number, timeZone: string): string {
	const parts = dtf('en-CA', timeZone, {
		year: 'numeric',
		month: '2-digit',
		day: '2-digit'
	}).formatToParts(ts * 1000);
	const get = (t: string) => parts.find((p) => p.type === t)?.value ?? '';
	return `${get('year')}-${get('month')}-${get('day')}`;
}

/** "Hoy", "Ayer" o "lunes, 18 de octubre" (con año si no es el actual). */
export function formatDayLabel(ts: number, ctx: FormatContext): string {
	const day = dayKey(ts, ctx.timeZone);
	if (day === dayKey(ctx.now, ctx.timeZone)) {
		return capitalize(rtf(ctx.locale, 'long').format(0, 'day'));
	}
	if (day === dayKey(ctx.now - 86400, ctx.timeZone)) {
		return capitalize(rtf(ctx.locale, 'long').format(-1, 'day'));
	}
	const sameYear = day.slice(0, 4) === dayKey(ctx.now, ctx.timeZone).slice(0, 4);
	return capitalize(
		dtf(ctx.locale, ctx.timeZone, {
			weekday: 'long',
			day: 'numeric',
			month: 'long',
			...(sameYear ? {} : { year: 'numeric' })
		}).format(ts * 1000)
	);
}

/** "hace 12 min", "hace 3 h", "ayer"… (estilo corto por defecto). */
export function formatRelative(
	ts: number | null | undefined,
	ctx: FormatContext,
	style: Intl.RelativeTimeFormatStyle = 'short'
): string {
	if (ts === null || ts === undefined || !Number.isFinite(ts)) return '—';
	const diff = Math.round(ts - ctx.now);
	const abs = Math.abs(diff);
	const f = rtf(ctx.locale, style);
	if (abs < 45) return f.format(0, 'second');
	if (abs < 3600) return f.format(Math.round(diff / 60), 'minute');
	if (abs < 86400) return f.format(Math.round(diff / 3600), 'hour');
	if (abs < 30 * 86400) return f.format(Math.round(diff / 86400), 'day');
	if (abs < 365 * 86400) return f.format(Math.round(diff / (30 * 86400)), 'month');
	return f.format(Math.round(diff / (365 * 86400)), 'year');
}

export function formatNumber(
	value: number | null | undefined,
	ctx: Pick<FormatContext, 'locale'>,
	maxDigits = 1,
	minDigits = 0
): string {
	if (value === null || value === undefined || !Number.isFinite(value)) return '—';
	return nf(ctx.locale, {
		maximumFractionDigits: maxDigits,
		minimumFractionDigits: minDigits
	}).format(value);
}

/** Porcentaje a partir de un valor 0-100 ("7,4 %"). */
export function formatPercent(
	value: number | null | undefined,
	ctx: Pick<FormatContext, 'locale'>,
	maxDigits = 1
): string {
	if (value === null || value === undefined || !Number.isFinite(value)) return '—';
	return nf(ctx.locale, { style: 'percent', maximumFractionDigits: maxDigits }).format(value / 100);
}

/** Valor con unidad (`unit` de Intl: celsius, percent, meter, kilometer-per-hour…). */
export function formatUnit(
	value: number | null | undefined,
	unit: string,
	ctx: Pick<FormatContext, 'locale'>,
	maxDigits = 1
): string {
	if (value === null || value === undefined || !Number.isFinite(value)) return '—';
	return nf(ctx.locale, {
		style: 'unit',
		unit,
		unitDisplay: 'short',
		maximumFractionDigits: maxDigits
	}).format(value);
}

/** Duración compacta: "3 d 4 h", "5 h 12 min", "40 s". */
export function formatDuration(
	seconds: number | null | undefined,
	ctx: Pick<FormatContext, 'locale'>
): string {
	if (seconds === null || seconds === undefined || !Number.isFinite(seconds)) return '—';
	const s = Math.max(0, Math.round(seconds));
	const d = Math.floor(s / 86400);
	const h = Math.floor((s % 86400) / 3600);
	const m = Math.floor((s % 3600) / 60);
	const unit = (v: number, u: string) =>
		nf(ctx.locale, { style: 'unit', unit: u, unitDisplay: 'narrow' }).format(v);
	if (d > 0) return h > 0 ? `${unit(d, 'day')} ${unit(h, 'hour')}` : unit(d, 'day');
	if (h > 0) return m > 0 ? `${unit(h, 'hour')} ${unit(m, 'minute')}` : unit(h, 'hour');
	if (m > 0) return unit(m, 'minute');
	return unit(s, 'second');
}

/** Tamaño de archivo o memoria en múltiplos de 1024 ("3,4 MB", "512 kB"). */
export function formatBytes(
	bytes: number | null | undefined,
	ctx: Pick<FormatContext, 'locale'>
): string {
	if (bytes === null || bytes === undefined || !Number.isFinite(bytes)) return '—';
	const units = ['byte', 'kilobyte', 'megabyte', 'gigabyte', 'terabyte'];
	let v = Math.abs(bytes);
	let i = 0;
	while (v >= 1024 && i < units.length - 1) {
		v /= 1024;
		i++;
	}
	return formatUnit(Math.sign(bytes) * v, units[i], ctx, i > 0 && v < 10 ? 1 : 0);
}

export function formatDistance(
	meters: number | null | undefined,
	ctx: Pick<FormatContext, 'locale'>
): string {
	if (meters === null || meters === undefined || !Number.isFinite(meters)) return '—';
	if (meters < 1000) return formatUnit(Math.round(meters), 'meter', ctx, 0);
	return formatUnit(meters / 1000, 'kilometer', ctx, meters < 10000 ? 1 : 0);
}
