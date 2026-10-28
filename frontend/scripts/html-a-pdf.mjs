#!/usr/bin/env node
// Imprime una página HTML local a PDF con el Chromium de Playwright (lo usa scripts/manual_pdf.py).
// Uso: node scripts/html-a-pdf.mjs <entrada.html> <salida.pdf> [texto del pie]

import { pathToFileURL } from 'node:url';
import { chromium } from '@playwright/test';

const [input, output, footer = ''] = process.argv.slice(2);
if (!input || !output) {
	console.error('Uso: node scripts/html-a-pdf.mjs <entrada.html> <salida.pdf> [pie]');
	process.exit(2);
}

const browser = await chromium.launch();
try {
	const page = await browser.newPage();
	await page.goto(pathToFileURL(input).href, { waitUntil: 'networkidle' });
	await page.evaluate(() => document.fonts.ready);
	const esc = footer.replace(/[&<>]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;' })[c]);
	await page.pdf({
		path: output,
		format: 'A4',
		printBackground: true,
		preferCSSPageSize: true,
		displayHeaderFooter: true,
		headerTemplate: '<span></span>',
		footerTemplate: `<div style="font: 8px 'Segoe UI', sans-serif; color: #6b7d84; width: 100%; padding: 0 16mm; display: flex; justify-content: space-between;"><span>${esc}</span><span><span class="pageNumber"></span> / <span class="totalPages"></span></span></div>`,
		margin: { top: '16mm', bottom: '18mm', left: '16mm', right: '16mm' }
	});
} finally {
	await browser.close();
}
