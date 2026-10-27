import { beforeEach, describe, expect, it } from 'vitest';
import type { Alert } from '$lib/api/types';
import { isSos, pickBanner } from './alerts.svelte';
import { PREFS_KEY, prefs } from './prefs.svelte';
import { filters, selection, toasts } from './ui.svelte';
import { sheetAnchorFor, viewFor } from './view';

const alert = (id: number, extra: Partial<Alert>): Alert => ({
	id,
	state: 'firing',
	severity: 'warning',
	kind: 'telemetry_threshold',
	node: null,
	title: 'Batería baja',
	body: null,
	ts: 100,
	...extra
});

describe('alerta destacada (banner SOS)', () => {
	it('la más grave primero y, a igual gravedad, la más reciente; nunca resueltas ni ocultadas', () => {
		const list = [
			alert(1, { severity: 'warning', ts: 300 }),
			alert(2, { severity: 'critical', ts: 100, kind: 'keyword', title: 'SOS' }),
			alert(3, { severity: 'critical', ts: 200 }),
			alert(4, { severity: 'critical', ts: 400, state: 'resolved' })
		];
		expect(pickBanner(list, new Set())?.id).toBe(3);
		expect(pickBanner(list, new Set([3]))?.id).toBe(2);
		expect(pickBanner([alert(9, { state: 'resolved' })], new Set())).toBeNull();
	});

	it('SOS: crítica, palabra clave o el texto SOS', () => {
		expect(isSos(alert(1, { severity: 'critical' }))).toBe(true);
		expect(isSos(alert(1, { kind: 'keyword' }))).toBe(true);
		expect(isSos(alert(1, { body: 'sos en la ruta' }))).toBe(true);
		expect(isSos(alert(1, {}))).toBe(false);
	});
});

describe('preferencias (localStorage, sin cookies)', () => {
	beforeEach(() => localStorage.clear());

	it('guarda tema, modo sólido, capas e idioma', () => {
		prefs.setTheme('light');
		prefs.setSolid(true);
		prefs.setLayer('links', false);
		const saved = JSON.parse(localStorage.getItem(PREFS_KEY) ?? '{}');
		expect(saved).toMatchObject({ theme: 'light', solid: true, layers: { links: false } });
		expect(document.documentElement.dataset.theme).toBe('light');
		expect(document.documentElement.hasAttribute('data-solid')).toBe(true);
		prefs.setSolid(false);
		prefs.setTheme('dark');
		expect(document.documentElement.hasAttribute('data-solid')).toBe(false);
	});
});

describe('filtros compartidos mapa/lista', () => {
	it('alternar chips, estados y limpiar conservando "inactivos"', () => {
		filters.applySiteDefault(true);
		filters.toggle('onlyInfra');
		filters.toggleStatus('late');
		expect(filters.active).toBe(2);
		filters.clear();
		expect(filters.active).toBe(0);
		expect(filters.value.showInactive).toBe(true);
		filters.applySiteDefault(false); // solo la primera vez
		expect(filters.value.showInactive).toBe(true);
	});
});

describe('selección y avisos', () => {
	it('cambiar de nodo limpia recorrido, cursor y traceroute', () => {
		selection.select('!00000001');
		selection.track = [{ ts: 1, lat: 1, lon: 1, alt: null, precision_m: null, speed_kmh: null }];
		selection.cursor = 0;
		selection.select('!00000002');
		expect(selection.track).toEqual([]);
		expect(selection.cursor).toBeNull();
	});

	it('los avisos se acumulan hasta 4 y se descartan', () => {
		for (let i = 0; i < 6; i++) toasts.show(`aviso ${i}`, { timeout: 0 });
		expect(toasts.list).toHaveLength(4);
		toasts.dismiss(toasts.list[0].id);
		expect(toasts.list).toHaveLength(3);
	});
});

describe('vistas públicas', () => {
	it('ruta → vista → anclaje del panel inferior', () => {
		expect(viewFor('/(public)')).toBe('home');
		expect(viewFor('/(public)/n/[id]')).toBe('node');
		expect(viewFor('/admin')).toBe('other');
		expect(sheetAnchorFor('home')).toBe('peek');
		expect(sheetAnchorFor('node')).toBe('half');
		expect(sheetAnchorFor('chat')).toBe('full');
	});
});
