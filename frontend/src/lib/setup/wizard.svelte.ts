// Estado del asistente de primer uso (18.1): pasos visibles según el equipo, paso actual,
// pasos hechos y acceso. Sin usuarios se usa el código de configuración (X-Setup-Code, solo en
// memoria); creado el administrador, la sesión (cookie y CSRF) sigue el resto de los pasos.
import * as adminApi from '$lib/admin/api';
import type { SetupState, SetupStep } from '$lib/admin/types';
import { ApiError } from '$lib/api/client';
import { admin } from '$lib/stores/admin.svelte';

export type Access =
	| 'loading'
	/** Sin usuarios y con la ventana de 60 min abierta: código o punto de acceso. */
	| 'setup'
	/** Con sesión de administrador. */
	| 'session'
	/** Ya hay usuarios: iniciar sesión para seguir. */
	| 'login'
	/** Sin usuarios y la ventana se cerró: reiniciar el equipo. */
	| 'closed'
	| 'error';

/** Pasos de esta visita: "code" solo sin usuarios (y fuera del punto de acceso), "admin" solo sin usuarios. */
export function visibleSteps(st: SetupState): SetupStep[] {
	return st.steps.filter((s) => {
		if (s === 'code') return !st.users_exist && st.code_required;
		if (s === 'admin') return !st.users_exist;
		return true;
	});
}

export class Wizard {
	state = $state.raw<SetupState | null>(null);
	error = $state.raw<unknown>(null);
	access = $state<Access>('loading');
	/** Código de configuración ya verificado (nunca se guarda en el navegador). */
	code = $state<string | null>(null);
	current = $state<SetupStep>('locale');
	done = $state<SetupStep[]>([]);
	/** Fijos durante la visita: crear el administrador no cambia la lista. */
	steps = $state<SetupStep[]>([]);

	index = $derived(this.steps.indexOf(this.current));

	async load(): Promise<void> {
		if (!this.state) this.access = 'loading';
		try {
			const st = await adminApi.setup.state();
			this.state = st;
			const first = !this.steps.length;
			if (first) this.steps = visibleSteps(st);
			this.done = [...new Set([...this.done, ...st.completed])];
			if (st.users_exist) {
				const session = admin.session ?? (await admin.check());
				this.access = session && session.role === 'admin' ? 'session' : 'login';
			} else {
				this.access = st.window_open ? 'setup' : 'closed';
			}
			// La primera vez, el primer paso pendiente; después, se queda donde está si sigue valiendo.
			if (first || !this.steps.includes(this.current) || this.done.includes(this.current)) {
				this.current = this.firstPending();
			}
			this.error = null;
		} catch (err) {
			this.error = err;
			this.access = 'error';
		}
	}

	firstPending(): SetupStep {
		return this.steps.find((s) => !this.done.includes(s)) ?? 'finish';
	}

	isDone(step: SetupStep): boolean {
		return this.done.includes(step);
	}

	/** Se puede ir directo a un paso hecho o al primero pendiente (sin pasar "admin" sin sesión). */
	reachable(step: SetupStep): boolean {
		const i = this.steps.indexOf(step);
		if (i < 0) return false;
		if (this.access !== 'session') {
			const adminAt = this.steps.indexOf('admin');
			if (adminAt >= 0 && i > adminAt) return false;
		}
		return this.isDone(step) || step === this.firstPending();
	}

	go(step: SetupStep): void {
		if (this.steps.includes(step)) this.current = step;
		if (typeof window !== 'undefined') window.scrollTo({ top: 0 });
	}

	/** Marca el paso como hecho y avanza al siguiente. */
	complete(step: SetupStep = this.current): void {
		if (!this.done.includes(step)) this.done = [...this.done, step];
		const i = this.steps.indexOf(step);
		this.go(this.steps[i + 1] ?? 'finish');
	}

	back(): void {
		const i = this.index;
		if (i > 0) this.go(this.steps[i - 1]);
	}

	/** POST a /api/v1/setup/{path}: con el código mientras no hay sesión. */
	post<T = Record<string, unknown>>(path: string, body?: unknown): Promise<T> {
		return adminApi.setup.post<T>(path, body, admin.session ? null : this.code);
	}

	/** El servidor volvió a pedir el código (se reinició o venció): pedirlo de nuevo. */
	handleAuth(err: unknown): boolean {
		if (err instanceof ApiError && err.status === 401 && err.problem.code_required) {
			this.code = null;
			if (this.steps.includes('code')) {
				this.done = this.done.filter((s) => s !== 'code');
				this.go('code');
			}
			return true;
		}
		return false;
	}
}
