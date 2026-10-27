// Actividad en vivo (16.5): pulso del emisor y trazo animado hacia el gateway. La fuente se
// actualiza a ~30 cuadros/s solo mientras hay animaciones; con movimiento reducido se muestra
// un anillo fijo y la fuente cambia solo cuando llega o vence un evento.
import type { GeoJSONSource, Map as MlMap } from 'maplibre-gl';
import type { ActivityEvent, Node } from '$lib/api/types';
import { isValidLatLon, lerp } from '$lib/utils/geo';
import type { Feature, FeatureCollection, LineString, Point } from './geojson';
import { SRC } from './layers';
import { activityCategory, type MapColors } from './theme';

const DURATION_MS = 1600;
const MAX_ITEMS = 24;
const FRAME_MS = 33;

interface Item {
	start: number;
	from: [number, number];
	to: [number, number] | null;
	color: string;
}

type Props = { color: string; opacity: number; radius: number };

export class ActivityLayer {
	#items: Item[] = [];
	#raf = 0;
	#timer: ReturnType<typeof setTimeout> | undefined;
	#lastFrame = 0;
	#map: MlMap;
	#colors: MapColors;
	#reduced: () => boolean;
	enabled = true;

	constructor(map: MlMap, colors: MapColors, reducedMotion: () => boolean) {
		this.#map = map;
		this.#colors = colors;
		this.#reduced = reducedMotion;
	}

	setColors(colors: MapColors): void {
		this.#colors = colors;
	}

	push(ev: ActivityEvent, nodes: Map<string, Node>): void {
		if (!this.enabled) return;
		const from = nodes.get(ev.from);
		if (!from || !isValidLatLon(from.lat, from.lon)) return;
		const gw = ev.gateway ? nodes.get(ev.gateway) : undefined;
		const to =
			gw && gw.id !== from.id && isValidLatLon(gw.lat, gw.lon)
				? ([gw.lon, gw.lat] as [number, number])
				: null;
		this.#items.push({
			start: performance.now(),
			from: [from.lon as number, from.lat as number],
			to,
			color: this.#colors[activityCategory(ev.portnum)]
		});
		if (this.#items.length > MAX_ITEMS) this.#items.splice(0, this.#items.length - MAX_ITEMS);
		if (this.#reduced()) this.#still();
		else if (!this.#raf) this.#raf = requestAnimationFrame(this.#frame);
	}

	clear(): void {
		this.#items = [];
		this.#render(performance.now());
	}

	destroy(): void {
		cancelAnimationFrame(this.#raf);
		clearTimeout(this.#timer);
		this.#raf = 0;
		this.#items = [];
	}

	#frame = (now: number) => {
		this.#raf = 0;
		this.#items = this.#items.filter((it) => now - it.start < DURATION_MS);
		if (now - this.#lastFrame >= FRAME_MS || this.#items.length === 0) {
			this.#lastFrame = now;
			this.#render(now);
		}
		if (this.#items.length) this.#raf = requestAnimationFrame(this.#frame);
	};

	/** Sin animación: dibuja ahora y vuelve a dibujar cuando vence el evento más viejo. */
	#still = () => {
		clearTimeout(this.#timer);
		const now = performance.now();
		this.#items = this.#items.filter((it) => now - it.start < DURATION_MS);
		this.#render(now);
		if (this.#items.length) {
			const wait = this.#items[0].start + DURATION_MS - now;
			this.#timer = setTimeout(this.#still, Math.max(16, wait + 1));
		}
	};

	#render(now: number): void {
		const source = this.#map.getSource(SRC.activity) as GeoJSONSource | undefined;
		if (!source) return;
		const reduced = this.#reduced();
		const features: Feature<Point | LineString, Props>[] = [];
		for (const it of this.#items) {
			const t = Math.min(1, (now - it.start) / DURATION_MS);
			const fade = reduced ? 0.9 : 1 - t;
			features.push({
				type: 'Feature',
				geometry: { type: 'Point', coordinates: it.from },
				properties: { color: it.color, opacity: fade, radius: reduced ? 14 : 6 + 22 * t }
			});
			if (it.to) {
				const head = reduced ? 1 : Math.min(1, t * 1.6);
				features.push({
					type: 'Feature',
					geometry: { type: 'LineString', coordinates: [it.from, lerp(it.from, it.to, head)] },
					properties: { color: it.color, opacity: fade * 0.9, radius: 0 }
				});
			}
		}
		const fc: FeatureCollection<Point | LineString, Props> = {
			type: 'FeatureCollection',
			features
		};
		source.setData(fc as never);
	}
}
