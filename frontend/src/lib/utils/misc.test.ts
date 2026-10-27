import { describe, expect, it, vi } from 'vitest';
import { FpsJudge } from '$lib/map/fps';
import { base64UrlToBytes } from '$lib/stores/push.svelte';
import { contrastRatio, hexToRgb, oklchToRgb, onColor, parseOklch, rgbToHex } from './color';
import { isNodeId, nodeNum, normalizeNodeId } from './ids';
import { EMPTY_FILTER, filterNodes, sortNodes } from './nodes';
import { fold, mapLabel, matches, truncate } from './text';
import { throttle } from './timing';
import type { Node } from '$lib/api/types';

describe('colores OKLCH → sRGB (tokens a MapLibre)', () => {
	it('convierte los tokens del plan', () => {
		expect(rgbToHex(oklchToRgb(0.78, 0.17, 150))).toBe('#56d57b');
		expect(rgbToHex(oklchToRgb(1, 0, 0))).toBe('#ffffff');
		expect(parseOklch('oklch(22% 0.02 255 / 0.55)')?.alpha).toBe(0.55);
		expect(parseOklch('rojo')).toBeNull();
	});

	it('texto sobre el acento configurable con el mejor contraste', () => {
		expect(onColor('#22b8cf')).toBe('#0b1118');
		expect(onColor('#1a237e')).toBe('#ffffff');
		const ratio = contrastRatio(hexToRgb('#ffffff')!, hexToRgb('#000000')!);
		expect(ratio).toBeCloseTo(21, 0);
	});
});

describe('identificadores de nodo', () => {
	it('!xxxxxxxx', () => {
		expect(isNodeId('!c05b1d28')).toBe(true);
		expect(isNodeId('c05b1d28')).toBe(false);
		expect(nodeNum('!c05b1d28')).toBe(0xc05b1d28);
		expect(normalizeNodeId('C05B1D28')).toBe('!c05b1d28');
		expect(normalizeNodeId('hola')).toBeNull();
	});
});

describe('texto', () => {
	it('búsqueda sin acentos y por palabras', () => {
		expect(fold('Ñandú Ópalo')).toBe('nandu opalo');
		expect(matches('nandu op', 'Ñandú', 'Ópalo')).toBe(true);
		expect(matches('xyz', 'Ñandú')).toBe(false);
		expect(matches('', 'x')).toBe(true);
	});

	it('etiquetas del mapa y recortes', () => {
		expect(mapLabel('🛰️ SAT', 'x')).toBe('SAT');
		expect(mapLabel(null, 'abcd')).toBe('abcd');
		expect(truncate('abcdef', 4)).toBe('abc…');
		expect(truncate('ab', 4)).toBe('ab');
	});
});

describe('filtros y orden de la lista', () => {
	const now = 1000_000;
	const T = { active_s: 3600, recent_s: 7200, late_s: 86400 };
	const n = (id: string, extra: Partial<Node>): Node =>
		({ id, short_name: null, long_name: id, role: 'CLIENT', lat: 1, lon: 1, battery: null, powered: false,
			voltage: null, channel_utilization: null, env: null, last_heard: now, snr: null, hops: null, is_infra: false,
			is_fixed: false, ...extra }) as Node; // prettier-ignore
	const list = [
		n('b', { battery: 20, snr: 3, hops: 2, last_heard: now - 100 }),
		n('a', { battery: 101, powered: true, snr: 9, hops: 0, is_infra: true, role: 'ROUTER' }),
		n('c', { battery: null, snr: null, hops: 5, last_heard: now - 5 * 86400 })
	];

	it('filtra por infraestructura, rol, telemetría e inactivos', () => {
		expect(filterNodes(list, EMPTY_FILTER, now, T).map((x) => x.id)).toEqual(['b', 'a']);
		expect(
			filterNodes(list, { ...EMPTY_FILTER, onlyInfra: true }, now, T).map((x) => x.id)
		).toEqual(['a']);
		expect(filterNodes(list, { ...EMPTY_FILTER, role: 'ROUTER' }, now, T)).toHaveLength(1);
		expect(
			filterNodes(list, { ...EMPTY_FILTER, withTelemetry: true, showInactive: true }, now, T)
		).toHaveLength(2);
		expect(
			filterNodes(list, { ...EMPTY_FILTER, statuses: ['inactive'] }, now, T).map((x) => x.id)
		).toEqual(['c']);
	});

	it('ordena por batería (alimentados primero), SNR, saltos y nombre', () => {
		expect(sortNodes(list, 'battery', now, T).map((x) => x.id)).toEqual(['a', 'b', 'c']);
		expect(sortNodes(list, 'snr', now, T).map((x) => x.id)).toEqual(['a', 'b', 'c']);
		expect(sortNodes(list, 'hops', now, T).map((x) => x.id)).toEqual(['a', 'b', 'c']);
		expect(sortNodes(list, 'name', now, T).map((x) => x.id)).toEqual(['a', 'b', 'c']);
		expect(sortNodes(list, 'last_heard', now, T).map((x) => x.id)).toEqual(['a', 'b', 'c']);
	});
});

describe('agrupado cada 500 ms (16.5)', () => {
	it('llama una vez al principio y una al final del intervalo con lo último', () => {
		vi.useFakeTimers();
		const fn = vi.fn();
		const t = throttle(fn, 500);
		t(1);
		t(2);
		t(3);
		expect(fn).toHaveBeenCalledTimes(1);
		expect(fn).toHaveBeenLastCalledWith(1);
		vi.advanceTimersByTime(500);
		expect(fn).toHaveBeenCalledTimes(2);
		expect(fn).toHaveBeenLastCalledWith(3);
		vi.useRealTimers();
	});
});

describe('sugerencia de modo sólido (16.1.9)', () => {
	it('solo con menos de 40 cuadros/s sostenidos durante 3 s', () => {
		const j = new FpsJudge();
		expect(j.addWindow(30)).toBe(false);
		expect(j.addWindow(35)).toBe(false);
		expect(j.addWindow(55)).toBe(false); // se corta la racha
		expect(j.addWindow(30)).toBe(false);
		expect(j.addWindow(30)).toBe(false);
		expect(j.addWindow(39)).toBe(true);
	});
});

describe('clave VAPID', () => {
	it('base64url → bytes', () => {
		expect([...base64UrlToBytes('AQID_-8')]).toEqual([1, 2, 3, 255, 239]);
	});
});
