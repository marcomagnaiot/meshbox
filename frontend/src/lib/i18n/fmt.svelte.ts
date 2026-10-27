// Formatos ligados al contexto actual (idioma elegido, zona horaria del sitio y hora del
// servidor). Usados dentro de plantillas, se recalculan solos cuando cambia el contexto.
import { clock } from '$lib/stores/clock.svelte';
import { site } from '$lib/stores/site.svelte';
import * as f from './format';
import { i18n } from './locale.svelte';

export function formatContext(): f.FormatContext {
	return { locale: i18n.locale, timeZone: site.timezone, now: clock.now };
}

export const fmt = {
	time: (ts: number, seconds = false) => f.formatTime(ts, formatContext(), seconds),
	date: (ts: number) => f.formatDate(ts, formatContext()),
	dateTime: (ts: number) => f.formatDateTime(ts, formatContext()),
	day: (ts: number) => f.formatDayLabel(ts, formatContext()),
	dayKey: (ts: number) => f.dayKey(ts, site.timezone),
	relative: (ts: number | null | undefined, style: Intl.RelativeTimeFormatStyle = 'short') =>
		f.formatRelative(ts, formatContext(), style),
	number: (v: number | null | undefined, max = 1, min = 0) =>
		f.formatNumber(v, { locale: i18n.locale }, max, min),
	percent: (v: number | null | undefined, max = 1) =>
		f.formatPercent(v, { locale: i18n.locale }, max),
	unit: (v: number | null | undefined, unit: string, max = 1) =>
		f.formatUnit(v, unit, { locale: i18n.locale }, max),
	duration: (s: number | null | undefined) => f.formatDuration(s, { locale: i18n.locale }),
	distance: (m: number | null | undefined) => f.formatDistance(m, { locale: i18n.locale }),
	bytes: (b: number | null | undefined) => f.formatBytes(b, { locale: i18n.locale }),
	db: (v: number | null | undefined) =>
		v === null || v === undefined ? '—' : `${f.formatNumber(v, { locale: i18n.locale }, 1)} dB`,
	dbm: (v: number | null | undefined) =>
		v === null || v === undefined ? '—' : `${f.formatNumber(v, { locale: i18n.locale }, 0)} dBm`
};
