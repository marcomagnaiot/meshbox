import { describe, expect, it } from 'vitest';
import { contrastRatio, oklchToRgb, rgbToOklch } from './color';
import { nodeColor, nodeColorStyle } from './node-color';

describe('color de cada nodo (como la app de Meshtastic)', () => {
	it('usa los 24 bits bajos del número como rojo, verde y azul', () => {
		expect(nodeColor('!c05b1d28')?.rgb).toEqual([0x5b, 0x1d, 0x28]);
		expect(nodeColor('!c00dedcc')?.rgb).toEqual([0x0d, 0xed, 0xcc]);
		expect(nodeColor('!c05b1d28')?.css).toBe('rgb(91 29 40)');
	});

	it('texto negro o blanco, siempre con contraste suficiente', () => {
		expect(nodeColor('!c05b1d28')?.ink).toBe('#ffffff');
		expect(nodeColor('!c00dedcc')?.ink).toBe('#000000');
		for (const id of ['!00000000', '!00ffffff', '!00777777', '!00808080', '!12345678']) {
			const c = nodeColor(id);
			const ink: [number, number, number] = c?.ink === '#000000' ? [0, 0, 0] : [255, 255, 255];
			expect(contrastRatio(c!.rgb, ink)).toBeGreaterThanOrEqual(4.5);
		}
	});

	it('el tinte de la burbuja conserva el tono y modera la croma', () => {
		const c = nodeColor('!c00dedcc')!;
		expect(c.chroma).toBeLessThanOrEqual(0.11);
		expect(Math.abs(c.hue - rgbToOklch(c.rgb).h)).toBeLessThan(1);
		expect(nodeColorStyle('!c00dedcc')).toContain('--node:rgb(13 237 204)');
	});

	it('sin id válido no hay color', () => {
		expect(nodeColor(null)).toBeNull();
		expect(nodeColor('vecino')).toBeNull();
		expect(nodeColorStyle(undefined)).toBeUndefined();
	});

	it('rgbToOklch es la inversa de oklchToRgb', () => {
		const back = rgbToOklch(oklchToRgb(0.7, 0.1, 200));
		expect(back.L).toBeCloseTo(0.7, 2);
		expect(back.C).toBeCloseTo(0.1, 2);
		expect(back.h).toBeCloseTo(200, 0);
	});
});
