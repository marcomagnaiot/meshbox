import { describe, expect, it } from 'vitest';
import { absolute, wantedBase } from './style';

describe('absolute', () => {
	it('conserva las llaves de la plantilla de teselas', () => {
		const url = absolute('/tiles/v/{z}/{x}/{y}.mvt?v=1792502981');
		expect(url).toMatch(/\/tiles\/v\/\{z\}\/\{x\}\/\{y\}\.mvt\?v=1792502981$/);
		expect(url).not.toContain('%7B');
	});

	it('deja igual una URL absoluta', () => {
		expect(absolute('https://tiles.example/{z}/{x}/{y}.mvt')).toBe(
			'https://tiles.example/{z}/{x}/{y}.mvt'
		);
	});

	it('agrega la barra a una ruta sin ella', () => {
		expect(absolute('tiles/v/{z}/{x}/{y}.mvt')).toMatch(/\/tiles\/v\/\{z\}\/\{x\}\/\{y\}\.mvt$/);
	});
});

describe('wantedBase', () => {
	it('sin elección del visitante usa la capa configurada en el sitio', () => {
		expect(wantedBase(null, 'light')).toBe('light');
		expect(wantedBase(null, 'dark')).toBe('dark');
		expect(wantedBase(null, 'satellite')).toBe('satellite');
	});

	it('la elección del visitante gana', () => {
		expect(wantedBase('dark', 'light')).toBe('dark');
		expect(wantedBase('satellite', 'light')).toBe('satellite');
	});
});
