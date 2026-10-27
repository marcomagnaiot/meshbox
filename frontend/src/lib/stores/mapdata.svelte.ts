// Datos de capas del mapa que no son la foto de nodos: enlaces (`GET /api/v1/links` + evento
// `link`) y puntos de interés (`GET /api/v1/waypoints` + evento `waypoint`).
import { publicApi } from '$lib/api/public';
import type { Link, Waypoint } from '$lib/api/types';
import { live } from './live.svelte';

export const linkKey = (l: Pick<Link, 'a' | 'b' | 'source'>) => `${l.a}|${l.b}|${l.source}`;
const LINK_MAX_AGE_S = 86400;

class MapData {
	links = $state.raw<Map<string, Link>>(new Map());
	waypoints = $state.raw<Map<number, Waypoint>>(new Map());
	#bound = false;
	#linksLoaded = false;
	#waypointsLoaded = false;

	#bind(): void {
		if (this.#bound) return;
		this.#bound = true;
		live.core.on('link', (ev) => {
			const { seq: _seq, ...link } = ev;
			const map = new Map(this.links);
			map.set(linkKey(link), link);
			this.links = map;
		});
		live.core.on('waypoint', (ev) => {
			const { seq: _seq, deleted, ...wp } = ev;
			const map = new Map(this.waypoints);
			if (deleted) map.delete(wp.id);
			else map.set(wp.id, wp as Waypoint);
			this.waypoints = map;
		});
		live.core.onSync(() => {
			if (this.#linksLoaded) void this.loadLinks(true);
			if (this.#waypointsLoaded) void this.loadWaypoints(true);
		});
	}

	async loadLinks(force = false): Promise<void> {
		this.#bind();
		if (this.#linksLoaded && !force) return;
		this.#linksLoaded = true;
		try {
			const list = await publicApi.links(LINK_MAX_AGE_S);
			const map = new Map<string, Link>();
			// La API devuelve del más nuevo al más viejo: se queda el primero de cada clave.
			for (const l of list) if (!map.has(linkKey(l))) map.set(linkKey(l), l);
			this.links = map;
		} catch {
			this.#linksLoaded = false;
		}
	}

	async loadWaypoints(force = false): Promise<void> {
		this.#bind();
		if (this.#waypointsLoaded && !force) return;
		this.#waypointsLoaded = true;
		try {
			const list = await publicApi.waypoints();
			this.waypoints = new Map(list.map((w) => [w.id, w]));
		} catch {
			this.#waypointsLoaded = false;
		}
	}
}

export const mapData = new MapData();
