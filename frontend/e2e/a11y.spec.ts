// Accesibilidad automática (16.6, 27): sin violaciones serias ni críticas de axe (WCAG 2.2 AA).
import AxeBuilder from '@axe-core/playwright';
import { expect, test, waitForLive } from './fixtures';

const PAGES: { path: string; ready: string }[] = [
	{ path: '/', ready: 'a[data-node]' },
	{ path: '/nodos', ready: 'a[data-node]' },
	{ path: '/chat', ready: '.msg' },
	{ path: '/acerca', ready: '.notice' }
];

for (const { path, ready } of PAGES) {
	test(`axe sin violaciones serias en ${path}`, async ({ page }) => {
		await page.goto(path);
		await waitForLive(page);
		await page.locator(ready).first().waitFor({ state: 'attached' });
		const results = await new AxeBuilder({ page })
			.withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'wcag22aa'])
			.analyze();
		const serious = results.violations.filter(
			(v) => v.impact === 'serious' || v.impact === 'critical'
		);
		const summary = serious.map((v) => ({
			id: v.id,
			impact: v.impact,
			help: v.help,
			nodes: v.nodes
				.slice(0, 4)
				.map((n) => `${n.target.join(' ')} :: ${n.html.slice(0, 200)} :: ${n.failureSummary ?? ''}`)
		}));
		expect(summary, JSON.stringify(summary, null, 2)).toEqual([]);
	});
}
