import { render } from '@testing-library/svelte';
import { describe, expect, it } from 'vitest';
import type { NoticeBlock } from '$lib/api/types';
import NoticeBlocks from './NoticeBlocks.svelte';

describe('aviso de privacidad en bloques (13.5: nunca HTML)', () => {
	it('dibuja párrafos, títulos, listas y formato en línea', () => {
		const blocks: NoticeBlock[] = [
			{ t: 'h3', c: [{ t: 'text', v: 'Privacidad' }] },
			{
				t: 'p',
				c: [
					{ t: 'text', v: 'Se muestra ' },
					{ t: 'strong', v: 'solo' },
					{ t: 'text', v: ' el canal ' },
					{ t: 'em', v: 'público' },
					{ t: 'text', v: ' y ' },
					{ t: 'code', v: 'LongFast' }
				]
			},
			{
				t: 'ul',
				c: [
					[{ t: 'text', v: 'uno' }],
					[{ t: 'link', v: 'OSM', href: 'https://www.openstreetmap.org' }]
				]
			}
		];
		const { container } = render(NoticeBlocks, { blocks });
		expect(container.querySelector('h3')?.textContent).toBe('Privacidad');
		expect(container.querySelector('p strong')?.textContent).toBe('solo');
		expect(container.querySelector('p em')?.textContent).toBe('público');
		expect(container.querySelector('p code')?.textContent).toBe('LongFast');
		expect(container.querySelectorAll('li')).toHaveLength(2);
		const link = container.querySelector('a');
		expect(link?.getAttribute('href')).toBe('https://www.openstreetmap.org');
		expect(link?.getAttribute('rel')).toContain('noopener');
	});

	it('el HTML que venga en el texto se muestra como texto', () => {
		const blocks: NoticeBlock[] = [
			{ t: 'p', c: [{ t: 'text', v: '<img src=x onerror="alert(1)"><b>hola</b>' }] }
		];
		const { container } = render(NoticeBlocks, { blocks });
		expect(container.querySelector('img')).toBeNull();
		expect(container.querySelector('b')).toBeNull();
		expect(container.querySelector('p')?.textContent).toBe(
			'<img src=x onerror="alert(1)"><b>hola</b>'
		);
	});

	it('los enlaces que no son http(s) ni mailto quedan como texto', () => {
		const blocks: NoticeBlock[] = [
			{ t: 'p', c: [{ t: 'link', v: 'clic', href: 'javascript:alert(1)' }] },
			{ t: 'p', c: [{ t: 'link', v: 'correo', href: 'mailto:admin@ejemplo.com' }] }
		];
		const { container } = render(NoticeBlocks, { blocks });
		const links = container.querySelectorAll('a');
		expect(links).toHaveLength(1);
		expect(links[0].getAttribute('href')).toBe('mailto:admin@ejemplo.com');
		expect(container.textContent).toContain('clic');
	});

	it('bloques de tipo desconocido se ignoran', () => {
		const blocks = [{ t: 'script', c: [{ t: 'text', v: 'x' }] }] as unknown as NoticeBlock[];
		const { container } = render(NoticeBlocks, { blocks });
		expect(container.textContent?.trim()).toBe('');
	});
});
