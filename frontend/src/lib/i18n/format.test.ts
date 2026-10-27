import { describe, expect, it } from 'vitest';
import {
	dayKey,
	formatDayLabel,
	formatDistance,
	formatDuration,
	formatNumber,
	formatPercent,
	formatRelative,
	formatTime,
	type FormatContext
} from './format';

// 20/10/2026 13:00:00 UTC = 10:00 en Buenos Aires (UTC−3, sin horario de verano).
const NOW = Date.UTC(2026, 9, 20, 13, 0, 0) / 1000;
const es: FormatContext = { locale: 'es', timeZone: 'America/Argentina/Buenos_Aires', now: NOW };
const en: FormatContext = { ...es, locale: 'en' };

describe('hora en la zona horaria del sitio (16.7)', () => {
	it('formatea en la zona del sitio y no en la del equipo', () => {
		expect(formatTime(NOW, es)).toBe('10:00');
		expect(formatTime(NOW, { ...es, timeZone: 'UTC' })).toBe('13:00');
	});

	it('inglés usa su propio formato', () => {
		expect(formatTime(NOW, en)).toMatch(/10:00\s?AM/);
	});

	it('clave de día según la zona del sitio (pasada la medianoche UTC sigue siendo el día anterior)', () => {
		const lateNight = Date.UTC(2026, 9, 21, 2, 30) / 1000; // 23:30 del 20 en Buenos Aires
		expect(dayKey(lateNight, es.timeZone)).toBe('2026-10-20');
		expect(dayKey(lateNight, 'UTC')).toBe('2026-10-21');
	});
});

describe('"escuchado hace…"', () => {
	it.each([
		[10, 'ahora'],
		[12 * 60, 'hace 12 min'],
		[3 * 3600, 'hace 3 h'],
		[86400, 'ayer'],
		[2 * 86400, 'anteayer'],
		[3 * 86400, 'hace 3 d']
	])('hace %i s → %s', (age, text) => {
		expect(formatRelative(NOW - age, es).replace(/\u00a0/g, ' ')).toBe(text);
	});

	it('en inglés', () => {
		expect(formatRelative(NOW - 12 * 60, en)).toBe('12 min. ago');
	});

	it('sin dato', () => {
		expect(formatRelative(null, es)).toBe('—');
	});
});

describe('separadores de día del chat', () => {
	it('hoy y ayer con mayúscula inicial', () => {
		expect(formatDayLabel(NOW - 3600, es)).toBe('Hoy');
		expect(formatDayLabel(NOW - 86400, es)).toBe('Ayer');
		expect(formatDayLabel(NOW - 3600, en)).toBe('Today');
	});

	it('más atrás, día de la semana y fecha', () => {
		expect(formatDayLabel(NOW - 3 * 86400, es)).toBe('Sábado, 17 de octubre');
	});
});

describe('números', () => {
	it('separador decimal según el idioma', () => {
		expect(formatNumber(7.45, es, 1)).toBe('7,5');
		expect(formatNumber(7.45, en, 1)).toBe('7.5');
		expect(formatNumber(null, es)).toBe('—');
	});

	it('porcentaje desde 0-100', () => {
		expect(formatPercent(7.4, es).replace(/\u00a0/g, ' ')).toBe('7,4 %');
		expect(formatPercent(7.4, en)).toBe('7.4%');
	});

	it('duraciones y distancias compactas', () => {
		expect(formatDuration(3 * 86400 + 4 * 3600, es)).toMatch(/^3\s?d 4\s?h$/);
		expect(formatDuration(45, es)).toMatch(/^45\s?s$/);
		expect(formatDistance(850, es).replace(/\u00a0/g, ' ')).toBe('850 m');
		expect(formatDistance(2300, es).replace(/\u00a0/g, ' ')).toBe('2,3 km');
	});
});
