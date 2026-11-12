// Avisos en este equipo (ADR 0023): el panel instalado en el celular, o cualquier navegador, se
// suscribe a push y elige qué recibe: los mensajes que llegan a las placas del Cliente (solo los
// directos o también los de canales) y las alertas. En iPhone, push pide el panel instalado
// en la pantalla de inicio (iOS 16.4 o posterior).
import * as adminApi from '$lib/admin/api';
import type { MessageAlerts } from '$lib/admin/api';
import { base64UrlToBytes } from '$lib/stores/push.svelte';

export type DevicePushState =
	'checking' | 'unsupported' | 'needs-install' | 'denied' | 'unavailable' | 'ready';

interface InstallPrompt extends Event {
	prompt(): Promise<void>;
	userChoice: Promise<{ outcome: 'accepted' | 'dismissed' }>;
}

function isIos(): boolean {
	return (
		/iphone|ipad|ipod/i.test(navigator.userAgent) ||
		(navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1)
	);
}

export function isStandalone(): boolean {
	return (
		matchMedia('(display-mode: standalone)').matches ||
		(navigator as Navigator & { standalone?: boolean }).standalone === true
	);
}

class DevicePush {
	state = $state<DevicePushState>('checking');
	subscribed = $state(false);
	messages = $state<MessageAlerts>('off');
	alerts = $state(true);
	busy = $state(false);
	/** El navegador ofreció instalar el panel (Chrome y Edge; en iPhone es a mano). */
	canInstall = $state(false);
	installed = $state(false);
	#key: string | null = null;
	#prompt: InstallPrompt | null = null;
	#started = false;

	/** Escucha el ofrecimiento de instalar; se llama una vez desde el layout del panel. */
	start(): void {
		if (this.#started || typeof window === 'undefined') return;
		this.#started = true;
		this.installed = isStandalone();
		window.addEventListener('beforeinstallprompt', (e) => {
			e.preventDefault();
			this.#prompt = e as InstallPrompt;
			this.canInstall = true;
		});
		window.addEventListener('appinstalled', () => {
			this.#prompt = null;
			this.canInstall = false;
			this.installed = true;
		});
	}

	async install(): Promise<void> {
		const p = this.#prompt;
		if (!p) return;
		await p.prompt();
		const choice = await p.userChoice;
		if (choice.outcome === 'accepted') {
			this.#prompt = null;
			this.canInstall = false;
		}
	}

	async #subscription(): Promise<PushSubscription | null> {
		const reg = await navigator.serviceWorker.getRegistration();
		return (await reg?.pushManager.getSubscription()) ?? null;
	}

	async refresh(): Promise<void> {
		if (
			typeof window === 'undefined' ||
			!('serviceWorker' in navigator) ||
			!('PushManager' in window) ||
			!('Notification' in window)
		) {
			this.state = isIos() && !isStandalone() ? 'needs-install' : 'unsupported';
			return;
		}
		try {
			const info = await adminApi.notifications.info();
			if (!info.available || !info.public_key) {
				this.state = 'unavailable';
				return;
			}
			this.#key = info.public_key;
			const sub = await this.#subscription();
			const st = sub ? await adminApi.notifications.state(sub.endpoint) : { subscribed: false };
			this.subscribed = st.subscribed;
			this.messages = st.subscribed ? (st.messages ?? 'off') : 'off';
			this.alerts = st.subscribed ? (st.alerts ?? true) : true;
			this.state = Notification.permission === 'denied' ? 'denied' : 'ready';
		} catch {
			this.state = 'unavailable';
		}
	}

	/** Guarda lo que recibe este equipo; si no queda nada, se da de baja. */
	async save(messages: MessageAlerts, alerts: boolean): Promise<void> {
		this.busy = true;
		try {
			if (messages === 'off' && !alerts) {
				await this.off();
				return;
			}
			const reg = await navigator.serviceWorker.ready;
			if (Notification.permission !== 'granted') {
				const permission = await Notification.requestPermission();
				if (permission !== 'granted') {
					this.state = permission === 'denied' ? 'denied' : 'ready';
					throw new Error('denied');
				}
			}
			const sub =
				(await reg.pushManager.getSubscription()) ??
				(await reg.pushManager.subscribe({
					userVisibleOnly: true,
					applicationServerKey: base64UrlToBytes(this.#key ?? '')
				}));
			const json = sub.toJSON() as { endpoint?: string; keys?: Record<string, string> };
			await adminApi.notifications.save({
				endpoint: json.endpoint ?? sub.endpoint,
				keys: { p256dh: json.keys?.p256dh ?? '', auth: json.keys?.auth ?? '' },
				alerts,
				messages
			});
			this.subscribed = true;
			this.messages = messages;
			this.alerts = alerts;
		} finally {
			this.busy = false;
		}
	}

	async off(): Promise<void> {
		this.busy = true;
		try {
			const sub = await this.#subscription();
			if (sub) {
				await adminApi.notifications.remove(sub.endpoint);
				await sub.unsubscribe();
			}
			this.subscribed = false;
			this.messages = 'off';
			this.alerts = true;
		} finally {
			this.busy = false;
		}
	}

	async test(): Promise<void> {
		const sub = await this.#subscription();
		if (!sub) throw new Error('no-subscription');
		await adminApi.notifications.test(sub.endpoint);
	}
}

export const devicePush = new DevicePush();
