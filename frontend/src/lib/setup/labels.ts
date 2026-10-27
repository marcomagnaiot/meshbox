// Nombres de los pasos del asistente (18.1).
import type { SetupStep } from '$lib/admin/types';
import { m } from '$lib/paraglide/messages';

export function stepLabel(step: SetupStep): string {
	switch (step) {
		case 'wifi':
			return m.setup_step_wifi();
		case 'code':
			return m.setup_step_code();
		case 'locale':
			return m.setup_step_locale();
		case 'admin':
			return m.setup_step_admin();
		case 'site':
			return m.setup_step_site();
		case 'radio':
			return m.setup_step_radio();
		case 'channel':
			return m.setup_step_channel();
		case 'privacy':
			return m.setup_step_privacy();
		case 'tiles':
			return m.setup_step_tiles();
		case 'cloudflare':
			return m.setup_step_cloudflare();
		case 'finish':
			return m.setup_step_finish();
		default:
			return step;
	}
}
