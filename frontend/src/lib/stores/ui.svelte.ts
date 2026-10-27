// Estado de la interfaz: disposición adaptable (16.3), panel inferior, paleta de comandos,
// filtros compartidos por el mapa y la lista, nodo seleccionado y avisos emergentes.
import type { NodeStatus, Position, Traceroute } from '$lib/api/types';
import { EMPTY_FILTER, type NodeFilter, type SortKey } from '$lib/utils/nodes';

export type LayoutMode = 'mobile' | 'landscape' | 'tablet' | 'desktop';
export type SheetAnchor = 'peek' | 'half' | 'full';

const QUERIES = {
	landscape: '(orientation: landscape) and (max-height: 500px) and (max-width: 1199.98px)',
	desktop: '(min-width: 1200px)',
	tablet: '(min-width: 768px)'
} as const;

function computeLayout(): LayoutMode {
	if (typeof matchMedia !== 'function') return 'desktop';
	if (matchMedia(QUERIES.landscape).matches) return 'landscape';
	if (matchMedia(QUERIES.desktop).matches) return 'desktop';
	if (matchMedia(QUERIES.tablet).matches) return 'tablet';
	return 'mobile';
}

class Ui {
	layout = $state<LayoutMode>(computeLayout());
	sheet = $state<SheetAnchor>('peek');
	/** Panel lateral plegado (tableta y celular apaisado). */
	sideCollapsed = $state(false);
	paletteOpen = $state(false);
	reducedMotion = $state(false);
	/** Alto visible del panel inferior en px: el mapa ajusta su relleno. */
	sheetHeight = $state(0);
	#started = false;

	get isMobile(): boolean {
		return this.layout === 'mobile';
	}

	get isDesktop(): boolean {
		return this.layout === 'desktop';
	}

	start(): void {
		if (this.#started || typeof matchMedia !== 'function') return;
		this.#started = true;
		const update = () => (this.layout = computeLayout());
		for (const q of Object.values(QUERIES)) matchMedia(q).addEventListener('change', update);
		const rm = matchMedia('(prefers-reduced-motion: reduce)');
		this.reducedMotion = rm.matches;
		rm.addEventListener('change', (e) => (this.reducedMotion = e.matches));
		update();
	}
}

export const ui = new Ui();

class Filters {
	value = $state<NodeFilter>({ ...EMPTY_FILTER });
	sort = $state<SortKey>('last_heard');
	#siteDefaultApplied = false;

	set<K extends keyof NodeFilter>(key: K, v: NodeFilter[K]): void {
		this.value = { ...this.value, [key]: v };
	}

	toggle(
		key: 'onlyActive' | 'onlyInfra' | 'withPosition' | 'withTelemetry' | 'showInactive'
	): void {
		this.set(key, !this.value[key]);
	}

	toggleStatus(status: NodeStatus): void {
		const list = this.value.statuses.includes(status)
			? this.value.statuses.filter((s) => s !== status)
			: [...this.value.statuses, status];
		this.set('statuses', list);
	}

	clear(): void {
		this.value = { ...EMPTY_FILTER, showInactive: this.value.showInactive };
	}

	/** Los inactivos se ocultan salvo que el sitio diga lo contrario (`show_inactive`). */
	applySiteDefault(showInactive: boolean): void {
		if (this.#siteDefaultApplied) return;
		this.#siteDefaultApplied = true;
		this.set('showInactive', showInactive);
	}

	get active(): number {
		const v = this.value;
		return (
			Number(v.onlyActive) +
			Number(v.onlyInfra) +
			Number(v.withPosition) +
			Number(v.withTelemetry) +
			v.statuses.length +
			Number(Boolean(v.role))
		);
	}
}

export const filters = new Filters();

/** Nodo seleccionado (lo fija la ruta /n/[id]) y lo que el mapa dibuja para él. */
class Selection {
	nodeId = $state<string | null>(null);
	/** Recorrido del nodo seleccionado en el rango elegido. */
	track = $state.raw<Position[]>([]);
	/** Índice del punto actual durante la reproducción (null = sin reproducción). */
	cursor = $state<number | null>(null);
	traceroute = $state.raw<Traceroute | null>(null);
	/** Sube para pedirle al mapa que centre el nodo seleccionado. */
	focusTick = $state(0);

	select(id: string | null): void {
		if (id === this.nodeId) return;
		this.nodeId = id;
		this.track = [];
		this.cursor = null;
		this.traceroute = null;
	}

	focus(): void {
		this.focusTick++;
	}
}

export const selection = new Selection();

export type ToastKind = 'info' | 'success' | 'warning' | 'error';

export interface Toast {
	id: number;
	message: string;
	kind: ToastKind;
	action?: { label: string; run: () => void };
	timeout: number;
}

class Toasts {
	list = $state.raw<Toast[]>([]);
	#id = 0;

	show(message: string, opts: Partial<Omit<Toast, 'id' | 'message'>> = {}): number {
		const toast: Toast = { id: ++this.#id, message, kind: 'info', timeout: 5000, ...opts };
		this.list = [...this.list, toast].slice(-4);
		if (toast.timeout > 0) setTimeout(() => this.dismiss(toast.id), toast.timeout);
		return toast.id;
	}

	dismiss(id: number): void {
		this.list = this.list.filter((t) => t.id !== id);
	}
}

export const toasts = new Toasts();
