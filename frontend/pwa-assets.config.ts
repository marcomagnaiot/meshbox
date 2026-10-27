// Íconos de la PWA desde static/favicon.svg (`pnpm gen:icons`): favicon.ico, pwa-64/192/512,
// maskable-icon-512 y apple-touch-icon-180. Los PNG se versionan en static/.
import { defineConfig, minimal2023Preset as preset } from '@vite-pwa/assets-generator/config';

const background = '#0f141b';

export default defineConfig({
	headLinkOptions: { preset: '2023' },
	preset: {
		...preset,
		maskable: { ...preset.maskable, resizeOptions: { background, fit: 'contain' } },
		apple: { ...preset.apple, resizeOptions: { background, fit: 'contain' } }
	},
	images: ['static/favicon.svg']
});
