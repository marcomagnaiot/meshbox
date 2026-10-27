// Puente entre el mapa (cargado en diferido) y los controles de la interfaz, que están en el
// paquete inicial: los controles llaman acá y el mapa registra su implementación al cargar.

export interface MapActions {
	zoomIn(): void;
	zoomOut(): void;
	resetNorth(): void;
	locate(): Promise<void>;
	fitNodes(): void;
	focusNode(id: string): void;
}

class MapController {
	ready = $state(false);
	failed = $state(false);
	bearing = $state(0);
	locating = $state(false);
	#actions: MapActions | null = null;
	#idle: Promise<void>;
	#resolveIdle: () => void = () => {};

	constructor() {
		this.#idle = new Promise((resolve) => (this.#resolveIdle = resolve));
	}

	/** El mapa terminó su primer dibujo completo (o no se pudo crear). */
	markIdle(): void {
		this.#resolveIdle();
	}

	/** Para diferir trabajo que compite con la carga del mapa (service worker, animaciones). */
	whenIdle(): Promise<void> {
		return this.#idle;
	}

	register(actions: MapActions | null): void {
		this.#actions = actions;
		this.ready = actions !== null;
	}

	zoomIn = () => this.#actions?.zoomIn();
	zoomOut = () => this.#actions?.zoomOut();
	resetNorth = () => this.#actions?.resetNorth();
	fitNodes = () => this.#actions?.fitNodes();
	focusNode = (id: string) => this.#actions?.focusNode(id);
	locate = async () => {
		if (!this.#actions) return;
		this.locating = true;
		try {
			await this.#actions.locate();
		} finally {
			this.locating = false;
		}
	};
}

export const mapController = new MapController();
