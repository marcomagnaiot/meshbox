// Suscripción pública a notificaciones push (secciones 19.2 y 20). Contrato del backend:
// GET /api/v1/push/vapid-public-key → {key}; POST/DELETE /api/v1/push/subscriptions con
// {endpoint, keys: {p256dh, auth}}. En iPhone requiere la PWA instalada (iOS 16.4+).
import { ApiError } from '$lib/api/client';
import { publicApi, type PushSubscriptionBody } from '$lib/api/public';

export type PushState =
	| 'checking'
	| 'unsupported'
	| 'needs-install'
	| 'denied'
	| 'off'
	| 'on'
	| 'working'
	| 'unavailable';

/** Clave VAPID en base64url → bytes para `applicationServerKey`. */
export function base64UrlToBytes(value: string): Uint8Array<ArrayBuffer> {
	const padded =
		value.replace(/-/g, '+').replace(/_/g, '/') + '='.repeat((4 - (value.length % 4)) % 4);
	const raw = atob(padded);
	const out = new Uint8Array(new ArrayBuffer(raw.length));
	for (let i = 0; i < raw.length; i++) out[i] = raw.charCodeAt(i);
	return out;
}

function toBody(sub: PushSubscription): PushSubscriptionBody {
	const json = sub.toJSON() as { endpoint?: string; keys?: Record<string, string> };
	return {
		endpoint: json.endpoint ?? sub.endpoint,
		keys: { p256dh: json.keys?.p256dh ?? '', auth: json.keys?.auth ?? '' }
	};
}

function isIos(): boolean {
	return /iphone|ipad|ipod/i.test(navigator.userAgent);
}

function isStandalone(): boolean {
	return (
		matchMedia('(display-mode: standalone)').matches ||
		(navigator as Navigator & { standalone?: boolean }).standalone === true
	);
}

class PushStore {
	state = $state<PushState>('checking');
	error = $state<string | null>(null);

	async refresh(): Promise<void> {
		if (typeof window === 'undefined') return;
		if (
			!('serviceWorker' in navigator) ||
			!('PushManager' in window) ||
			!('Notification' in window)
		) {
			this.state = isIos() && !isStandalone() ? 'needs-install' : 'unsupported';
			return;
		}
		if (Notification.permission === 'denied') {
			this.state = 'denied';
			return;
		}
		try {
			const reg = await navigator.serviceWorker.getRegistration();
			const sub = await reg?.pushManager.getSubscription();
			this.state = sub ? 'on' : 'off';
		} catch {
			this.state = 'off';
		}
	}

	async enable(): Promise<void> {
		this.error = null;
		this.state = 'working';
		try {
			const permission = await Notification.requestPermission();
			if (permission !== 'granted') {
				this.state = permission === 'denied' ? 'denied' : 'off';
				return;
			}
			const { key } = await publicApi.vapidKey();
			const reg = await navigator.serviceWorker.ready;
			const sub =
				(await reg.pushManager.getSubscription()) ??
				(await reg.pushManager.subscribe({
					userVisibleOnly: true,
					applicationServerKey: base64UrlToBytes(key)
				}));
			await publicApi.subscribe(toBody(sub));
			this.state = 'on';
		} catch (err) {
			this.state = err instanceof ApiError && err.status === 404 ? 'unavailable' : 'off';
			this.error = err instanceof Error ? err.message : String(err);
		}
	}

	async disable(): Promise<void> {
		this.error = null;
		this.state = 'working';
		try {
			const reg = await navigator.serviceWorker.getRegistration();
			const sub = await reg?.pushManager.getSubscription();
			if (sub) {
				await publicApi.unsubscribe(toBody(sub)).catch(() => undefined);
				await sub.unsubscribe();
			}
			this.state = 'off';
		} catch (err) {
			this.state = 'on';
			this.error = err instanceof Error ? err.message : String(err);
		}
	}
}

export const push = new PushStore();
