import { describe, expect, it } from 'vitest';
import { batteryLevel, classify, isPowered, signalBars, snrClass } from './status';

const T = { active_s: 3600, recent_s: 7200, late_s: 86400 };
const now = 1_800_000_000;

describe('classify (17.3)', () => {
	it.each([
		[0, 'active'],
		[3599, 'active'],
		[3600, 'recent'],
		[7199, 'recent'],
		[7200, 'late'],
		[86399, 'late'],
		[86400, 'inactive'],
		[10 * 86400, 'inactive']
	])('hace %i s → %s', (age, expected) => {
		expect(classify(now - age, now, T)).toBe(expected);
	});

	it('usa los umbrales configurados en el panel', () => {
		const custom = { active_s: 600, recent_s: 1200, late_s: 3600 };
		expect(classify(now - 900, now, custom)).toBe('recent');
		expect(classify(now - 900, now, T)).toBe('active');
	});

	it('sin dato es inactivo', () => {
		expect(classify(null, now, T)).toBe('inactive');
		expect(classify(undefined, now, T)).toBe('inactive');
		expect(classify(Number.NaN, now, T)).toBe('inactive');
	});

	it('un reloj del equipo adelantado no da estados raros (escuchado "en el futuro")', () => {
		expect(classify(now + 30, now, T)).toBe('active');
	});
});

describe('batería y señal', () => {
	it('101 es alimentación externa', () => {
		expect(isPowered(101)).toBe(true);
		expect(isPowered(100)).toBe(false);
		expect(isPowered(null, true)).toBe(true);
		expect(batteryLevel(101)).toBe('powered');
		expect(batteryLevel(null)).toBe('unknown');
		expect(batteryLevel(10)).toBe('critical');
		expect(batteryLevel(30)).toBe('low');
		expect(batteryLevel(60)).toBe('medium');
		expect(batteryLevel(90)).toBe('high');
	});

	it('clases de SNR de los enlaces (16.5)', () => {
		expect(snrClass(5)).toBe('good');
		expect(snrClass(4.99)).toBe('fair');
		expect(snrClass(0)).toBe('fair');
		expect(snrClass(-0.25)).toBe('poor');
		expect(snrClass(null)).toBe('unknown');
	});

	it('barras de señal por SNR o, sin SNR, por RSSI', () => {
		expect(signalBars(10)).toBe(4);
		expect(signalBars(3)).toBe(3);
		expect(signalBars(-2)).toBe(2);
		expect(signalBars(-12)).toBe(1);
		expect(signalBars(null, -85)).toBe(4);
		expect(signalBars(null, -120)).toBe(1);
		expect(signalBars(null, null)).toBe(0);
	});
});
