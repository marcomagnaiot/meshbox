// Sesión del panel (13.2): la cookie HttpOnly la maneja el navegador; acá se guarda en
// memoria el token CSRF (también lo devuelve /auth/me al recargar) y los datos del usuario.
import { goto } from '$app/navigation';
import { adminApi } from '$lib/api/admin';
import { ApiError, apiHooks } from '$lib/api/client';
import type { AdminSession } from '$lib/api/types';

class AdminStore {
	session = $state.raw<AdminSession | null>(null);
	checking = $state(false);
	checked = $state(false);
	/** Motivo por el que se volvió al inicio de sesión (sesión vencida). */
	notice = $state<string | null>(null);

	constructor() {
		apiHooks.csrfToken = () => this.session?.csrf_token ?? null;
		apiHooks.onUnauthorized = () => this.expired();
	}

	async check(): Promise<AdminSession | null> {
		this.checking = true;
		try {
			const me = await adminApi.me();
			this.session = me;
			return me;
		} catch (err) {
			if (err instanceof ApiError && err.status === 401) this.session = null;
			else throw err;
			return null;
		} finally {
			this.checking = false;
			this.checked = true;
		}
	}

	async login(username: string, password: string): Promise<AdminSession> {
		const session = await adminApi.login(username, password);
		this.session = session;
		this.notice = null;
		this.checked = true;
		// /auth/me agrega datos del equipo (modo, servidor, transmisión).
		try {
			this.session = { ...session, ...(await adminApi.me()) };
		} catch {
			// la sesión del login alcanza
		}
		return this.session;
	}

	/** Sesión creada por el asistente de primer uso (POST /setup/admin deja la cookie). */
	adopt(session: AdminSession): void {
		this.session = session;
		this.notice = null;
		this.checked = true;
	}

	async logout(): Promise<void> {
		try {
			await adminApi.logout();
		} finally {
			this.session = null;
			await goto('/admin/login');
		}
	}

	expired(): void {
		// Durante la verificación inicial decide el layout (sin aviso de "sesión vencida").
		if (this.checking) return;
		if (!this.session && this.checked) return;
		this.session = null;
		this.notice = 'expired';
		const here = typeof location === 'undefined' ? '/admin' : location.pathname;
		if (!here.startsWith('/admin/login')) {
			void goto(`/admin/login?next=${encodeURIComponent(here)}`);
		}
	}
}

export const admin = new AdminStore();
