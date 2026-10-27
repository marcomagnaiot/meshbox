// Alertas públicas: `GET /api/v1/alerts` y eventos `alert` (firing / resolved). La alerta
// activa más importante se muestra en un aviso en todas las páginas (SOS con aria-live
// assertive).
import { publicApi } from '$lib/api/public';
import type { Alert } from '$lib/api/types';
import { live } from './live.svelte';

const DISMISSED_KEY = 'meshbox.dismissedAlerts';
const SEVERITY_RANK: Record<Alert['severity'], number> = { critical: 0, warning: 1, info: 2 };

function readDismissed(): Set<number> {
	try {
		const raw = globalThis.sessionStorage?.getItem(DISMISSED_KEY);
		return new Set(raw ? (JSON.parse(raw) as number[]) : []);
	} catch {
		return new Set();
	}
}

/** SOS: alerta crítica o de palabra clave (la regla por defecto busca "SOS"). */
export function isSos(alert: Pick<Alert, 'severity' | 'kind' | 'title' | 'body'>): boolean {
	return (
		alert.severity === 'critical' ||
		alert.kind === 'keyword' ||
		/\bSOS\b/i.test(`${alert.title} ${alert.body ?? ''}`)
	);
}

/** La alerta activa a destacar: la más grave y, a igual gravedad, la más reciente. */
export function pickBanner(alerts: Iterable<Alert>, dismissed: Set<number>): Alert | null {
	let best: Alert | null = null;
	for (const a of alerts) {
		if (a.state !== 'firing' || dismissed.has(a.id)) continue;
		if (
			!best ||
			SEVERITY_RANK[a.severity] < SEVERITY_RANK[best.severity] ||
			(SEVERITY_RANK[a.severity] === SEVERITY_RANK[best.severity] && a.ts > best.ts)
		) {
			best = a;
		}
	}
	return best;
}

class AlertsStore {
	byId = $state.raw<Map<number, Alert>>(new Map());
	next = $state<string | null>(null);
	loaded = $state(false);
	loading = $state(false);
	error = $state<unknown>(null);
	dismissed = $state.raw<Set<number>>(readDismissed());
	#bound = false;

	list = $derived([...this.byId.values()].sort((a, b) => b.ts - a.ts));
	banner = $derived(pickBanner(this.byId.values(), this.dismissed));

	#bind(): void {
		if (this.#bound) return;
		this.#bound = true;
		live.core.on('alert', (ev) => {
			const { seq: _seq, ...alert } = ev;
			const map = new Map(this.byId);
			map.set(alert.id, alert);
			this.byId = map;
		});
		live.core.onSync(() => {
			if (this.loaded) void this.load(true);
		});
	}

	async load(force = false): Promise<void> {
		this.#bind();
		if ((this.loaded && !force) || this.loading) return;
		this.loading = true;
		try {
			const page = await publicApi.alerts(null, 20);
			const map = new Map(this.byId);
			for (const a of page.alerts) map.set(a.id, a);
			this.byId = map;
			if (!this.loaded) this.next = page.next ?? null;
			this.loaded = true;
			this.error = null;
		} catch (err) {
			this.error = err;
		} finally {
			this.loading = false;
		}
	}

	async loadMore(): Promise<void> {
		if (!this.next) return;
		try {
			const page = await publicApi.alerts(this.next, 20);
			const map = new Map(this.byId);
			for (const a of page.alerts) map.set(a.id, a);
			this.byId = map;
			this.next = page.next ?? null;
		} catch (err) {
			this.error = err;
		}
	}

	dismiss(id: number): void {
		const set = new Set(this.dismissed);
		set.add(id);
		this.dismissed = set;
		try {
			globalThis.sessionStorage?.setItem(DISMISSED_KEY, JSON.stringify([...set]));
		} catch {
			// sin almacenamiento de sesión: vale hasta recargar
		}
	}
}

export const alerts = new AlertsStore();
