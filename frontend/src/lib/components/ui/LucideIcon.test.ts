import { render } from '@testing-library/svelte';
import { describe, expect, it } from 'vitest';
import LucideIcon from './LucideIcon.svelte';

const wifi = {
	name: 'wifi',
	size: 24,
	node: [
		['path', { d: 'M12 20h.01' }],
		['circle', { cx: 12, cy: 12, r: 3, key: 'k1' }]
	] as [string, Record<string, string | number>][]
};

describe('LucideIcon (base liviana de los íconos)', () => {
	it('dibuja los trazos dentro del SVG, oculto para lectores por defecto', () => {
		const { container } = render(LucideIcon, { icon: wifi, size: 18, class: 'extra' });
		const svg = container.querySelector('svg')!;
		expect(svg.getAttribute('width')).toBe('18');
		expect(svg.getAttribute('aria-hidden')).toBe('true');
		expect(svg.getAttribute('class')).toContain('lucide-wifi');
		expect(svg.getAttribute('class')).toContain('extra');
		expect(svg.querySelector('path')?.getAttribute('d')).toBe('M12 20h.01');
		const circle = svg.querySelector('circle')!;
		expect(circle.getAttribute('r')).toBe('3');
		expect(circle.hasAttribute('key')).toBe(false);
		// Los trazos quedan en el espacio de nombres de SVG (si no, no se dibujan).
		expect(circle.namespaceURI).toBe('http://www.w3.org/2000/svg');
	});

	it('con etiqueta accesible no se oculta y pasa los demás atributos', () => {
		const { container } = render(LucideIcon, {
			icon: wifi,
			'aria-label': 'WiFi',
			strokeWidth: 3,
			color: 'red'
		});
		const svg = container.querySelector('svg')!;
		expect(svg.hasAttribute('aria-hidden')).toBe(false);
		expect(svg.getAttribute('aria-label')).toBe('WiFi');
		expect(svg.getAttribute('stroke-width')).toBe('3');
		expect(svg.getAttribute('stroke')).toBe('red');
	});
});
